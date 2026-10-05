"""局部动效：已通过验收的静态图 + 一个作用区域 → 循环 GIF。只用 Pillow，不重画像素，作用区域以外逐帧完全相同。

模板：glow 光晕脉冲、particles 飘动粒子、breathe 轻微呼吸缩放、labels 标签依次淡入（先抹掉标签区域再逐个还原）。
输出 GIF 或动画 WebP（网页展示用）。按平台预算自动降档（宽度、帧率、颜色数/画质），
降到底仍超预算就报错，不交付超标文件。平台预算见 references/motion.md；没有真机预览前不承诺自动播放。
"""
from __future__ import annotations

import math
import random
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

TARGETS = {
    "wechat-article": {"max_w": 720, "budget": 3_000_000, "square": False},
    "wechat-sticker": {"max_w": 240, "budget": 500_000, "square": True},
    "x": {"max_w": 1200, "budget": 15_000_000, "square": False},
    "web": {"max_w": 640, "budget": 1_500_000, "square": False, "edge": True},   # 网页展示：长边 640
    "web-small": {"max_w": 320, "budget": 400_000, "square": False, "edge": True},   # 网页小图（表情包）：长边 320
}
TEMPLATES = ("glow", "particles", "breathe", "labels")
FORMATS = ("gif", "webp")
FRAMES = 24
SRC_FPS = 12                                   # 出帧的名义帧率；降档时按步长抽帧，时长按真实间隔算
LADDER = [(1.0, 12, 128), (0.85, 12, 96), (0.7, 10, 64), (0.55, 8, 48), (0.45, 8, 32)]
WEBP_QUALITY = {128: 80, 96: 72, 64: 64, 48: 55, 32: 45}
LABEL_LEAD, LABEL_FADE, LABEL_GAP, LABEL_HOLD = 0.4, 0.4, 0.25, 1.5   # 秒：起始静止、单个淡入、相邻间隔、全部出现后停留


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


def _erase(base: Image.Image, box) -> Image.Image:
    """用方框外一圈的颜色按行、按列插值填平，再加与周边相当的细颗粒；方框外不动。"""
    arr = np.asarray(base, dtype=np.float32)
    H, W = arr.shape[:2]
    x0, y0, x1, y1 = box
    m = max(3, round(min(x1 - x0, y1 - y0) * 0.08))
    edges = {}
    if x0 - m >= 0:
        edges["l"] = np.median(arr[y0:y1, x0 - m:x0], axis=1)
    if x1 + m <= W:
        edges["r"] = np.median(arr[y0:y1, x1:x1 + m], axis=1)
    if y0 - m >= 0:
        edges["t"] = np.median(arr[y0 - m:y0, x0:x1], axis=0)
    if y1 + m <= H:
        edges["b"] = np.median(arr[y1:y1 + m, x0:x1], axis=0)
    if not edges:
        return base.copy()
    h, w = y1 - y0, x1 - x0
    parts = []
    if "l" in edges and "r" in edges:
        k = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
        left, right = edges["l"], edges["r"]
        med = np.median(np.concatenate([e.reshape(-1, 3) for e in edges.values()]), axis=0)
        clash = np.abs(left - right).mean(axis=1) > 48     # 两侧颜色差太大（一侧撞上了插画元素）：取更接近整圈中位色的一侧
        near_left = np.abs(left - med).sum(axis=1) <= np.abs(right - med).sum(axis=1)
        both = np.where(near_left[:, None], left, right)
        left, right = np.where(clash[:, None], both, left), np.where(clash[:, None], both, right)
        parts.append(left[:, None, :] * (1 - k) + right[:, None, :] * k)
    if not parts and "t" in edges and "b" in edges:      # 左右可参考时只按行插值，避免上下边缘的字笔画污染
        k = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        parts.append(edges["t"][None, :, :] * (1 - k) + edges["b"][None, :, :] * k)
    if not parts:                                   # 只有一侧可参考：沿该侧外推
        side = next(iter(edges.values()))
        parts.append(np.broadcast_to(side[:, None, :] if side.shape[0] == h else side[None, :, :], (h, w, 3)))
    fill = np.mean(parts, axis=0)
    ring = np.concatenate([e.reshape(-1, 3) for e in edges.values()])
    sigma = float(np.clip(ring.std(axis=0).mean() * 0.5, 0, 3))
    rng = np.random.default_rng(7)
    fill = fill + rng.normal(0, sigma, (h, w, 1)).astype(np.float32) if sigma else fill
    out = np.array(arr)
    out[y0:y1, x0:x1] = np.clip(fill, 0, 255)
    return Image.fromarray(out.astype(np.uint8))


def _smooth(a: float) -> float:
    a = min(1.0, max(0.0, a))
    return a * a * (3 - 2 * a)


def _labels(base: Image.Image, groups: list[list[tuple[int, int, int, int]]]) -> list[Image.Image]:
    """groups：每组是同时出现的一个或几个方框，组之间按顺序依次淡入。"""
    erased = base
    for g in groups:
        for b in g:
            erased = _erase(erased, b)
    total = LABEL_LEAD + (len(groups) - 1) * (LABEL_FADE + LABEL_GAP) + LABEL_FADE + LABEL_HOLD
    out = []
    for f in range(math.ceil(total * SRC_FPS)):
        t = f / SRC_FPS
        frame = erased.copy()
        for i, g in enumerate(groups):
            a = _smooth((t - LABEL_LEAD - i * (LABEL_FADE + LABEL_GAP)) / LABEL_FADE)
            for b in g:
                if a >= 1:
                    frame.paste(base.crop(b), b[:2])
                elif a > 0:
                    frame.paste(Image.blend(erased.crop(b), base.crop(b), a), b[:2])
        out.append(frame)
    return out


