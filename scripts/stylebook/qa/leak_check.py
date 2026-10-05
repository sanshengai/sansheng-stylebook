"""串味检查（只报告）：参考图里的局部有没有被原样搬进成图。

取参考图里纹理最丰富的几块，在成图里做多尺度归一化互相关；某一块在成图里找到几乎一样的位置（相关系数很高），
说明参考图的内容被抄进来了。只能发现「原样搬运」，发现不了「换了个姿势的同一个人物」，后者仍靠看图验收。
纯 numpy，无需 OpenCV。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

WORK_W = 384          # 统一工作宽度
PATCH = 56            # 参考块边长（工作像素）
PATCHES = 30
SCALES = (0.7, 0.85, 1.0, 1.2, 1.4)
FLAG_NCC = 0.80       # 回测：24 张人工贴块的成图检出 21 张，20 张真实成图 0 误报（references/qa.md）


def _gray(path: Path, width: int = WORK_W) -> np.ndarray:
    im = Image.open(path).convert("L")
    h = max(8, round(im.height * width / im.width))
    im = im.resize((width, h), Image.LANCZOS)
    low = np.asarray(im.filter(ImageFilter.GaussianBlur(6)), dtype=np.float64)
    return np.asarray(im, dtype=np.float64) - low   # 高通：去掉纸色与大块明暗，只比形状与笔画


def _best_patches(ref: np.ndarray) -> list[tuple[int, int, np.ndarray]]:
    H, W = ref.shape
    cands = []
    step = PATCH // 2
    for y in range(0, H - PATCH + 1, step):
        for x in range(0, W - PATCH + 1, step):
            p = ref[y:y + PATCH, x:x + PATCH]
            cands.append((float(p.std()), y, x))
    cands.sort(reverse=True)
    picked: list[tuple[int, int, np.ndarray]] = []
    for sd, y, x in cands:
        if sd < 6:
            break
        if all(abs(y - py) >= PATCH or abs(x - px) >= PATCH for py, px, _ in picked):
            picked.append((y, x, ref[y:y + PATCH, x:x + PATCH]))
        if len(picked) == PATCHES:
            break
    return picked


def _ncc_max(img: np.ndarray, tpl: np.ndarray) -> float:
    th, tw = tpl.shape
    H, W = img.shape
    if H < th or W < tw:
        return 0.0
    t = tpl - tpl.mean()
    tn = np.sqrt((t * t).sum())
    if tn < 1e-6:
        return 0.0
    fs = (H + th, W + tw)
    corr = np.fft.irfft2(np.fft.rfft2(img, fs) * np.conj(np.fft.rfft2(t, fs)), fs)[:H - th + 1, :W - tw + 1]
    ii = np.pad(img, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    ii2 = np.pad(img * img, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def box(a):
        return a[th:, tw:] - a[:-th, tw:] - a[th:, :-tw] + a[:-th, :-tw]

    n = th * tw
    s1, s2 = box(ii)[:H - th + 1, :W - tw + 1], box(ii2)[:H - th + 1, :W - tw + 1]
    var = np.maximum(s2 - s1 * s1 / n, 1e-9)
    ncc = corr / (np.sqrt(var) * tn)
    return float(np.clip(ncc.max(), -1, 1))


def check(output: Path, reference: Path) -> dict:
    ref = _gray(reference)
    out = _gray(output)
    patches = _best_patches(ref)
    if not patches:
        raise ValueError("参考图几乎没有纹理，无法做串味检查")
    rows = []
    for y, x, p in patches:
        best = 0.0
        for s in SCALES:
            tpl = np.asarray(Image.fromarray(p.astype(np.float32), mode="F").resize((max(8, round(PATCH * s)),) * 2, Image.BILINEAR), dtype=np.float64)
            best = max(best, _ncc_max(out, tpl))
        rows.append({"patch": [x, y], "ncc": round(best, 3)})
    top = max(r["ncc"] for r in rows)
    return {"mode": "report_only", "patches": rows, "max_ncc": top, "flag": top >= FLAG_NCC, "flag_ncc": FLAG_NCC}
