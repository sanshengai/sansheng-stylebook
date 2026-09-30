import hashlib
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stylebook.qa import sheet as sheets


@pytest.mark.parametrize("mode,color,expected", [
    ("RGBA", (0, 255, 0, 0), (255, 255, 255)),
    ("RGBA", (0, 255, 0, 128), (127, 255, 127)),
    ("RGB", (12, 34, 56), (12, 34, 56)),
    ("LA", (0, 128), (127, 127, 127)),
    ("P", 0, (255, 255, 255)),
])
@pytest.mark.parametrize("consumer", ["consistency", "thumb", "matrix"])
def test_sheet_composites_transparency_without_mutating_source(tmp_path, mode, color, expected, consumer):
    source = tmp_path / "source.png"
    im = Image.new(mode, (24, 24), color)
    if mode == "P":
        im.putpalette([0, 255, 0] + [0, 0, 0] * 255)
        im.info["transparency"] = 0
    im.save(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    out = tmp_path / "sheet.png"
    if consumer == "consistency":
        sheets.consistency_sheet(source, [], out, cell=40)
        point = (20, 20)
    elif consumer == "thumb":
        sheets.thumb_sheet(source, out, sizes=(24,))
        point = (20, 20)
    else:
        sheets.matrix_sheet([{"image": source}], out, cols=1, cell=40)
        point = (20, 20)
    with Image.open(out) as preview:
        assert preview.mode == "RGB"
        assert preview.getpixel(point) == expected
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_old_alpha_discard_behavior_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "hidden-green.png"
    Image.new("RGBA", (24, 24), (0, 255, 0, 0)).save(source)
    monkeypatch.setattr(sheets, "_preview_rgb", lambda p: Image.open(p).convert("RGB"))
    out = tmp_path / "old.png"
    sheets.consistency_sheet(source, [], out, cell=40)
    with Image.open(out) as preview:
        assert preview.getpixel((20, 20)) != (255, 255, 255)
