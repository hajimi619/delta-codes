#!/usr/bin/env python3
"""Turn data/codes.json into docs/delta-codes/data.js consumed by the delta-codes page.

`docs/` is the publish root (Cloudflare Pages + GitHub Pages); each feature lives in its own subfolder.
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "codes.json"
OUT = ROOT / "docs" / "delta-codes" / "data.js"
CONFIG = ROOT / "config.json"
GUN_IMG = ROOT / "data" / "gun-images.json"

OWNER = "哈基米"
SITE_NAME = "三角洲行动 · 改枪码库"
FOOTER_NOTE = "本站为个人整理的改枪码检索工具，与游戏官方无关；改枪码随游戏版本变动，以游戏内实际情况为准。"
SITE_NOTICE = ("改枪码失效通常是同一套码用的人太多触发游戏机制限制，不是改法本身有问题。"
               "遇到失效可以换个方案，或过一段时间再试。")

PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[wW万]")


def norm(s: str) -> str:
    return re.sub(r"[\s\-_]", "", s or "").lower()


def is_subsequence(needle: str, hay: str) -> bool:
    """True when every char of `needle` appears in `hay`, in order."""
    it = iter(hay)
    return all(c in it for c in needle)


def clean_build(label: str, gun: str) -> str:
    """Drop a 'build' cell that is really just the gun's short name.

    The sheet repeats the gun name in the label column for some tabs
    (e.g. 沙漠之鹰 / 沙鹰), which is not a build name.
    """
    if not label:
        return ""
    a, b = norm(label), norm(gun)
    if not a:
        return ""
    if a in b or b in a or is_subsequence(a, b) or is_subsequence(b, a):
        return ""
    return label


def price_of(build: str) -> float | None:
    m = PRICE_RE.search(build or "")
    return float(m.group(1)) if m else None


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    records = []
    for tab in data["tabs"]:
        label = tab["label"]
        for rec in tab["records"]:
            build = clean_build(rec.get("build", ""), rec.get("gun", ""))
            records.append(
                {
                    # a code can appear in more than one tab, so scope the id
                    "id": f"{label}|{rec['code']}",
                    "code": rec["code"],
                    "gun": rec["gun"],
                    "build": build,
                    "mode": rec["mode"],
                    "tab": label,
                    "price": price_of(build),
                }
            )

    modes = []
    for rec in records:
        if rec["tab"] not in modes:
            modes.append(rec["tab"])

    prices = [r["price"] for r in records if r["price"] is not None]
    gun_images = {}
    if GUN_IMG.is_file():
        try:
            gun_images = json.loads(GUN_IMG.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            print(f"[warn] gun-images.json 读不了，枪械图将缺失: {exc}")
    api_base = ""
    if CONFIG.is_file():
        try:
            # 记事本 / PowerShell 存出来的 json 常带 BOM
            api_base = (json.loads(CONFIG.read_text(encoding="utf-8-sig")).get("apiBase") or "").rstrip("/")
        except Exception as exc:
            print(f"[warn] config.json 读不了，按只读模式处理: {exc}")
    payload = {
        "source": data["source"],
        "apiBase": api_base,
        "gunImages": gun_images,
        "siteName": SITE_NAME,
        "footerNote": FOOTER_NOTE,
        "copyright": f"© {datetime.date.today().year} {OWNER}",
        "total": len(records),
        "modes": modes,
        "notices": [SITE_NOTICE],
        "priceMin": int(min(prices)) if prices else 0,
        "priceMax": int(max(prices)) + 1 if prices else 0,
        "withPrice": len(prices),
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "window.DELTA_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}  records={len(records)}  modes={modes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
