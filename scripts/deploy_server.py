# -*- coding: utf-8 -*-
"""把 docs/ 部署到腾讯云服务器（SFTP 上传，跳过没变的文件）。

用法:
  python scripts/deploy_server.py                 # 上传站点
  python scripts/deploy_server.py --api           # 顺带更新后端并重启服务
  python scripts/deploy_server.py --reload-nginx  # 顺带 reload nginx

依赖: paramiko (pip install paramiko)
"""
import argparse
import hashlib
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    sys.exit("缺少 paramiko，请先: pip install paramiko")

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SERVER_JS = ROOT / "server" / "server.js"

HOST = "119.45.171.242"
USER = "root"
KEY_PATH = Path(r"D:\APP\dswork\.ssh\id_ed25519_hajimiovo")
WEB_ROOT = "/var/www/hajimiovo"
API_DIR = "/opt/hajimiovo-api"

SKIP_NAMES = {"_headers", ".nojekyll", ".DS_Store", "Thumbs.db"}


def connect():
    key = paramiko.Ed25519Key.from_private_key_file(str(KEY_PATH))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=22, username=USER, pkey=key,
              timeout=25, banner_timeout=30, auth_timeout=30)
    return c


def run(c, cmd, timeout=600):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode(errors="replace")
    e = err.read().decode(errors="replace")
    code = out.channel.recv_exit_status()
    return code, o, e


def remote_sizes(sftp, base):
    """返回 {相对路径: 文件大小}"""
    sizes = {}

    def walk(path, rel):
        try:
            entries = sftp.listdir_attr(path)
        except IOError:
            return
        for e in entries:
            r = (rel + "/" + e.filename) if rel else e.filename
            full = path + "/" + e.filename
            if e.st_mode & 0o040000:      # 目录
                sizes[r + "/"] = -1
                walk(full, r)
            else:
                sizes[r] = e.st_size

    walk(base, "")
    return sizes


def mkdirs(sftp, path):
    parts = [p for p in path.split("/") if p]
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except IOError:
            sftp.mkdir(cur)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", action="store_true", help="同时更新后端并重启服务")
    ap.add_argument("--reload-nginx", action="store_true", help="同时 reload nginx")
    args = ap.parse_args()

    c = connect()
    try:
        sftp = c.open_sftp()
        existing = remote_sizes(sftp, WEB_ROOT)
        print(f"远端已有 {sum(1 for v in existing.values() if v >= 0)} 个文件")

        mkdirs(sftp, WEB_ROOT)
        uploaded = skipped = 0
        for f in sorted(DOCS.rglob("*")):
            rel = f.relative_to(DOCS)
            if any(part in SKIP_NAMES or part.startswith(".") for part in rel.parts):
                continue
            key = str(rel).replace("\\", "/")
            target = WEB_ROOT + "/" + key
            if f.is_dir():
                mkdirs(sftp, target)
                continue
            size = f.stat().st_size
            if existing.get(key) == size:
                skipped += 1
                continue
            mkdirs(sftp, str(Path(target).parent).replace("\\", "/"))
            sftp.put(str(f), target)
            uploaded += 1
        print(f"站点: 上传 {uploaded} 个, 跳过 {skipped} 个（大小一致）")

        if args.api:
            mkdirs(sftp, API_DIR)
            sftp.put(str(SERVER_JS), API_DIR + "/server.js")
            print("后端: 已更新 server.js")
            code, o, e = run(c, "systemctl restart hajimiovo-api && sleep 2 && systemctl is-active hajimiovo-api")
            print("后端服务:", o.strip() or e.strip())

        if args.reload_nginx:
            code, o, e = run(c, "nginx -t 2>&1 && systemctl reload nginx && echo reloaded")
            print("nginx:", (o + e).strip())

        # 权限
        run(c, f"chown -R www-data:www-data {WEB_ROOT} && find {WEB_ROOT} -type d -exec chmod 755 {{}} \\; && find {WEB_ROOT} -type f -exec chmod 644 {{}} \\;")

        sftp.close()
    finally:
        c.close()

    print(f"\n[ok] 部署完成  http://{HOST}:8080/")


if __name__ == "__main__":
    main()
