# -*- coding: utf-8 -*-
"""部署 Cloudflare Worker（用 REST API，不需要 wrangler）。

用法:
  python scripts/deploy_worker.py                # 部署 worker/worker.js
  python scripts/deploy_worker.py --dry-run      # 只做语法检查
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "worker" / "worker.js"

ACCOUNT = "c9edadde3416e33b1d2501ae4fc1f10f"
SCRIPT_NAME = "delta-codes-api"
TOKEN_FILE = Path(r"D:\APP\dswork\.cf-token")

# ⚠️ PUT /workers/scripts/<name> 是整体替换，metadata 里不给 bindings 就会把
#    已有的绑定（D1 等）全部弄丢。所以这里必须显式带上。
D1_DATABASE_ID = "4de56c0d-0c61-4a7d-81cd-3b66c6069cbd"
BINDINGS = [
    {"type": "d1", "name": "DB", "id": D1_DATABASE_ID},
]


def worker_token():
    """优先用 worker 专用令牌文件，没有就回退到主令牌"""
    for p in [Path(r"D:\APP\dswork\.cf-worker-token"), TOKEN_FILE]:
        if p.exists():
            t = p.read_text(encoding="utf-8").strip()
            if t:
                return t
    sys.exit("找不到 Cloudflare 令牌")


def check_syntax(src):
    """用 Node 做一次模块语法检查"""
    import subprocess
    import tempfile
    import os
    node = os.environ.get("DSH_NODE") or str(
        Path(os.environ.get("DSH_HOME", r"C:\Users\哈基米.OBITO\.dsh"))
        / "dsh-runtimes" / "dsh-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as f:
        f.write(src)
        tmp = f.name
    try:
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        return r.returncode == 0, (r.stderr or "").strip()
    finally:
        os.unlink(tmp)


def deploy(src, token, bindings=None):
    boundary = "----dsh" + uuid.uuid4().hex
    meta_obj = {"main_module": "worker.js", "compatibility_date": "2024-11-01"}
    if bindings:
        meta_obj["bindings"] = bindings
    meta = json.dumps(meta_obj)

    parts = []
    parts.append(f"--{boundary}\r\n"
                 'Content-Disposition: form-data; name="metadata"; filename="metadata.json"\r\n'
                 "Content-Type: application/json\r\n\r\n" + meta + "\r\n")
    parts.append(f"--{boundary}\r\n"
                 'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
                 "Content-Type: application/javascript+module\r\n\r\n" + src + "\r\n")
    parts.append(f"--{boundary}--\r\n")
    body = "".join(parts).encode("utf-8")

    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/scripts/{SCRIPT_NAME}"
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"success": False, "errors": [{"message": f"HTTP {e.code}"}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-bindings", action="store_true",
                    help="不带任何绑定（纯转发型 Worker 用）")
    args = ap.parse_args()

    src = WORKER.read_text(encoding="utf-8")
    print(f"Worker 源码 {len(src)} 字节  ({WORKER.name})")

    ok, err = check_syntax(src)
    print(f"语法检查: {'✓ 通过' if ok else '✗ 失败'}")
    if not ok:
        print(err)
        sys.exit(1)
    if args.dry_run:
        return

    token = worker_token()
    bindings = [] if args.no_bindings else BINDINGS
    if bindings:
        print("绑定:", ", ".join(f"{b['type']}:{b['name']}" for b in bindings))
    print(f"部署到 {SCRIPT_NAME} …")
    d = deploy(src, token, bindings)
    if d.get("success"):
        r = d.get("result", {})
        print(f"  ✅ 部署成功  modified={r.get('modified_on')}  etag={str(r.get('etag'))[:16]}")
    else:
        print("  ❌ 失败:")
        for e in d.get("errors", []):
            print("    ", e.get("code"), e.get("message"))
        sys.exit(1)


if __name__ == "__main__":
    main()
