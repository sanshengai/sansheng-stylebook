"""色彩：OKLCH 空间里调深浅与鲜灰；网页与 Skill 用同一套算法，保证预览色块与提示词里的 hex 一致。"""
from __future__ import annotations

import math

from .data import palettes


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _delin(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_oklch(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    r, g, b = (_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.atan2(B, A)


def _oklch_to_rgb(L: float, C: float, H: float) -> tuple[float, float, float]:
    A, B = C * math.cos(H), C * math.sin(H)
    l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
    m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
    s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def _to_hex(rgb) -> str:
    return "#" + "".join(f"{round(min(1, max(0, _delin(min(1, max(0, v))))) * 255):02X}" for v in rgb)


def adjust(hex_color: str, light: int = 0, sat: int = 0) -> str:
    """light: 1 浅 / 0 标准 / -1 深；sat: -1 柔和 / 0 标准 / 1 鲜艳。"""
    if not light and not sat:
        return hex_color.upper()
    cfg = palettes()["adjust"]
    L, C, H = hex_to_oklch(hex_color)
    lo, hi = cfg["lightness_clamp"]
    L = min(hi, max(lo, L + light * cfg["lightness_step"]))
    C *= {-1: cfg["chroma_multiplier"]["柔和"], 0: 1.0, 1: cfg["chroma_multiplier"]["鲜艳"]}[sat]
    rgb = _oklch_to_rgb(L, C, H)
    for _ in range(40):
        if all(-0.0005 <= v <= 1.0005 for v in rgb):
            break
        C *= 0.95
        rgb = _oklch_to_rgb(L, C, H)
    return _to_hex(rgb)


def resolve(family: str, light: int = 0, sat: int = 0, custom: list[str] | None = None) -> list[dict]:
    """返回 [{name, hex}]；family=orig 返回空（沿用样式自己的颜色）。"""
    if family == "orig":
        return []
    if family == "brand":
        if not custom:
            raise ValueError("品牌自定义色系需要至少一个 hex")
        base = [{"name": f"品牌色{i + 1} brand colour {i + 1}", "hex": h.upper() if h.startswith("#") else "#" + h.upper()} for i, h in enumerate(custom)]
    else:
        fams = {p["id"]: p for p in palettes()["palettes"]}
        if family not in fams:
            raise ValueError(f"未知色系 {family}")
        base = fams[family]["colors"]
    return [{"name": c["name"], "hex": adjust(c["hex"], light, sat)} for c in base]


def luma(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def swatch_png(hexes: list[str], *, size: tuple[int, int] = (1024, 256)):
    """无字色带：按顺序等宽排开，内容寻址缓存，同一组颜色永远得到同一个文件。"""
    import hashlib
    import os
    import tempfile
    from pathlib import Path

    from PIL import Image, ImageDraw

    key = hashlib.sha256("|".join(h.upper() for h in hexes).encode()).hexdigest()[:16]
    root = Path(os.environ.get("SANSHENG_IMAGE_CACHE") or Path(tempfile.gettempdir()) / "sansheng-image-cache")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"swatch-{key}.png"
    if not path.exists():
        img = Image.new("RGB", size, "#FFFFFF")
        draw = ImageDraw.Draw(img)
        w = size[0] / max(1, len(hexes))
        for i, h in enumerate(hexes):
            draw.rectangle([round(i * w), 0, round((i + 1) * w), size[1]], fill=h)
        tmp = path.with_suffix(".tmp")
        img.save(tmp, "PNG")
        tmp.replace(path)
    return path
