# -*- coding: utf-8 -*-
"""Cloudflare zone 删掉重建之后，把所有配置恢复回去。

会被恢复的东西：
  1. DNS：hajimiovo.top / www → CNAME delta-codes.pages.dev（proxied）
  2. DNS：api.hajimiovo.top 的 Worker 自定义域名记录（由 API 自动创建）
  3. Pages 自定义域名：hajimiovo.top、www.hajimiovo.top
  4. Worker 自定义域名：api.hajimiovo.top
  5. Worker 路由：hajimiovo.top/api/* → delta-codes-api

用法：python scripts/restore_zone.py
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

TOKEN = (Path(r"D:\APP\dswork\.cf-token")).read_text().strip()
ACCOUNT = "c9edadde3416e33b1d2501ae4fc1f10f"
ZONE_NAME = "hajimiovo.top"
PAGES_PROJECT = "delta-codes"
PAGES_TARGET = "delta-codes.pages.dev"
WORKER = "delta-codes-api"
API = "https://api.cloudflare.com/client/v4"


def call(method, path, body=None, tries=5):
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(tries):
        req = urllib.request.Request(API + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + TOKEN)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "dsh-restore")
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            last = f"{e.code} {detail}"
            if e.code in (403, 429) and i < tries - 1:
                time.sleep(15 * (i + 1))
                continue
            raise RuntimeError(f"{method} {path} -> {last}")
        except Exception as e:
            last = str(e)
            if i < tries - 1:
                time.sleep(4 * (i + 1))
                continue
            raise RuntimeError(f"{method} {path} -> {last}")
    raise RuntimeError("重试耗尽: " + str(last))


def find_zone():
    """等 zone 出现并变成 active"""
    for attempt in range(40):
        r = call("GET", f"/zones?name={ZONE_NAME}")
        if r.get("result"):
            z = r["result"][0]
            print(f"  [{attempt+1}] zone={z['id']} status={z['status']} NS={','.join(z['name_servers'])}")
            if z["status"] == "active":
                return z["id"]
        else:
            print(f"  [{attempt+1}] 还没找到 zone")
        time.sleep(20)
    raise RuntimeError("等不到 active 的 zone")


def upsert_dns(zone_id, rec):
    r = call("GET", f"/zones/{zone_id}/dns_records?type={rec['type']}&name={rec['name']}")
    if r.get("result"):
        rid = r["result"][0]["id"]
        call("PUT", f"/zones/{zone_id}/dns_records/{rid}", rec)
        return "更新"
    call("POST", f"/zones/{zone_id}/dns_records", rec)
    return "新建"


def main():
    print("=== 1. 等 zone 激活 ===")
    zid = find_zone()

    print("=== 2. 恢复 DNS 记录 ===")
    for name in (ZONE_NAME, "www." + ZONE_NAME):
        rec = {"type": "CNAME", "name": name, "content": PAGES_TARGET,
               "proxied": True, "ttl": 1}
        print(f"  {name} -> {upsert_dns(zid, rec)}")

    print("=== 3. 恢复 Pages 自定义域名 ===")
    for name in (ZONE_NAME, "www." + ZONE_NAME):
        try:
            call("POST", f"/accounts/{ACCOUNT}/pages/projects/{PAGES_PROJECT}/domains", {"name": name})
            print(f"  {name} 已添加")
        except RuntimeError as e:
            print(f"  {name}: {e}")

    print("=== 4. 恢复 Worker 自定义域名 ===")
    try:
        call("POST", f"/accounts/{ACCOUNT}/workers/domains",
             {"zone_id": zid, "hostname": "api." + ZONE_NAME, "service": WORKER, "environment": "production"})
        print("  api." + ZONE_NAME + " 已添加")
    except RuntimeError as e:
        print("  " + str(e))

    print("=== 5. 恢复 Worker 路由 ===")
    try:
        call("POST", f"/zones/{zid}/workers/routes",
             {"pattern": f"{ZONE_NAME}/api/*", "script": WORKER})
        print(f"  {ZONE_NAME}/api/* -> {WORKER} 已添加")
    except RuntimeError as e:
        print("  " + str(e))

    print("=== 6. 最终状态 ===")
    recs = call("GET", f"/zones/{zid}/dns_records")
    for x in recs.get("result", []):
        print(f"  {x['type']} {x['name']} -> {x['content']} proxied={x['proxied']}")
    doms = call("GET", f"/accounts/{ACCOUNT}/pages/projects/{PAGES_PROJECT}/domains")
    for x in doms.get("result", []):
        print(f"  Pages {x['name']} status={x['status']}")
    routes = call("GET", f"/zones/{zid}/workers/routes")
    for x in routes.get("result", []):
        print(f"  Route {x['pattern']} -> {x['script']}")


if __name__ == "__main__":
    main()
