# -*- coding: utf-8 -*-
"""在服务器上设置管理员账号（用户名 + 密码）。

密码用 Node 的 scrypt 同样的参数做哈希（N=16384, r=8, p=1, dklen=64），
明文不落盘、不进日志。

用法:
  python scripts/set_admin.py --user hajimi                # 交互式输入密码
  python scripts/set_admin.py --user hajimi --password xxx # 直接给（注意 shell 历史）
  python scripts/set_admin.py --user hajimi --generate     # 随机生成一个强密码并打印
  python scripts/set_admin.py --show                       # 只看当前配置（不显示密码）
"""
import argparse
import getpass
import hashlib
import json
import secrets
import string
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    sys.exit("缺少 paramiko，请先: pip install paramiko")

HOST = "119.45.171.242"
USER = "root"
KEY_PATH = Path(r"D:\APP\dswork\.ssh\id_ed25519_hajimiovo")
ADMIN_FILE = "/var/lib/hajimiovo/admin.json"

SCRYPT_N, SCRYPT_R, SCRYPT_P, DKLEN = 16384, 8, 1, 64


def ssh():
    k = paramiko.Ed25519Key.from_private_key_file(str(KEY_PATH))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=22, username=USER, pkey=k, timeout=25)
    return c


def gen_password(n=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", help="管理员用户名")
    ap.add_argument("--password", help="管理员密码")
    ap.add_argument("--generate", action="store_true", help="随机生成强密码")
    ap.add_argument("--show", action="store_true", help="只看当前配置")
    args = ap.parse_args()

    c = ssh()
    try:
        def run(cmd, timeout=60):
            _, o, e = c.exec_command(cmd, timeout=timeout)
            return (o.read().decode(errors="replace") + e.read().decode(errors="replace")).strip()

        if args.show:
            out = run(f"cat {ADMIN_FILE} 2>/dev/null || echo '(未配置)'")
            try:
                d = json.loads(out)
                print("用户名:", d.get("username"))
                print("创建于:", d.get("created_at"))
                print("密码哈希:", (d.get("hash") or "")[:16] + "…（不可逆）")
            except Exception:
                print(out)
            return

        if not args.user:
            sys.exit("请用 --user 指定用户名")

        if args.generate:
            password = gen_password()
        elif args.password:
            password = args.password
        else:
            password = getpass.getpass("请输入管理员密码: ")
            again = getpass.getpass("再输一次确认: ")
            if password != again:
                sys.exit("两次输入不一致")
        if len(password) < 8:
            sys.exit("密码至少 8 位")

        salt = secrets.token_hex(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt.encode("utf-8"),
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DKLEN,
        ).hex()

        payload = {
            "username": args.user,
            "salt": salt,
            "hash": digest,
            "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }

        sftp = c.open_sftp()
        try:
            with sftp.open(ADMIN_FILE + ".new", "wb") as f:
                f.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            sftp.posix_rename(ADMIN_FILE + ".new", ADMIN_FILE)
        finally:
            sftp.close()

        print(run(f"chown www-data:www-data {ADMIN_FILE} && chmod 600 {ADMIN_FILE} && ls -la {ADMIN_FILE}"))
        print(run("systemctl restart hajimiovo-api && sleep 2 && systemctl is-active hajimiovo-api"))
        print(run('curl -s --max-time 5 http://127.0.0.1:8080/api/health'))

        print()
        print("=" * 50)
        print("  管理员账号已设置")
        print("=" * 50)
        print(f"  用户名: {args.user}")
        print(f"  密  码: {password}")
        print("=" * 50)
        print("  ⚠️ 记下来。密码只显示这一次，服务器上存的是哈希，找不回来。")
    finally:
        c.close()


if __name__ == "__main__":
    main()
