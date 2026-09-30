"""对照网格：一致性检查（第一格放定妆图，其余并排）与缩略图可辨认检查（46 / 66 / 128 像素）。"""
from __future__ import annotations

from pathlib import Path

CJK_FONTS = ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
             "C:/Windows/Fonts/msyh.ttc"]


def _font(size: int = 15):
    from PIL import ImageFont
    for f in CJK_FONTS:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size), True
            except OSError:
                continue
    return ImageFont.load_default(), False


def _preview_rgb(path: Path):
    """Composite source transparency onto the white sheet, without changing source bytes."""
    from PIL import Image
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        return Image.alpha_composite(background, rgba).convert("RGB")


def consistency_sheet(reference: Path, others: list[Path], out: Path, cell: int = 320, labels: list[str] | None = None) -> Path:
    from PIL import Image, ImageDraw
    items = [reference] + list(others)
    cols = min(5, len(items))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 24)), "white")
    d = ImageDraw.Draw(sheet)
    font, cjk = _font()
    for i, p in enumerate(items):
        im = _preview_rgb(p)
        im.thumbnail((cell, cell))
        x, y = (i % cols) * cell, (i // cols) * (cell + 24)
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        tag = ("定妆图" if cjk else "REF") if i == 0 else (labels[i - 1] if labels and i - 1 < len(labels) else p.stem)
        d.rectangle([x, y + cell, x + cell, y + cell + 24], fill=(236, 236, 231))
        d.text((x + 6, y + cell + 3), tag[:40], fill=(20, 20, 20), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def thumb_sheet(image: Path, out: Path, sizes=(46, 66, 128)) -> Path:
    from PIL import Image
    im = _preview_rgb(image)
    thumbs = []
    for s in sizes:
        t = im.copy()
        t.thumbnail((s, s))
        thumbs.append(t)
    w = sum(t.width for t in thumbs) + 20 * len(thumbs)
    h = max(t.height for t in thumbs) + 20
    sheet = Image.new("RGB", (w, h), "white")
    x = 10
    for t in thumbs:
        sheet.paste(t, (x, 10))
        x += t.width + 20
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


STATUS_COLOR = {"pass": ((226, 242, 228), (27, 94, 32)), "fail": ((251, 228, 226), (183, 28, 28)),
                "split": ((253, 240, 213), (146, 84, 0)), "pending": ((236, 236, 231), (90, 90, 90))}


def matrix_sheet(cells: list[dict], out: Path, cols: int = 4, cell: int = 360, title: str = "") -> Path:
    """测试矩阵图：每格一张图 + 底部状态条（通过绿、不过红、待定灰）；没出图的格子留灰底。"""
    from PIL import Image, ImageDraw
    rows = (len(cells) + cols - 1) // cols
    head = 40 if title else 0
    strip = 30
    sheet = Image.new("RGB", (cols * cell, head + rows * (cell + strip)), "white")
    d = ImageDraw.Draw(sheet)
    font, _ = _font(16)
    if title:
        d.text((10, 10), title, fill=(20, 20, 20), font=_font(20)[0])
    for i, c in enumerate(cells):
        x, y = (i % cols) * cell, head + (i // cols) * (cell + strip)
        if c.get("image"):
            im = _preview_rgb(c["image"])
            im.thumbnail((cell - 8, cell - 8))
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        else:
            d.rectangle([x + 4, y + 4, x + cell - 4, y + cell - 4], fill=(244, 244, 240))
        bg, fg = STATUS_COLOR.get(c.get("status", "pending"), STATUS_COLOR["pending"])
        d.rectangle([x, y + cell, x + cell, y + cell + strip], fill=bg)
        d.text((x + 8, y + cell + 6), c.get("label", "")[:40], fill=fg, font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
