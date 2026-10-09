#!/usr/bin/env python3
"""Turn data/codes.json into docs/data.js consumed by docs/index.html.

`docs/` is the GitHub Pages publish root.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "codes.json"
OUT = ROOT / "docs" / "data.js"

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
    notices = []
    for tab in data["tabs"]:
        label = tab["label"]
        for n in tab.get("notices", []):
            if n not in notices:
                notices.append(n)
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
    payload = {
        "source": data["source"],
        "generatedFrom": "GALI的改枪码合集 (腾讯文档)",
        "total": len(records),
        "modes": modes,
        "notices": notices,
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
