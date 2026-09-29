import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook.sticker import check_pack, check_single, split_grid  # noqa: E402
from sb import main  # noqa: E402


def _grid(path: Path, count: int) -> Path:
    side = 96
    image = Image.new("RGBA", (side * count, side * count), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for row in range(count):
        for col in range(count):
            x, y = col * side + side // 2, row * side + side // 2
            draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill=(40 + row * 30, 80 + col * 30, 120, 255))
    image.save(path)
    return path


@pytest.mark.parametrize("count", [2, 3, 4])
def test_split_transparent_grid_in_reading_order(tmp_path, count):
    source = _grid(tmp_path / "grid.png", count)
    paths = split_grid(source, tmp_path / "slices", count)
    assert len(paths) == count * count
    assert paths[0].name == "sticker-01.png"
    assert paths[-1].name == f"sticker-{count * count:02d}.png"
    for index, path in enumerate(paths):
        with Image.open(path) as image:
            assert image.mode == "RGBA" and image.size == (96, 96)
            assert image.getpixel((0, 0))[3] == 0
            assert image.getpixel((48, 48)) == (40 + (index // count) * 30, 80 + (index % count) * 30, 120, 255)


def test_rejects_opaque_source_and_cross_cell_content(tmp_path):
    opaque = tmp_path / "opaque.png"
    Image.new("RGB", (288, 288), "white").save(opaque)
    with pytest.raises(ValueError, match="透明通道"):
        split_grid(opaque, tmp_path / "opaque-out", 3)
    assert not (tmp_path / "opaque-out").exists()

    source = _grid(tmp_path / "cross.png", 3)
    with Image.open(source) as raw:
        image = raw.copy()
    ImageDraw.Draw(image).rectangle((93, 20, 99, 70), fill=(200, 30, 30, 255))
    image.save(source)
    with pytest.raises(ValueError, match="宫格分界"):
        split_grid(source, tmp_path / "cross-out", 3)
    assert not (tmp_path / "cross-out").exists()


def test_rejects_empty_cell_and_existing_output(tmp_path):
    source = _grid(tmp_path / "grid.png", 3)
    with Image.open(source) as raw:
        image = raw.copy()
    ImageDraw.Draw(image).rectangle((0, 0, 95, 95), fill=(0, 0, 0, 0))
    image.save(source)
    with pytest.raises(ValueError, match="第 1 格"):
        split_grid(source, tmp_path / "empty-out", 3)
    assert not (tmp_path / "empty-out").exists()

    (tmp_path / "existing").mkdir()
    with pytest.raises(FileExistsError, match="已存在"):
        split_grid(source, tmp_path / "existing", 3)


def test_cli_reports_invalid_grid_without_traceback(tmp_path, capsys):
    source = _grid(tmp_path / "grid.png", 3)
    code = main(["sticker-split", str(source), "--grid", "5", "-d", str(tmp_path / "slices")])
    stderr = capsys.readouterr().err
    assert code == 2
    assert "只能是 2×2、3×3 或 4×4" in stderr
    assert "Traceback" not in stderr


def _single(path: Path, *, stray: bool = False) -> Path:
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((170, 120, 342, 392), fill=(220, 120, 70, 255))
    if stray:
        image.putpixel((80, 80), (255, 0, 0, 255))
    image.save(path)
    return path


def test_single_gate_accepts_subject_and_rejects_detached_pixel(tmp_path):
    source = _single(tmp_path / "sticker.png")
    assert check_single(source)["passed"]
    _single(source, stray=True)
    bad = check_single(source)
    assert not bad["passed"] and "游离像素 1 个" in bad["problems"][0]


def test_single_gate_rejects_missing_alpha_and_padding(tmp_path):
    opaque = tmp_path / "opaque.png"
    Image.new("RGB", (512, 512), "white").save(opaque)
    assert not check_single(opaque)["passed"]
    edge = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(edge).ellipse((5, 100, 200, 300), fill=(220, 120, 70, 255))
    path = tmp_path / "edge.png"
    edge.save(path)
    assert any("透明留白不足" in p for p in check_single(path)["problems"])
    faint = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(faint).ellipse((170, 120, 342, 392), fill=(220, 120, 70, 100))
    faint_path = tmp_path / "faint.png"
    faint.save(faint_path)
    assert any("没有足够清晰" in p for p in check_single(faint_path)["problems"])


def test_pack_gate_and_cli_reject_empty_input(tmp_path, capsys):
    directory = tmp_path / "pack"
    directory.mkdir()
    assert not check_pack(directory)["passed"]
    assert main(["sticker-check", str(directory)]) == 2
    capsys.readouterr()
    for index in range(1, 10):
        _single(directory / f"sticker-{index:02d}.png")
    assert check_pack(directory)["passed"]
    assert main(["sticker-check", str(directory)]) == 0
    capsys.readouterr()
    _single(directory / "sticker-09.png", stray=True)
    assert main(["sticker-check", str(directory)]) == 2
