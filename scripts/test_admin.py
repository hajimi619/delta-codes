# -*- coding: utf-8 -*-
"""管理员系统全流程回归测试。\n\n用法（PowerShell）:\n  $env:HAJIMI_ADMIN_PWD="你的密码"; & $py scripts\\test_admin.py\n"""
import json
import urllib.request
import urllib.error

import os
import sys

BASE = os.environ.get("HAJIMI_BASE", "http://119.45.171.242:8080")
USER = os.environ.get("HAJIMI_ADMIN_USER", "hajimi")
PWD = os.environ.get("HAJIMI_ADMIN_PWD", "")
if not PWD:
    sys.exit("请先设置环境变量 HAJIMI_ADMIN_PWD=<管理员密码>")

PASS, FAIL = [], []


def call(method, path, body=None, token=None, origin=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def check(label, cond, extra=""):
    (PASS if cond else FAIL).append(label)
    print(f"  {'✓' if cond else '✗'} {label}" + (f"   {extra}" if extra else ""))


def changes():
    _, d = call("GET", "/api/changes")
    return d.get("changes", [])


def find(target_id):
    for c in changes():
        if c.get("target_id") == target_id and c.get("type") in ("edit", "delete"):
            return c
    return None


print("=" * 60)
print("1. 登录鉴权")
print("=" * 60)
st, d = call("POST", "/api/admin/login", {"username": USER, "password": "wrong-password"})
check("错误密码被拒", st == 400 and "不对" in d.get("error", ""), d.get("error", ""))

st, d = call("POST", "/api/admin/login", {"username": "nobody", "password": PWD})
check("错误用户名被拒", st == 400, d.get("error", ""))

st, d = call("POST", "/api/admin/login", {"username": USER, "password": PWD})
TOKEN = d.get("token", "")
check("正确凭据登录成功", st == 200 and len(TOKEN) == 64, f"token 长度 {len(TOKEN)}")

st, d = call("GET", "/api/admin/me", token=TOKEN)
check("令牌校验通过", st == 200 and d.get("username") == USER)

st, d = call("GET", "/api/admin/me", token="bogus-token-xxxx")
check("伪造令牌被拒", st == 401, d.get("error", ""))

print()
print("=" * 60)
print("2. 未登录不能调管理接口")
print("=" * 60)
for path, body in [("/api/admin/delete", {"target_id": "x"}),
                   ("/api/admin/edit", {"target_id": "x"}),
                   ("/api/admin/clearflags", {}),
                   ("/api/admin/purge", {"target_id": "user|x"})]:
    st, d = call("POST", path, body)
    check(f"{path} 无令牌被拒", st == 400 and "登录" in d.get("error", ""), d.get("error", ""))

print()
print("=" * 60)
print("3. 先加一条网友数据（模拟普通人提交）")
print("=" * 60)
st, d = call("POST", "/api/add", {"gun": "M14射手步枪", "build": "管理员测试用", "tab": "烽火地带",
                                  "code": "ADMINTEST00001", "author": "测试员"})
check("新增成功", st == 200 and d.get("ok"), str(d))
USER_ID = d.get("id", "")
print(f"     新记录 id = {USER_ID}")

print()
print("=" * 60)
print("4. 编辑基础数据（那 347 条里的）")
print("=" * 60)
BASE_ID = "烽火地带|6L6J4B01SD6JA3I74O3I"   # 随便挑一条基础数据
st, d = call("POST", "/api/admin/edit", {
    "target_id": BASE_ID, "gun": "M14射手步枪", "build": "管理员改过的名字",
    "tab": "全面战场", "code": "EDITEDCODE12345"}, token=TOKEN)
check("编辑基础数据成功", st == 200 and d.get("ok"), str(d))
e = find(BASE_ID)
check("改动已落库", e is not None and e.get("code") == "EDITEDCODE12345",
      f"gun={e.get('gun')} build={e.get('build')} tab={e.get('tab')} code={e.get('code')}")

print()
print("=" * 60)
print("5. 编辑同一目标会覆盖（不会堆积）")
print("=" * 60)
call("POST", "/api/admin/edit", {"target_id": BASE_ID, "gun": "M14射手步枪", "build": "第二次改",
                                 "tab": "烽火地带", "code": "EDITEDCODE22222"}, token=TOKEN)
n = len([c for c in changes() if c.get("type") == "edit" and c.get("target_id") == BASE_ID])
check("同一目标只有一条 edit", n == 1, f"实际 {n} 条")

print()
print("=" * 60)
print("6. 删除 → 恢复")
print("=" * 60)
st, d = call("POST", "/api/admin/delete", {"target_id": BASE_ID}, token=TOKEN)
check("删除成功", st == 200 and d.get("deleted") is True, str(d))
e = find(BASE_ID)
check("删除记录已落库", e is not None and e.get("status") == "deleted", str(e and e.get("status")))

st, d = call("POST", "/api/admin/delete", {"target_id": BASE_ID, "undo": True}, token=TOKEN)
check("恢复成功", st == 200 and d.get("deleted") is False, str(d))
e = find(BASE_ID)
check("恢复后状态是 valid", e is not None and e.get("status") == "valid", str(e and e.get("status")))

print()
print("=" * 60)
print("7. 标记失效 → 管理员清除（别人标的也能清）")
print("=" * 60)
st, d = call("POST", "/api/flag", {"target_id": BASE_ID, "status": "invalid"},
             origin="https://hajimiovo.top")
check("普通人标记失效成功", st == 200 and d.get("status") == "invalid", str(d))

st, d = call("POST", "/api/admin/clearflags", {"target_id": BASE_ID}, token=TOKEN)
check("清除单条失效标记", st == 200 and d.get("removed", 0) >= 1, f"清除 {d.get('removed')} 条")

print()
print("=" * 60)
print("8. 清理测试数据")
print("=" * 60)
st, d = call("POST", "/api/admin/purge", {"target_id": USER_ID}, token=TOKEN)
check("永久删除网友新增", st == 200 and d.get("ok"), str(d))
left = [c for c in changes() if c.get("id") == USER_ID.replace("user|", "")]
check("记录已物理移除", len(left) == 0)

st, d = call("POST", "/api/admin/purge", {"target_id": BASE_ID}, token=TOKEN)
check("基础数据拒绝永久删除", st == 400 and "只能隐藏" in d.get("error", ""), d.get("error", ""))

# 把编辑记录也清掉，恢复原样
call("POST", "/api/admin/edit", {"target_id": BASE_ID, "gun": "M14射手步枪", "build": "",
                                 "tab": "烽火地带", "code": "6L6J4B01SD6JA3I74O3I"}, token=TOKEN)
st, d = call("POST", "/api/admin/clearflags", {}, token=TOKEN)
check("清空全部失效标记", st == 200, f"清除 {d.get('removed')} 条")

print()
print("=" * 60)
print("9. 退出登录")
print("=" * 60)
st, d = call("POST", "/api/admin/logout", {}, token=TOKEN)
check("退出成功", st == 200)
st, d = call("GET", "/api/admin/me", token=TOKEN)
check("退出后令牌失效", st == 401, d.get("error", ""))

print()
print("=" * 60)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
print("=" * 60)
