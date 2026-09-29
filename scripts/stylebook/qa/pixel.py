"""像素级确定性测量（需要 Pillow）。"""
from __future__ import annotations

from pathlib import Path


def check_paper_margin(image: Path, *, min_margin: float) -> dict:
    """预检暖色纸底上的墨线与明显色块；浅色细节仍须看图。"""
    from PIL import Image

    with Image.open(image) as source:
        rgb = source.convert("RGB")
        rgb.thumbnail((1024, 1024))
        w, h = rgb.size
        raw = rgb.tobytes()
    left, top, right, bottom = w, h, -1, -1
    for index in range(0, len(raw), 3):
        r, g, b = raw[index:index + 3]
        if min(r, g, b) >= 120 and max(r, g, b) - min(r, g, b) <= 60:
            continue
        pixel = index // 3
        x, y = pixel % w, pixel // w
        left, top = min(left, x), min(top, y)
        right, bottom = max(right, x), max(bottom, y)
    if right < 0:
        return {"passed": False, "size": [w, h], "margins": None,
                "problems": ["没有可检测的墨线或明显色块，空图不能通过纸面留白验收"]}
    exact = {"left": left / w, "right": (w - 1 - right) / w,
             "top": top / h, "bottom": (h - 1 - bottom) / h}
    problems = [f"{side} 纸面边距 {value:.1%}，低于 {min_margin:.0%}"
                for side, value in exact.items() if value < min_margin]
    return {"passed": not problems, "size": [w, h],
            "margins": {side: round(value, 4) for side, value in exact.items()},
            "problems": problems,
            "scope": "只预检黑色墨线与明显色块；浅色细节、整体留白和手机可读性仍须实际看图"}


def measure(image: Path, dark_luma: float = 96, white_luma: float = 235) -> dict:
    from PIL import Image  # 可选依赖：只有验收与切图需要
    source = Image.open(image)
    alpha = source.convert("RGBA").getchannel("A") if ("A" in source.getbands() or "transparency" in source.info) else None
    alpha_nonopaque_pixels = 0
    if alpha is not None:
        hist = alpha.histogram()
        alpha_nonopaque_pixels = sum(hist[:255])
    im = source.convert("RGB")
    im.thumbnail((512, 512))
    raw = im.tobytes()  # 兼容新旧 Pillow（getdata 将在 Pillow 14 移除）
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    n = len(px)
    lumas = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in px]
    sats = []
    for r, g, b in px:
        mx, mn = max(r, g, b), min(r, g, b)
        sats.append(0 if mx == 0 else (mx - mn) / mx)
    return {
        "mean_luma": round(sum(lumas) / n, 1),
        "dark_ratio": round(sum(1 for x in lumas if x < dark_luma) / n, 4),
        "white_ratio": round(sum(1 for x in lumas if x > white_luma) / n, 4),
        "mean_saturation": round(sum(sats) / n, 4),
        "alpha_nonopaque_pixels": alpha_nonopaque_pixels,
        "alpha_nonopaque_ratio": round(alpha_nonopaque_pixels / (source.width * source.height), 4),
        "size": list(source.size),
    }


def check_pixels(m: dict, th: dict) -> list[str]:
    out = []
    if "mean_luma_min" in th and m["mean_luma"] < th["mean_luma_min"]:
        out.append(f"整体偏暗：平均明度 {m['mean_luma']} < {th['mean_luma_min']}")
    if "mean_luma_max" in th and m["mean_luma"] > th["mean_luma_max"]:
        out.append(f"整体偏亮：平均明度 {m['mean_luma']} > {th['mean_luma_max']}")
    if "dark_pixel_ratio_max" in th and m["dark_ratio"] > th["dark_pixel_ratio_max"]:
        out.append(f"暗部过多：{m['dark_ratio']:.1%} > {th['dark_pixel_ratio_max']:.0%}")
    if "mean_saturation_max" in th and m["mean_saturation"] > th["mean_saturation_max"]:
        out.append(f"颜色过艳：平均饱和度 {m['mean_saturation']} > {th['mean_saturation_max']}")
    if "mean_saturation_min" in th and m["mean_saturation"] < th["mean_saturation_min"]:
        out.append(f"颜色过灰：平均饱和度 {m['mean_saturation']} < {th['mean_saturation_min']}")
    if "white_ratio_min" in th and m["white_ratio"] < th["white_ratio_min"]:
        out.append(f"留白不足：{m['white_ratio']:.1%} < {th['white_ratio_min']:.0%}")
    return out
