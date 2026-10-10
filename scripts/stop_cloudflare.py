# -*- coding: utf-8 -*-
"""把 Cloudflare 降级成"只做跳转"：

  1. 摘掉 Pages 的两个自定义域名（站点不再托管在 Cloudflare）
  2. 摘掉 Worker 的 api.hajimiovo.top 自定义域名
  3. Worker 路由从 hajimiovo.top/api/* 扩到整个域名，用来做 301 跳转
  4. Worker 本体改写成纯跳转（不再碰 D1）

用法:  python scripts/stop_cloudflare.py --dry-run
       python scripts/stop_cloudflare.py --apply
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

TOKEN = Path(r"D:\APP\dswork\.cf-token").read_text(encoding="utf-8").strip()
ACCOUNT = "c9edadde3416e33b1d2501ae4fc1f10f"
ZONE = "9a26264be7dfc1650b000bc40befa715"
PROJECT = "delta-codes"
WORKER = "delta-codes-api"
SERVER = "119.45.171.242:8080"


def api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {"success": True, "result": None}
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"success": False, "errors": [{"message": f"HTTP {e.code}"}]}


def show_state():
    print("=== 当前状态 ===")
    d = api("GET", f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains")
    print("  Pages 域名:")
    for x in d.get("result") or []:
        print(f"    {x['name']}  status={x.get('status')}")
    d = api("GET", f"/zones/{ZONE}/workers/routes")
    print("  Worker 路由:")
    for x in d.get("result") or []:
        print(f"    {x['pattern']} -> {x['script']}  id={x['id']}")
    d = api("GET", f"/accounts/{ACCOUNT}/workers/domains")
    print("  Worker 自定义域名:")
    for x in d.get("result") or []:
        if "hajimi" in (x.get("hostname") or ""):
            print(f"    {x['hostname']} -> {x['service']}  id={x['id']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    show_state()
    if args.dry_run or not args.apply:
        print("\n（dry-run，什么都没改。加 --apply 执行）")
        return

    print("\n=== 开始执行 ===")

    # 1. 摘 Pages 自定义域名
    d = api("GET", f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains")
    for x in d.get("result") or []:
        r = api("DELETE", f"/accounts/{ACCOUNT}/pages/projects/{PROJECT}/domains/{x['name']}")
        print(f"  Pages 域名 {x['name']}: {'✅ 已摘掉' if r.get('success') else '❌ ' + str(r.get('errors'))}")

    # 2. 摘 Worker 自定义域名
    d = api("GET", f"/accounts/{ACCOUNT}/workers/domains")
    for x in d.get("result") or []:
        if (x.get("service") == WORKER and x.get("hostname") != "hajimiovo.top"):
            r = api("DELETE", f"/accounts/{ACCOUNT}/workers/domains/{x['id']}")
            print(f"  Worker 域名 {x['hostname']}: {'✅ 已摘掉' if r.get('success') else '❌ ' + str(r.get('errors'))}")

    # 3. 路由改成覆盖整个域名（含 www）
    d = api("GET", f"/zones/{ZONE}/workers/routes")
    for x in d.get("result") or []:
        if x["script"] == WORKER:
            api("DELETE", f"/zones/{ZONE}/workers/routes/{x['id']}")
            print(f"  删除旧路由 {x['pattern']}")
    for pat in ["hajimiovo.top/*", "www.hajimiovo.top/*"]:
        r = api("POST", f"/zones/{ZONE}/workers/routes", {"pattern": pat, "script": WORKER})
        print(f"  新路由 {pat}: {'✅' if r.get('success') else '❌ ' + str(r.get('errors'))}")

    print("\n=== 改完后 ===")
    show_state()


if __name__ == "__main__":
    main()
