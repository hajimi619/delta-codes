# -*- coding: utf-8 -*-
"""把 Cloudflare D1 里的网友改动搬到自建服务器的 JSON 存储。

切换到国内服务器之前必须跑一次，否则备案期间网友提交的改动会丢。

用法:
  python scripts/migrate_d1_to_server.py            # 正式迁移（覆盖服务器数据）
  python scripts/migrate_d1_to_server.py --dry-run  # 只看差异，不动服务器
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

try:
    import paramiko
except ImportError:
    sys.exit("缺少 paramiko，请先: pip install paramiko")

CF_API = "https://api.hajimiovo.top/api/changes"
HOST = "119.45.171.242"
USER = "root"
KEY_PATH = Path(r"D:\APP\dswork\.ssh\id_ed25519_hajimiovo")
REMOTE_STORE = "/var/lib/hajimiovo/changes.json"


def fetch_cf():
    req = urllib.request.Request(CF_API, headers={"User-Agent": "dsh-migrate"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    return data.get("changes", [])


def ssh():
    k = paramiko.Ed25519Key.from_private_key_file(str(KEY_PATH))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=22, username=USER, pkey=k, timeout=25)
    return c


def read_remote(c):
    sftp = c.open_sftp()
    try:
        with sftp.open(REMOTE_STORE, "r") as f:
            raw = f.read().decode()
    except IOError:
        return []
    finally:
        sftp.close()
    try:
        d = json.loads(raw)
        return d if isinstance(d, list) else d.get("changes", [])
    except Exception:
        return []


def write_remote(c, changes):
    body = json.dumps({"changes": changes}, ensure_ascii=False).encode("utf-8")
    sftp = c.open_sftp()
    try:
        with sftp.open(REMOTE_STORE + ".new", "wb") as f:
            f.write(body)
        sftp.posix_rename(REMOTE_STORE + ".new", REMOTE_STORE)
    finally:
        sftp.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=== 1. 从 Cloudflare 拉取 ===")
    cf = fetch_cf()
    print(f"  Cloudflare 上有 {len(cf)} 条改动")
    for c in cf:
        tag = "新增" if c.get("type") == "add" else "标记"
        print(f"    [{tag}] {c.get('gun') or c.get('target_id')}  {c.get('code') or c.get('status')}  by {c.get('author') or '-'}")

    c = ssh()
    try:
        print("\n=== 2. 读取服务器现有数据 ===")
        local = read_remote(c)
        print(f"  服务器上有 {len(local)} 条改动")

        have = {x.get("id") for x in local}
        new = [x for x in cf if x.get("id") not in have]
        print(f"  需要新增 {len(new)} 条")

        if not new:
            print("\n两边一致，无需迁移。")
            return

        print("\n=== 3. 合并 ===")
        merged = local + new
        # 按时间排序，方便人工看
        merged.sort(key=lambda x: x.get("created_at") or "")

        if args.dry_run:
            print(f"  [dry-run] 会写入 {len(merged)} 条，未做任何修改")
            return

        write_remote(c, merged)
        print(f"  已写入 {len(merged)} 条到 {REMOTE_STORE}")

        # 权限 + 重启服务让内存里的数据同步
        for cmd in [
            f"chown www-data:www-data {REMOTE_STORE}",
            "systemctl restart hajimiovo-api && sleep 2 && systemctl is-active hajimiovo-api",
            "curl -s --max-time 5 http://127.0.0.1:8080/api/health",
        ]:
            _, o, e = c.exec_command(cmd, timeout=60)
            out = (o.read().decode().strip() or e.read().decode().strip())
            print("  $", cmd[:50], "->", out)
    finally:
        c.close()

    print("\n[ok] 迁移完成")


if __name__ == "__main__":
    main()
