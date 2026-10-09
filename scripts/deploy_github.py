#!/usr/bin/env python3
"""Deploy this project to GitHub Pages using only the REST API (no git needed).

Creates (or reuses) a public repo, uploads every project file, then turns on
GitHub Pages with `/docs` as the publish directory.

The token is read from a file and never printed.

    python scripts/deploy_github.py --token-file ../.gh-token --repo delta-codes
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
UA = "dsh-deploy-script"

SKIP_DIRS = {".git", "__pycache__", ".gh-token", "dist"}
SKIP_FILES = {".gh-token", ".DS_Store", "Thumbs.db"}

# GitHub's TLS handshake from mainland China is flaky; retry transient failures.
RETRYABLE = (urllib.error.URLError, ssl.SSLError, socket.timeout, ConnectionError, OSError)


def git_blob_sha(data: bytes) -> str:
    """Git blob hash of `data`, so we can compare against the Contents API sha."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def call(method: str, path: str, token: str, body=None, ok=(200, 201, 204), attempts=6):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", UA)
        req.add_header("Connection", "close")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return resp.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw}
            if e.code in ok:
                return e.code, payload
            # 5xx / rate limit are worth retrying, 4xx are not
            if e.code >= 500 or e.code == 429:
                last = f"HTTP {e.code}"
                time.sleep(2 + 3 * attempt)
                continue
            return e.code, payload
        except RETRYABLE as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 + 3 * attempt)
    return 0, {"message": f"network retries exhausted ({last})"}


def collect_files():
    out = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        out.append((rel, path))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--repo", default="delta-codes")
    ap.add_argument("--description", default="三角洲行动改枪码检索库（静态站，数据来自 GALI 的腾讯文档）")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token_path = Path(args.token_file)
    if not token_path.is_absolute():
        token_path = (ROOT / token_path).resolve()
    if not token_path.is_file():
        print(f"[x] token file not found: {token_path}", file=sys.stderr)
        return 2
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        print("[x] token file is empty", file=sys.stderr)
        return 2

    files = collect_files()
    print(f"files to upload: {len(files)}  ({sum(p.stat().st_size for _, p in files) / 1024:.0f} KB)")
    for rel, path in files:
        print(f"   {rel}  ({path.stat().st_size / 1024:.1f} KB)")
    if args.dry_run:
        return 0

    status, me = call("GET", "/user", token)
    if status != 200:
        print(f"[x] token rejected ({status}): {me.get('message')}", file=sys.stderr)
        return 3
    login = me["login"]
    print(f"[ok] authenticated as {login}")

    # ---- create or reuse the repo ----
    status, repo = call(
        "POST", "/user/repos", token,
        {
            "name": args.repo,
            "description": args.description,
            "private": bool(args.private),
            "has_issues": False,
            "has_wiki": False,
            "has_projects": False,
        },
        ok=(201,),
    )
    if status == 201:
        print(f"[ok] created repo {login}/{args.repo}")
    elif status == 422:
        status2, repo = call("GET", f"/repos/{login}/{args.repo}", token)
        if status2 != 200:
            print(f"[x] repo exists but cannot read it ({status2})", file=sys.stderr)
            return 4
        print(f"[=] repo {login}/{args.repo} already exists, reusing it")
    else:
        print(f"[x] create repo failed ({status}): {repo.get('message')}", file=sys.stderr)
        return 4

    # ---- upload every changed file through the Contents API ----
    branch = repo.get("default_branch") or "main"
    uploaded = skipped = failed = 0
    for rel, path in files:
        posix = rel.as_posix()
        raw = path.read_bytes()
        local_sha = git_blob_sha(raw)

        # existing file -> same blob sha means nothing to do
        st, cur = call("GET", f"/repos/{login}/{args.repo}/contents/{posix}", token, ok=(200, 404))
        if st == 200 and isinstance(cur, dict) and cur.get("sha"):
            if cur["sha"] == local_sha:
                skipped += 1
                continue

        body = {
            "message": f"{'update' if st == 200 else 'add'} {posix}",
            "content": base64.b64encode(raw).decode("ascii"),
        }
        if st == 200 and isinstance(cur, dict) and cur.get("sha"):
            body["sha"] = cur["sha"]
        if repo.get("size") or uploaded:
            body["branch"] = branch

        st, res = call("PUT", f"/repos/{login}/{args.repo}/contents/{posix}", token, body, ok=(200, 201))
        if st in (200, 201):
            uploaded += 1
        elif "branch" in body:
            # empty repo: retry without an explicit branch so GitHub creates it
            body.pop("branch", None)
            st, res = call("PUT", f"/repos/{login}/{args.repo}/contents/{posix}", token, body, ok=(200, 201))
            if st in (200, 201):
                uploaded += 1
            else:
                failed += 1
                print(f"   [!] {posix}: {st} {res.get('message')}")
        else:
            failed += 1
            print(f"   [!] {posix}: {st} {res.get('message')}")
    print(f"[ok] uploaded {uploaded}, unchanged {skipped}" + (f", failed {failed}" if failed else ""))

    # ---- enable Pages from /docs ----
    src = {"source": {"branch": branch, "path": "/docs"}}
    st, res = call("POST", f"/repos/{login}/{args.repo}/pages", token, src, ok=(201, 409))
    if st == 201:
        print("[ok] GitHub Pages enabled (branch=%s, dir=/docs)" % branch)
    elif st == 409:
        st2, res2 = call("PUT", f"/repos/{login}/{args.repo}/pages", token, src, ok=(204,))
        print("[=] Pages already enabled" + ("" if st2 == 204 else f" (update failed: {st2})"))
    else:
        print(f"[!] enabling Pages failed ({st}): {res.get('message')}")
        print("    -> 手动开：仓库 Settings → Pages → Source: Deploy from a branch → %s + /docs" % branch)

    # ---- wait for the first build and report the URL ----
    url = f"https://{login}.github.io/{args.repo}/"
    for attempt in range(10):
        st, info = call("GET", f"/repos/{login}/{args.repo}/pages", token, ok=(200, 404))
        if st == 200:
            url = info.get("html_url") or url
            print(f"     pages status: {info.get('status')}")
            if info.get("status") in ("built", "errored"):
                break
        time.sleep(6)
    print()
    print("=" * 56)
    print("PUBLIC URL :", url)
    print("REPO       :", repo.get("html_url") or f"https://github.com/{login}/{args.repo}")
    print("=" * 56)
    print("首次部署通常 1-2 分钟内生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
