#!/usr/bin/env python3
"""Bundle docs/index.html + docs/data.js into one self-contained HTML file.

Useful for hosting on single-file services, mailing, or offline sharing.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "docs" / "index.html"
DATA = ROOT / "docs" / "data.js"
OUT = ROOT / "dist" / "delta-codes.html"


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    data = DATA.read_text(encoding="utf-8")
    needle = '<script src="data.js"></script>'
    if needle not in html:
        raise SystemExit(f"anchor not found in {INDEX}: {needle}")
    html = html.replace(needle, "<script>\n" + data + "\n</script>")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