def boxes_from_layout(path: Path) -> list[tuple[float, float, float, float]]:
    """读 overlay 排字配置（见 overlay.py 的 items[].box），按 items 顺序当作出现顺序。"""
    from .textspec import overlay_items
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    boxes = [tuple(float(v) for v in item["box"]) for item in overlay_items(spec) if isinstance(item.get("box"), list)]
    if not boxes:
        raise MotionError(f"排字配置里没有可用的文字框：{path}")
    return boxes


def _label_boxes(size, regions) -> list[list[tuple[int, int, int, int]]]:
    """regions 每项是一个 (x,y,w,h)，或同时出现的若干个 [(x,y,w,h), ...]；返回像素框分组。"""
    if not isinstance(regions, (list, tuple)) or not regions:
        raise MotionError("labels 需要至少一个标签框，格式为 [(x,y,w,h), ...]")
    groups = []
    for r in regions:
        if not isinstance(r, (list, tuple)) or not r:
            raise MotionError(f"标签框格式不对：{r}")
        items = [r] if all(isinstance(v, (int, float)) for v in r) else list(r)
        groups.append([_box(size, tuple(x)) for x in items])
    flat = [b for g in groups for b in g]
    for i, a in enumerate(flat):
        for b in flat[:i]:
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                raise MotionError("标签框不能互相重叠")
    return groups


def frames(src: Path, template: str, region, *, count: int = FRAMES, color: tuple[int, int, int] | None = None) -> list[Image.Image]:
    """region：单个 (x,y,w,h)；labels 模板为按出现顺序排列的 [(x,y,w,h), ...]（同时出现的几个框放进一个子列表）。color 只对 glow、particles 生效。"""
    if template not in TEMPLATES:
        raise MotionError(f"未知动效模板 {template}，可选 {TEMPLATES}")
    base = Image.open(src).convert("RGB")
    if template == "labels":
        return _labels(base, _label_boxes(base.size, region))
    box = _box(base.size, region)
    fn = {"glow": _glow, "particles": _particles, "breathe": _breathe}[template]
    kw = {"color": tuple(color)} if color and template in ("glow", "particles") else {}
    return [fn(base, box, i / count, **kw) for i in range(count)]


def _fit(img: Image.Image, scale: float, max_w: int, square: bool, edge: bool = False) -> Image.Image:
    if square:
        side = min(img.size)
        left, top = (img.width - side) // 2, (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side))
    if edge:                                       # max_w 当作长边上限
        w = max(96, round(img.width * min(1.0, max_w / max(img.size)) * scale))
    else:
        w = min(max_w, round(img.width * scale)) if not square else max(96, round(max_w * scale))
    return img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)


def _shared_palette(sized: list[Image.Image], colors: int) -> Image.Image:
    """全部帧共用一张调色板：不动的区域逐帧同色，不闪，也让 GIF 只记录变化部分。"""
    pick = sized[:: max(1, len(sized) // 6)][:6]
    strip = Image.new("RGB", (pick[0].width, pick[0].height * len(pick)))
    for i, f in enumerate(pick):
        strip.paste(f, (0, i * f.height))
    return strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def encode(imgs: list[Image.Image], out: Path, target: str, fmt: str | None = None, loop: bool = True) -> dict:
    """fmt：gif 或 webp，缺省按输出后缀；loop=False 则播完停在最后一帧。"""
    if target not in TARGETS:
        raise MotionError(f"未知目标 {target}，可选 {list(TARGETS)}")
    fmt = fmt or ("webp" if out.suffix.lower() == ".webp" else "gif")
    if fmt not in FORMATS:
        raise MotionError(f"未知输出格式 {fmt}，可选 {FORMATS}")
    cfg = TARGETS[target]
    last = 0
    for scale, fps, colors in LADDER:
        sized = [_fit(f, scale, cfg["max_w"], cfg["square"], cfg.get("edge", False)) for f in imgs]
        step = max(1, round(SRC_FPS / fps))
        picked, durations = [], []
        for f in sized[::step]:                    # 相邻完全相同的帧合并成一帧，累加时长
            if picked and f.tobytes() == picked[-1].tobytes():
                durations[-1] += round(1000 * step / SRC_FPS)
            else:
                picked.append(f)
                durations.append(round(1000 * step / SRC_FPS))
        out.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "gif":
            pal_img = _shared_palette(picked, colors)
            pal = [f.quantize(palette=pal_img, dither=Image.Dither.NONE) for f in picked]
            kw = {"loop": 0} if loop else {}
            pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, optimize=True, **kw)
        else:
            picked[0].save(out, save_all=True, append_images=picked[1:], duration=durations, loop=0 if loop else 1,
                           quality=WEBP_QUALITY[colors], method=6)
        last = out.stat().st_size
        if last <= cfg["budget"]:
            with Image.open(out) as saved:         # WebP 编码器会再合并有损后完全相同的相邻帧，以文件实际帧数为准
                n_frames = getattr(saved, "n_frames", 1)
            return {"path": str(out), "bytes": last, "frames": n_frames, "size": list(sized[0].size), "fps": fps,
                    "colors": colors, "format": fmt, "loop": loop, "target": target, "budget": cfg["budget"]}
    out.unlink(missing_ok=True)
    raise MotionError(f"降到最低档仍超预算：{last} > {cfg['budget']}（{target}）。换更小的作用区域或更简单的模板")


def make(src: Path, template: str, region, target: str, out: Path, fmt: str | None = None, loop: bool = True,
         color: tuple[int, int, int] | None = None) -> dict:
    return encode(frames(src, template, region, color=color), out, target, fmt, loop)
