# -*- coding: utf-8 -*-
"""给「基米餐馆」设置进门密码（和服务端同样的 scrypt 参数）。

用法:
  python scripts/set_restaurant.py --password 0813
  python scripts/set_restaurant.py --generate
  python scripts/set_restaurant.py --show
另外可用 --menu 单独更新菜单:
  python scripts/set_restaurant.py --menu
"""
import argparse
import hashlib
import json
import secrets
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    sys.exit("缺少 paramiko，请先: pip install paramiko")

ROOT = Path(__file__).resolve().parent.parent
HOST = "119.45.171.242"
USER = "root"
KEY_PATH = Path(r"D:\APP\dswork\.ssh\id_ed25519_hajimiovo")
GUEST_FILE = "/var/lib/hajimiovo/restaurant.json"
MENU_FILE = "/var/lib/hajimiovo/restaurant-menu.json"
LOCAL_MENU = ROOT / "restaurant" / "menu.json"

SCRYPT_N, SCRYPT_R, SCRYPT_P, DKLEN = 16384, 8, 1, 64


def ssh():
    k = paramiko.Ed25519Key.from_private_key_file(str(KEY_PATH))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=22, username=USER, pkey=k, timeout=25)
    return c


def gen_password(n=6):
    alphabet = "0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password")
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--menu", action="store_true", help="只更新菜单文件")
    args = ap.parse_args()

    c = ssh()
    try:
        def run(cmd, timeout=90):
            _, o, e = c.exec_command(cmd, timeout=timeout)
            return (o.read().decode(errors="replace") + e.read().decode(errors="replace")).strip()

        sftp = c.open_sftp()

        if args.show or args.menu:
            if args.show:
                out = run(f"cat {GUEST_FILE} 2>/dev/null || echo '(未配置)'")
                try:
                    d = json.loads(out)
                    print("餐馆密码已配置，版本:", d.get("ver"), "创建于:", d.get("created_at"))
                except Exception:
                    print(out)
            if args.menu or args.show:
                # 注意：这段命令里不要用 % 格式化，里面的 % 会和 Python 的 % 运算打架
                out = run(
                    "python3 -c \"import json;m=json.load(open('" + MENU_FILE + "'));"
                    "n=sum(len(c['dishes']) for c in m['cuisines']);"
                    "print('菜单: '+str(len(m['cuisines']))+' 个菜系, '+str(n)+' 道菜')\""
                    " 2>/dev/null || echo '(菜单未配置)'")
                print(out)

        # 「只推菜单」必须在上面那个 return 之前判断，否则永远走不到
        if args.menu and not args.password and not args.generate:
            print("\n推送菜单…")
            sftp.put(str(LOCAL_MENU), MENU_FILE)
            print(run(f"chown www-data:www-data {MENU_FILE} && ls -la {MENU_FILE}"))
            print(run("systemctl restart hajimiovo-api && sleep 2 && systemctl is-active hajimiovo-api"))
            print(run("journalctl -u hajimiovo-api -n 6 --no-pager | grep 餐馆 || true"))
            print("\n[ok] 菜单已更新")
            return

        if args.show and not args.password and not args.generate:
            return

        if args.generate:
            password = gen_password()
        elif args.password:
            password = args.password
        else:
            sys.exit("要么给 --password，要么加 --generate")
        if len(password) < 4:
            sys.exit("密码至少 4 位")

        salt = secrets.token_hex(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt.encode("utf-8"),
            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DKLEN,
        ).hex()

        import datetime
        payload = {
            "salt": salt,
            "hash": digest,
            "ver": secrets.token_hex(8),
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }

        with sftp.open(GUEST_FILE + ".new", "wb") as f:
            f.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        sftp.posix_rename(GUEST_FILE + ".new", GUEST_FILE)

        # 顺手把菜单也推上去
        sftp.put(str(LOCAL_MENU), MENU_FILE)

        # 密码变了 -> 所有访客令牌作废
        with sftp.open("/var/lib/hajimiovo/restaurant-tokens.json.new", "wb") as f:
            f.write(b"{}")
        sftp.posix_rename("/var/lib/hajimiovo/restaurant-tokens.json.new",
                          "/var/lib/hajimiovo/restaurant-tokens.json")
        sftp.close()

        print(run("chown -R www-data:www-data /var/lib/hajimiovo && chmod 600 " + GUEST_FILE))
        print(run("systemctl restart hajimiovo-api && sleep 2 && systemctl is-active hajimiovo-api"))
        print(run("journalctl -u hajimiovo-api -n 6 --no-pager | grep 餐馆"))

        print()
        print("=" * 50)
        print("  基米餐馆 进门密码已设置")
        print("=" * 50)
        print(f"  密  码: {password}")
        print("=" * 50)
    finally:
        c.close()


if __name__ == "__main__":
    main()
