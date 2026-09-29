import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import export as EX  # noqa: E402


def _img(tmp_path, w, h, name="g.png"):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (240, 236, 228))
    d = ImageDraw.Draw(im)
    d.rectangle([w // 2 - 10, h // 2 - 10, w // 2 + 10, h // 2 + 10], fill=(200, 30, 30))  # 中心红块
    d.rectangle([0, 0, 20, 20], fill=(30, 30, 200))  # 左上蓝块
    p = tmp_path / name
    im.save(p)
    return p


def test_cover_head_crop_resize_and_square(tmp_path):
    from PIL import Image
    src = _img(tmp_path, 1672, 941)  # 中转实际返回的尺寸（请求 1536×656 的 2.35:1 也会出现这种偏差）
    r = EX.export(src, "wechat-cover-head", tmp_path / "cover.png")
    out = Image.open(r.main)
    assert out.size == (900, 383)
    assert out.getpixel((450, 191))[0] > 150  # 居中裁切，红块仍在中心
    sq = Image.open(r.extras[0])
    assert sq.size == (383, 383) and r.extras[0].name == "cover-square.png"


def test_anchor_moves_crop(tmp_path):
    from PIL import Image
    src = _img(tmp_path, 2000, 1000)
    r = EX.export(src, "wechat-cover-square", tmp_path / "sq.png", anchor=(0.0, 0.5))
    assert Image.open(r.main).getpixel((5, 5))[2] > 150  # 焦点在左，保住左上蓝块


def test_music_cover_never_upscales(tmp_path):
    from PIL import Image
    src = _img(tmp_path, 2880, 2880)
    r = EX.export(src, "music-cover", tmp_path / "m.png")
    assert Image.open(r.main).size == (2880, 2880) and any("不得放大" in w for w in r.warnings)
    r = EX.export(src, "podcast-cover", tmp_path / "p.png")
    assert Image.open(r.main).size == (3000, 3000) and any("放大到" in w for w in r.warnings)


def test_unknown_format(tmp_path):
    with pytest.raises(KeyError):
        EX.export(_img(tmp_path, 100, 100), "nope", tmp_path / "x.png")


def test_nontransparent_export_rejects_alpha_before_rgb_conversion(tmp_path):
    from PIL import Image
    src = tmp_path / "alpha.png"
    im = Image.new("RGBA", (100, 100), (240, 236, 228, 255))
    im.putpixel((0, 0), (0, 0, 0, 1))
    im.save(src)
    out = tmp_path / "export.png"
    with pytest.raises(ValueError, match="源图含透明像素"):
        EX.export(src, "xhs-cover", out)
    assert not out.exists()
    assert EX.export(src, "sticker-grid", out).main == out


def test_single_sticker_export_is_rgba_512(tmp_path):
    from PIL import Image
    src = tmp_path / "source.png"
    Image.new("RGBA", (1254, 1254), (0, 0, 0, 0)).save(src)
    out = tmp_path / "sticker.png"
    result = EX.export(src, "sticker-single", out)
    with Image.open(result.main) as image:
        assert image.mode == "RGBA" and image.size == (512, 512)
    assert not result.warnings
