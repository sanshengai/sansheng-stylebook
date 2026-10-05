"""局部动效：已通过验收的静态图 + 一个作用区域 → 循环 GIF。只用 Pillow，不重画像素，作用区域以外逐帧完全相同。

模板：glow 光晕脉冲、particles 飘动粒子、breathe 轻微呼吸缩放。按平台预算自动降档（宽度、帧率、颜色数），
降到底仍超预算就报错，不交付超标文件。平台预算见 references/motion.md；没有真机预览前不承诺自动播放。
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

TARGETS = {
    "wechat-article": {"max_w": 720, "budget": 3_000_000, "square": False},
    "wechat-sticker": {"max_w": 240, "budget": 500_000, "square": True},
    "x": {"max_w": 1200, "budget": 15_000_000, "square": False},
}
TEMPLATES = ("glow", "particles", "breathe")
FRAMES = 24
LADDER = [(1.0, 12, 128), (0.85, 12, 96), (0.7, 10, 64), (0.55, 8, 48), (0.45, 8, 32)]


class MotionError(ValueError):
    pass


def _box(size: tuple[int, int], region: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x, y, w, h = region
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1.0001 and y + h <= 1.0001):
        raise MotionError(f"作用区域必须是画面内的比例矩形 (x,y,w,h)：{region}")
    W, H = size
    return round(x * W), round(y * H), round((x + w) * W), round((y + h) * H)


def _glow(base: Image.Image, box, t: float, color=(255, 214, 140)) -> Image.Image:
    w, h = box[2] - box[0], box[3] - box[1]
    mask = Image.radial_gradient("L").resize((w, h))          # 中心黑边缘白
    mask = ImageChops.invert(mask).point(lambda v: int(v * (0.12 + 0.16 * (0.5 + 0.5 * math.sin(2 * math.pi * t)))))
    layer = Image.new("RGB", (w, h), color)
    out = base.copy()
    out.paste(layer, box[:2], mask)
    return out


def _particles(base: Image.Image, box, t: float, seed: int = 7, n: int = 14, color=(255, 240, 200)) -> Image.Image:
    w, h = box[2] - box[0], box[3] - box[1]
    rng = random.Random(seed)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(n):
        x0, phase, r = rng.random() * w, rng.random(), 1.5 + rng.random() * 2.5
        p = (t + phase) % 1.0
        y = h - p * h
        x = x0 + math.sin(2 * math.pi * (p + phase)) * w * 0.03
        a = int(200 * math.sin(math.pi * p))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*color, a))
    out = base.convert("RGBA")
    out.alpha_composite(ov, box[:2])
    return out.convert("RGB")


def _breathe(base: Image.Image, box, t: float, amp: float = 0.018) -> Image.Image:
    w, h = box[2] - box[0], box[3] - box[1]
    s = 1 + amp * math.sin(2 * math.pi * t)
    crop = base.crop(box)
    big = crop.resize((round(w * s), round(h * s)), Image.LANCZOS)
    ox, oy = (big.width - w) // 2, (big.height - h) // 2
    big = big.crop((ox, oy, ox + w, oy + h))
    feather = Image.new("L", (w, h), 0)
    ImageDraw.Draw(feather).rectangle([w * 0.08, h * 0.08, w * 0.92, h * 0.92], fill=255)
    feather = feather.filter(ImageFilter.GaussianBlur(max(2, min(w, h) * 0.06)))
    out = base.copy()
    out.paste(big, box[:2], feather)
    return out


def frames(src: Path, template: str, region: tuple[float, float, float, float], *, count: int = FRAMES) -> list[Image.Image]:
    if template not in TEMPLATES:
        raise MotionError(f"未知动效模板 {template}，可选 {TEMPLATES}")
    base = Image.open(src).convert("RGB")
    box = _box(base.size, region)
    fn = {"glow": _glow, "particles": _particles, "breathe": _breathe}[template]
    return [fn(base, box, i / count) for i in range(count)]


def _fit(img: Image.Image, scale: float, max_w: int, square: bool) -> Image.Image:
    if square:
        side = min(img.size)
        left, top = (img.width - side) // 2, (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side))
    w = min(max_w, round(img.width * scale)) if not square else max(96, round(max_w * scale))
    return img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)


def encode(imgs: list[Image.Image], out: Path, target: str) -> dict:
    if target not in TARGETS:
        raise MotionError(f"未知目标 {target}，可选 {list(TARGETS)}")
    cfg = TARGETS[target]
    last = 0
    for scale, fps, colors in LADDER:
        sized = [_fit(f, scale, cfg["max_w"], cfg["square"]) for f in imgs]
        step = max(1, round(12 / fps))
        picked = sized[::step]
        pal = [f.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in picked]
        out.parent.mkdir(parents=True, exist_ok=True)
        pal[0].save(out, save_all=True, append_images=pal[1:], duration=round(1000 / fps * step), loop=0, optimize=True, disposal=2)
        last = out.stat().st_size
        if last <= cfg["budget"]:
            return {"path": str(out), "bytes": last, "frames": len(pal), "size": list(sized[0].size), "fps": fps, "colors": colors,
                    "target": target, "budget": cfg["budget"]}
    out.unlink(missing_ok=True)
    raise MotionError(f"降到最低档仍超预算：{last} > {cfg['budget']}（{target}）。换更小的作用区域或更简单的模板")


def make(src: Path, template: str, region: tuple[float, float, float, float], target: str, out: Path) -> dict:
    return encode(frames(src, template, region), out, target)
