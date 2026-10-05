"""色板偏差检查（只报告，不拒绝）：成图的主要颜色离所选色板有多远。

确定性像素统计，不调用模型。只有「饱和而且离色板远」的大面积颜色才算偏差——纸色、墨色这类低饱和中性色是画风本身，不计入。
只做报告，结果里固定写 mode=report_only。回测（54 张已知色系的图 × 18 个色板）AUC 约 0.71：能提示明显跑偏，但会漏掉一半、也会误报约 11%，所以不能升级成闸门。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from .. import palette as PL

THRESHOLD_DE = 10.0      # OKLab 距离 ×100；超过它算「离色板远」（2026-10-05 用 54 张已知色系的图回测）
FLAG_SHARE = 0.15        # 偏差面积超过它给出提示；回测：正确色板误报 11%、错误色板检出 48%，所以只能是提示，不能当闸门
CHROMA_FLOOR = 0.04      # OKLCH 彩度低于它视为中性色，不计偏差
MIN_SHARE = 0.05         # 面积不足 5% 的颜色忽略


def _lab(h: str) -> tuple[float, float, float]:
    L, C, H = PL.hex_to_oklch(h)
    return L, C * math.cos(H), C * math.sin(H)


def _de(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return 100 * math.dist(a, b)


def check(image: Path, hexes: list[str], *, colors: int = 8) -> dict:
    if not hexes:
        raise ValueError("色板为空，无法比较")
    img = Image.open(image).convert("RGB")
    img.thumbnail((160, 160))
    q = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: colors * 3]
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(n for n, _ in counts)
    target = [_lab(h) for h in hexes]
    rows, off = [], 0.0
    for n, idx in counts:
        share = n / total
        if share < MIN_SHARE:
            continue
        hx = "#%02X%02X%02X" % tuple(pal[idx * 3: idx * 3 + 3])
        lab = _lab(hx)
        chroma = math.hypot(lab[1], lab[2])
        nearest = min(_de(lab, t) for t in target)
        is_off = chroma >= CHROMA_FLOOR and nearest > THRESHOLD_DE
        off += share if is_off else 0.0
        rows.append({"hex": hx, "share": round(share, 3), "nearest_de": round(nearest, 1), "off_palette": is_off})
    return {"mode": "report_only", "palette": [h.upper() for h in hexes], "dominant": rows,
            "off_palette_share": round(off, 3), "threshold_de": THRESHOLD_DE,
            "flag": off > FLAG_SHARE, "flag_share": FLAG_SHARE}
