#!/usr/bin/env python3
"""把 docs/delta-codes/ 打包成一个自包含的 HTML 文件。

方便：单文件发给别人、离线打开、或传到只支持单文件的地方。
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "delta-codes"
INDEX = DOCS / "index.html"
DATA = DOCS / "data.js"
GUNS = DOCS / "img" / "guns"
OUT = ROOT / "dist" / "delta-codes.html"


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    data = DATA.read_text(encoding="utf-8")

    # 枪械图转成 data URI 内联；必须在主脚本之前定义，否则首屏渲染时取不到
    inline = {}
    for f in sorted(GUNS.glob("*.webp")):
        mime = mimetypes.guess_type(f.name)[0] or "image/webp"
        inline[f.name] = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode("ascii")

    bundle = data
    if inline:
        bundle += "\nwindow.DELTA_INLINE_IMAGES = " + json.dumps(inline, separators=(",", ":")) + ";"

    needle = '<script src="data.js"></script>'
    if needle not in html:
        raise SystemExit(f"anchor not found in {INDEX}: {needle}")
    html = html.replace(needle, "<script>\n" + bundle + "\n</script>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB, 内联 {len(inline)} 张枪械图)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
