"""把已导出的透明表情包宫格切成独立 PNG。"""
from __future__ import annotations

from collections import deque
from pathlib import Path


def split_grid(image: Path, out_dir: Path, grid: int) -> list[Path]:
    from PIL import Image

    if grid not in (2, 3, 4):
        raise ValueError("表情包宫格只能是 2×2、3×3 或 4×4")
    image, out_dir = Path(image), Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"输出目录已存在，拒绝覆盖：{out_dir}")

    with Image.open(image) as source:
        if source.width != source.height or source.width % grid:
            raise ValueError("输入必须是边长可被宫格数整除的方图；先用 sticker-grid 格式导出")
        if "A" not in source.getbands() and "transparency" not in source.info:
            raise ValueError("输入没有透明通道；不能把不透明背景切片冒充透明表情")
        canvas = source.convert("RGBA")

    alpha = canvas.getchannel("A")
    if alpha.getextrema()[0] != 0:
        raise ValueError("输入没有完全透明的背景像素")

    side = canvas.width // grid
    gutter = max(2, round(side * 0.01))
    for divider in range(side, canvas.width, side):
        vertical = alpha.crop((divider - gutter, 0, divider + gutter, canvas.height))
        horizontal = alpha.crop((0, divider - gutter, canvas.width, divider + gutter))
        if vertical.getextrema()[1] > 8 or horizontal.getextrema()[1] > 8:
            raise ValueError(f"宫格分界 {divider}px 附近有不透明内容；先修图，不能切断表情")

    cells = []
    for row in range(grid):
        for col in range(grid):
            cell = canvas.crop((col * side, row * side, (col + 1) * side, (row + 1) * side))
            low, high = cell.getchannel("A").getextrema()
            if low != 0 or high < 200:
                raise ValueError(f"第 {row * grid + col + 1} 格没有完整的透明背景和可见主体")
            cells.append(cell)

    out_dir.mkdir(parents=True, exist_ok=False)
    paths = []
    for index, cell in enumerate(cells, start=1):
        path = out_dir / f"sticker-{index:02d}.png"
        cell.save(path)
        paths.append(path)
    return paths


def check_single(image: Path, *, size: int = 512, min_margin: float = 0.10) -> dict:
    """只读检查正式导出的单张透明表情；语义和角色一致性仍需看图。"""
    from PIL import Image

    problems: list[str] = []
    try:
        with Image.open(image) as source:
            if source.mode != "RGBA":
                problems.append(f"图像模式为 {source.mode}，需要 RGBA")
            canvas = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        return {"image": str(image), "passed": False, "problems": [f"无法读取 PNG：{exc}"]}

    width, height = canvas.size
    if canvas.size != (size, size):
        problems.append(f"尺寸为 {width}×{height}，需要 {size}×{size}")
    alpha = canvas.getchannel("A")
    if alpha.getextrema()[0] != 0:
        problems.append("没有完全透明的背景像素")
    if alpha.getextrema()[1] < 200:
        problems.append("没有足够清晰的不透明主体")
    active = bytearray(value > 8 for value in alpha.tobytes())
    if not any(active):
        problems.append("没有可见主体")
        return {"image": str(image), "passed": False, "problems": problems}

    bbox = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
    margins = (bbox[0] / width, bbox[1] / height, (width - bbox[2]) / width, (height - bbox[3]) / height)
    if min(margins) < min_margin:
        problems.append(f"四边透明留白不足 {min_margin:.0%}：最窄 {min(margins):.2%}")

    visited = bytearray(len(active))
    components: list[int] = []
    for start in range(len(active)):
        if not active[start] or visited[start]:
            continue
        queue = deque([start])
        visited[start] = 1
        count = 0
        while queue:
            current = queue.popleft()
            count += 1
            x, y = current % width, current // width
            for yy in (y - 1, y, y + 1):
                if yy < 0 or yy >= height:
                    continue
                for xx in (x - 1, x, x + 1):
                    if xx < 0 or xx >= width:
                        continue
                    neighbor = yy * width + xx
                    if active[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        queue.append(neighbor)
        components.append(count)
    if len(components) != 1:
        problems.append(f"主体连通块 {len(components)} 个，游离像素 {sum(components) - max(components)} 个")
    return {"image": str(image), "passed": not problems, "problems": problems,
            "components": len(components), "margin_min_pct": round(min(margins) * 100, 2)}


def check_pack(directory: Path, *, count: int = 9, size: int = 512) -> dict:
    """检查成套 PNG 的数量、透明边界和游离像素，不改动图像。"""
    directory = Path(directory)
    if count < 1 or size < 1:
        raise ValueError("张数和边长必须为正整数")
    if not directory.is_dir():
        raise ValueError(f"表情包目录不存在：{directory}")
    images = sorted(directory.glob("*.png"))
    problems = [] if len(images) == count else [f"找到 {len(images)} 张 PNG，需要 {count} 张"]
    checks = [check_single(image, size=size) for image in images]
    return {"directory": str(directory), "passed": not problems and all(c["passed"] for c in checks),
            "problems": problems, "images": checks}
