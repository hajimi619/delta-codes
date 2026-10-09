#!/usr/bin/env python3
"""从游戏图鉴截图里裁出每把枪，输出网页用的 WebP + 枪名映射。

输入：assets/gun-screenshots/*.png   （图鉴列表截图，每张若干行，每行一把枪）
输出：docs/img/guns/<编号>.webp
      data/gun-images.json           {枪名: 文件名}

原理
----
图鉴列表每行固定高约 89px，行内左上角是枪名文字（近白色），下方才是枪身。
所以先用「左上角近白文字」定位每一行，行距用等差数列拟合；再取标题下方的
窗口，用**边缘强度**找出枪的轮廓外接框（背景是平滑渐变，几乎没有边缘）。
选中项那圈高亮边框是近白色的细线，会按「贯穿整行/整列 + 亮度 > 200」识别出来
并连同两侧的抗锯齿一并剔除。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

# 每张截图里从上到下的枪名（人工核对过）
NAMES = {
    "01": ["MDR突击步枪", "RM277突击步枪", "AR57突击步枪", "MCX LT突击步枪", "MK47突击步枪", "KC17突击步枪"],
    "02": ["K437突击步枪", "腾龙突击步枪", "AS Val突击步枪", "CAR-15突击步枪", "PTR-32突击步枪", "G3战斗步枪"],
    "03": ["SCAR-H战斗步枪", "AK-12突击步枪", "SG552突击步枪", "M7战斗步枪", "AUG突击步枪", "M16A4突击步枪", "K416突击步枪"],
    "04": ["ASh-12战斗步枪", "AKS-74U突击步枪", "QBZ95-1突击步枪", "AKM突击步枪", "M4A1突击步枪"],
    "05": ["汤姆逊冲锋枪", "MK4冲锋枪", "QCQ171冲锋枪", "MP7冲锋枪", "勇士冲锋枪", "SR-3M紧凑突击步枪", "SMG-45冲锋枪"],
    "06": ["野牛冲锋枪", "UZI冲锋枪", "Vector冲锋枪", "P90冲锋枪", "MP5冲锋枪"],
    "07": ["FS-12霰弹枪", "725双管霰弹枪", "M870霰弹枪", "S12K霰弹枪", "M1014霰弹枪"],
    "08": ["QJB201轻机枪", "M250通用机枪", "M249轻机枪", "PKM通用机枪"],
    "09": ["SVCH精确射手步枪", "杠杆式步枪", "PSG-1射手步枪", "SR9射手步枪", "SR-25射手步枪", "SKS射手步枪"],
    "10": ["M14射手步枪", "SVD狙击步枪", "VSS射手步枪", "Mini-14射手步枪"],
    "11": ["M82狙击步枪", "AWM狙击步枪", "M700狙击步枪", "R93狙击步枪", "SV-98狙击步枪"],
    "12": ["M1911", "G17", "93R", "G18", "沙漠之鹰", ".357左轮", "QSZ92G"],
    "13": ["复合弓"],
}
OVERRIDE = {"13": [29.5]}          # 13 号图里 6.0 那条是高亮边框横线，真标题在 29.5
PITCH_MIN, PITCH_MAX = 84.0, 94.5  # 行距范围
WIN_TOP, WIN_BOT = 6, 76           # 标题下方的取景窗口
X_EDGE = 9                         # 左右各忽略这么多列（高亮竖边框就在这附近）
PAD = 6                            # 外接框外扩
BRIGHT = 200                       # “近白”
EDGE_MIN = 16                      # 边缘强度阈值


def label_candidates(a):
    """找出左上角近白文字所在的行（返回每段文字的中心 y）。"""
    reg = a[:, 8:140, :]
    lum = reg.mean(axis=2)
    sat = reg.max(axis=2) - reg.min(axis=2)
    cnt = ((lum > 140) & (sat < 70)).sum(axis=1)
    runs, start = [], None
    for y in range(a.shape[0]):
        v = cnt[y] >= 3
        if v and start is None:
            start = y
        elif not v and start is not None:
            if y - start >= 3:
                runs.append((start + y) / 2)
            start = None
    if start is not None and a.shape[0] - start >= 3:
        runs.append((start + a.shape[0]) / 2)
    return runs


def best_progression(cands):
    """间距落在 [84,94.5] 的最长等差数列 —— 就是每一行的标题位置。"""
    best = []
    for s in cands:
        chain, cur = [s], s
        for c in cands:
            if c <= cur:
                continue
            if PITCH_MIN <= c - cur <= PITCH_MAX:
                chain.append(c); cur = c
        if len(chain) > len(best):
            best = chain
    return best


def foreground(a, y0, y1):
    """窗口内的前景掩码，用边缘强度找枪的轮廓。"""
    h, w, _ = a.shape
    win = a[y0:y1].astype(float)
    lum = win.mean(axis=2)
    gy, gx = np.gradient(lum)
    m = (np.abs(gx) + np.abs(gy)) > EDGE_MIN
    m[:, :X_EDGE] = False
    m[:, w - X_EDGE:] = False

    def dilate(flags, n=3):
        f = np.asarray(flags).copy()
        for _ in range(n):
            g = f.copy()
            g[1:] |= f[:-1]
            g[:-1] |= f[1:]
            f = g
        return f

    # 高亮边框：近白细线，贯穿整行或整列；两侧抗锯齿也要一起清掉
    bright = lum > BRIGHT
    m[dilate(bright.sum(axis=1) > 0.45 * (w - 2 * X_EDGE))] = False
    m[:, dilate(bright.sum(axis=0) > 0.45 * (y1 - y0))] = False
    return m, lum


def crop_gun(img, a, lum_full, label_y, w, h):
    y0 = max(0, int(round(label_y + WIN_TOP)))
    y1 = min(h, int(round(label_y + WIN_BOT)))
    if y1 - y0 < 12:
        return None
    m, _ = foreground(a, y0, y1)
    ys = np.where(m.any(axis=1))[0]
    xs = np.where(m.any(axis=0))[0]
    if len(ys) == 0 or len(xs) == 0:
        return None
    ymin, ymax = y0 + int(ys.min()), y0 + int(ys.max()) + 1
    cx0, cx1 = max(0, int(xs.min()) - PAD), min(w, int(xs.max()) + PAD + 1)
    cy0, cy1 = ymin, ymax
    # 外扩的边距别把高亮边框又框回来：padding 区只要还有偏亮像素就继续往里收
    while cx0 < int(xs.min()) and lum_full[ymin:ymax, cx0:int(xs.min())].max() > 160:
        cx0 += 1
    while cx1 > int(xs.max()) + 1 and lum_full[ymin:ymax, int(xs.max()) + 1:cx1].max() > 160:
        cx1 -= 1
    while cy0 < ymin and lum_full[cy0:ymin, cx0:cx1].max() > 160:
        cy0 += 1
    while cy1 > ymax and lum_full[ymax:cy1, cx0:cx1].max() > 160:
        cy1 -= 1
    return img.crop((cx0, cy0, cx1, cy1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "assets" / "gun-screenshots"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "img" / "guns"))
    ap.add_argument("--map", default=str(ROOT / "data" / "gun-images.json"))
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    total = 0

    for f in sorted(src.glob("*.png")):
        key = f.name[:2]
        if key not in NAMES:
            continue
        img = Image.open(f).convert("RGB")
        w, h = img.size
        a = np.asarray(img).astype(int)
        lum_full = a.mean(axis=2)
        names = NAMES[key]

        prog = OVERRIDE.get(key) or best_progression(label_candidates(a))
        if len(prog) != len(names):
            if len(prog) >= 2:                       # 缺项/多项时按行距补齐
                pitch = (prog[-1] - prog[0]) / (len(prog) - 1)
                while len(prog) < len(names):
                    prog.append(prog[-1] + pitch)
                while len(prog) > len(names):
                    prog.pop()
            else:
                pitch = h / len(names)
                prog = [pitch * 0.2 + pitch * i for i in range(len(names))]

        for i, ly in enumerate(prog):
            crop = crop_gun(img, a, lum_full, ly, w, h)
            if crop is None or min(crop.size) < 8:
                print(f"   [!] {key}-{i:02d} 裁切失败")
                continue
            name = f"{key}-{i:02d}"
            crop.save(out / f"{name}.webp", quality=88, method=5)
            mapping[names[i]] = f"{name}.webp"
            total += 1

    Path(args.map).parent.mkdir(parents=True, exist_ok=True)
    Path(args.map).write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in out.glob("*.webp"))
    print(f"裁出 {total} 张 -> {out}  （合计 {size/1024:.0f} KB）")
    print(f"映射 -> {args.map}  （{len(mapping)} 把枪）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
