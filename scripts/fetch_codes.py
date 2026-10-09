#!/usr/bin/env python3
"""Scrape GALI's Delta Force (三角洲行动) gun-mod code sheet from Tencent Docs.

Tencent Docs serves a zlib-compressed protobuf blob for each sheet. There is no
official API, so this module:

  1. calls /dop-api/opendoc for a tab
  2. walks the JSON envelope down to initialAttributedText.text[0].block_datas[*].related_sheet
  3. zlib-inflates it and reads the protobuf wire format generically
  4. recovers the cell grid from  sheet.r0.f19[0] = {f3: meta, f5: values, f6: cells}

Cell records are {f1: row, f2: col, f3: {f2: {f1: valueIndex}, f4: {f1: styleIndex}}}.
Rows/cols are 1-based; the shared value list is sheet.r0.f5.f1.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.request
import zlib
from pathlib import Path

DOC_ID = "DUmZJeER0dmNTSVRP"
DOC_URL = f"https://docs.qq.com/sheet/{DOC_ID}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
# tab id -> (display name, game mode)
TABS = [
    ("BB08J2", "烽火地带", "烽火地带"),
    ("bxp5c6", "全面战场", "全面战场"),
    ("bav4en", "烽火高操速T0", "烽火地带"),
    ("3anshx", "黑潮爆破", "黑潮爆破"),
]
CODE_RE = re.compile(r"^(?P<gun>.{1,24}?)-(?P<mode>[^-]{2,8})-(?P<code>[0-9A-Za-z]{12,})$")


# --------------------------------------------------------------------------- #
# generic protobuf wire reader
# --------------------------------------------------------------------------- #
def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = 0
    out = 0
    while True:
        b = buf[i]
        i += 1
        out |= (b & 0x7F) << shift
        if not b & 0x80:
            return out, i
        shift += 7


def _as_text(chunk: bytes) -> str | None:
    try:
        s = chunk.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 9 or (13 < ord(c) < 32) or ord(c) == 127 for c in s):
        return None
    return s


def pb_parse(buf: bytes, depth: int = 0, max_depth: int = 16) -> list:
    """Strict reader: raises unless the whole buffer is valid protobuf."""
    fields: list = []
    i, n = 0, len(buf)
    while i < n:
        key, i = _read_varint(buf, i)
        fno, wire = key >> 3, key & 7
        if fno == 0:
            raise ValueError("zero field number")
        if wire == 0:
            val, i = _read_varint(buf, i)
            fields.append((fno, 0, val))
        elif wire == 1:
            if i + 8 > n:
                raise ValueError("truncated fixed64")
            fields.append((fno, 1, buf[i:i + 8]))
            i += 8
        elif wire == 2:
            ln, i = _read_varint(buf, i)
            if i + ln > n:
                raise ValueError("truncated length-delimited")
            chunk = buf[i:i + ln]
            i += ln
            sub = None
            if depth < max_depth:
                try:
                    sub = pb_parse(chunk, depth + 1, max_depth)
                except Exception:
                    sub = None
                if not sub:
                    sub = None
            if sub is not None:
                fields.append((fno, 2, ("msg", sub)))
            else:
                txt = _as_text(chunk)
                fields.append((fno, 2, ("str", txt) if txt is not None else ("bin", chunk)))
        elif wire == 5:
            if i + 4 > n:
                raise ValueError("truncated fixed32")
            fields.append((fno, 5, buf[i:i + 4]))
            i += 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
    return fields


def pb_vals(fields: list, fno: int) -> list:
    return [v for f, _w, v in fields if f == fno]


def pb_unwrap(v):
    return v[1] if isinstance(v, tuple) else v


def pb_text(v) -> str | None:
    if isinstance(v, tuple):
        if v[0] == "str":
            return v[1]
        if v[0] == "msg":
            return "".join(x for x in (pb_text(y) for y in pb_vals(v[1], 1)) if x)
    return None


# --------------------------------------------------------------------------- #
# Tencent Docs plumbing
# --------------------------------------------------------------------------- #
def fetch_tab(tab: str, timeout: int = 60) -> str:
    url = (
        "https://docs.qq.com/dop-api/opendoc?"
        f"tab={tab}&u=&noEscape=1&enableSmartsheetSplit=1"
        "&startrow=0&endrow=60&needSheetState=1&sliceStates=1"
        "&block_end_col=31&block_end_row=255&block_start_col=0&block_start_row=0"
        f"&id={DOC_ID}&normal=1&outformat=1&wb=1&nowb=0"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": DOC_URL,
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig")


def parse_sheet(doc: str):
    """Yield (sheet_id, row_count, col_count, values, cells) per data block."""
    env = json.loads(doc)
    text = env["clientVars"]["collab_client_vars"]["initialAttributedText"]["text"]
    for block in text:
        for bd in block.get("block_datas", []):
            rel = bd.get("related_sheet")
            if not rel:
                continue
            tree = pb_parse(zlib.decompress(base64.b64decode(rel)))
            top = pb_unwrap(pb_vals(tree, 1)[0])
            for entry in pb_vals(top, 5):
                msg = pb_unwrap(entry)
                if not isinstance(msg, list):
                    continue
                for one in pb_vals(msg, 19):
                    r0 = pb_unwrap(one)
                    meta = pb_unwrap(pb_vals(r0, 3)[0])
                    sheet_id = pb_text(pb_vals(meta, 1)[0])
                    rows = pb_vals(meta, 4)[0]
                    cols = pb_vals(meta, 5)[0]
                    shared = []
                    for e in pb_vals(pb_unwrap(pb_vals(r0, 5)[0]), 1):
                        f = pb_unwrap(e)
                        shared.append(pb_text(pb_vals(f, 1)[0]) if pb_vals(f, 1) else "")
                    yield sheet_id, rows, cols, shared, pb_vals(r0, 6)


def build_grid(shared: list[str], cells: list) -> tuple[dict, list[str]]:
    """Return ({(row, col): text}, merged_cell_texts)."""
    grid: dict[tuple[int, int], str] = {}
    merged: list[str] = []
    for cell in cells:
        fields = pb_unwrap(cell)
        row = col = None
        f3 = None
        for fno, _w, val in fields:
            if fno == 1:
                row = val
            elif fno == 2:
                col = val
            elif fno == 3 and isinstance(val, tuple):
                f3 = val[1]
        if f3 is None:
            continue
        inner = {fno: val for fno, _w, val in f3}
        idx = None
        holder = inner.get(2)
        if isinstance(holder, tuple) and holder[0] == "msg":
            got = pb_vals(holder[1], 1)
            if got:
                idx = got[0]
        if not isinstance(idx, int) or not (0 <= idx < len(shared)):
            continue
        text = shared[idx]
        if not text:
            continue
        if row is None or col is None:
            merged.append(text)
            continue
        grid[(row, col)] = text
    return grid, merged


def extract_tab(tab: str) -> dict:
    """Pull every gun-mod code out of one tab."""
    grid = {}
    merged = []
    sheet_id = tab
    rows = cols = 0
    for sheet_id, rows, cols, shared, cells in parse_sheet(fetch_tab(tab)):
        grid, merged = build_grid(shared, cells)
        break

    records: list[dict] = []
    seen: set[str] = set()
    for (r, c), text in sorted(grid.items()):
        m = CODE_RE.match(text.strip())
        if not m:
            continue
        code = m.group("code")
        if code in seen:
            continue
        seen.add(code)
        # label = nearest non-empty cell to the left (build/price/notes column)
        label = ""
        for back in (1, 2):
            cand = grid.get((r, c - back))
            if cand and not CODE_RE.match(cand.strip()):
                label = cand.strip()
                break
        records.append(
            {
                "code": code,
                "gun": m.group("gun").strip(),
                "mode": m.group("mode").strip(),
                "build": label,
                "full": text.strip(),
                "row": r,
                "col": c,
                "tab": tab,
            }
        )

    # propagate the gun name down rows where the sheet only shows it once
    last_gun = ""
    for rec in records:
        if rec["gun"]:
            last_gun = rec["gun"]
        elif last_gun:
            rec["gun"] = last_gun
    return {
        "tab": tab,
        "sheetId": sheet_id,
        "rows": rows,
        "cols": cols,
        "notices": _clean_notices(merged),
        "records": records,
    }


def _clean_notices(merged: list[str]) -> list[str]:
    seen, out = set(), []
    for text in merged:
        t = text.strip()
        if len(t) < 4 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/codes.json")
    args = ap.parse_args()

    payload = {"source": DOC_URL, "tabs": []}
    total = 0
    for tab, label, _mode in TABS:
        try:
            data = extract_tab(tab)
        except Exception as exc:  # keep going; report per tab
            print(f"[fail] {label} ({tab}): {exc}", file=sys.stderr)
            continue
        data["label"] = label
        payload["tabs"].append(data)
        n = len(data["records"])
        total += n
        print(f"[ok] {label:16s} tab={tab}  codes={n:4d}  sheet={data['sheetId']}")
    payload["total"] = total

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"total codes: {total} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
