"""出图尺寸：按比例算各家模型能接受的生成尺寸；导出像素另由格式预设决定。"""
from __future__ import annotations

from fractions import Fraction


def parse_ratio(ratio: str) -> float:
    w, h = ratio.split(":")
    return float(Fraction(w)) / float(Fraction(h))


MAX_PIXELS, MIN_PIXELS = 8_294_400, 655_360  # gpt-image 系总像素上下限


def gen_size(ratio: str, model: str = "gpt-image-2", long_edge: int = 1536) -> tuple[int, int]:
    """gpt-image 系：宽高须为 16 的倍数、最长边 ≤ 3840、宽高比 ≤ 3:1、总像素在上下限之间。"""
    r = parse_ratio(ratio)
    r = max(1 / 3, min(3, r))
    long_edge = min(long_edge, 3840)
    if r >= 1:
        w, h = long_edge, long_edge / r
    else:
        w, h = long_edge * r, long_edge
    area = w * h
    if area > MAX_PIXELS or area < MIN_PIXELS:
        k = ((MAX_PIXELS if area > MAX_PIXELS else MIN_PIXELS) / area) ** 0.5
        w, h = w * k, h * k
    w16 = (int(w // 16) if area > MAX_PIXELS else int(-(-w // 16))) * 16  # 超上限向下取整，低于下限向上取整
    h16 = (int(h // 16) if area > MAX_PIXELS else int(-(-h // 16))) * 16
    if MIN_PIXELS <= area <= MAX_PIXELS:
        w16, h16 = int(round(w / 16) * 16), int(round(h / 16) * 16)
    while w16 * h16 > MAX_PIXELS:  # 四舍五入可能把面积推出范围，逐级收回
        w16, h16 = (w16 - 16, h16) if w16 >= h16 else (w16, h16 - 16)
    while w16 * h16 < MIN_PIXELS:
        w16, h16 = (w16 + 16, h16) if w16 <= h16 else (w16, h16 + 16)
    while max(w16, h16) > 3 * min(w16, h16):  # 取整后比例可能略超 3:1
        w16, h16 = (w16 - 16, h16) if w16 > h16 else (w16, h16 - 16)
    return w16, h16
