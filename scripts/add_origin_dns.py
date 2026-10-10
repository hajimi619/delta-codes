# -*- coding: utf-8 -*-
"""在 Cloudflare 上给服务器加一个只做 DNS 的名字（灰云），
让 Worker 能通过域名访问源站 —— Worker 不能 fetch 裸 IP。"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

TOKEN = Path(r"D:\APP\dswork\.cf-token").read_text(encoding="utf-8").strip()
ZONE = "9a26264be7dfc1650b000bc40befa715"
HOST = "origin.hajimiovo.top"
IP = "119.45.171.242"


def api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"success": False, "errors": [{"message": f"HTTP {e.code}"}]}


# 看看有没有已存在的
d = api("GET", f"/zones/{ZONE}/dns_records?name={HOST}")
existing = d.get("result") or []
payload = {"type": "A", "name": HOST, "content": IP, "ttl": 60,
           "proxied": False, "comment": "Worker 回源用，只做 DNS"}

if existing:
    rid = existing[0]["id"]
    r = api("PUT", f"/zones/{ZONE}/dns_records/{rid}", payload)
    print("更新已有记录")
else:
    r = api("POST", f"/zones/{ZONE}/dns_records", payload)
    print("新建记录")

if r.get("success"):
    res = r["result"]
    print(f"  ✅ {res['type']} {res['name']} -> {res['content']}  proxied={res['proxied']}  id={res['id']}")
else:
    print("  ❌", r.get("errors"))
    sys.exit(1)
