"""局部动效：区域外逐帧不变；按平台预算降档；超预算和坏参数必须被拒绝。"""
import pytest
from PIL import Image, ImageChops, ImageDraw

from scripts.stylebook import motion as MO


@pytest.fixture()
def pic(tmp_path):
    img = Image.new("RGB", (800, 450), "#F4EFE6")
    d = ImageDraw.Draw(img)
    for i in range(0, 800, 40):
        d.rectangle([i, 0, i + 20, 450], fill=(40 + i % 200, 90, 140))
    p = tmp_path / "s.png"
    img.save(p)
    return p


@pytest.mark.parametrize("template", MO.TEMPLATES)
def test_pixels_outside_region_are_identical_in_every_frame(pic, template):
    region = (0.5, 0.2, 0.3, 0.4)
    fr = MO.frames(pic, template, region)
    box = MO._box(fr[0].size, region)
    assert len(fr) == MO.FRAMES and any(ImageChops.difference(fr[0], f).getbbox() for f in fr[1:])  # 确实在动
    mask = Image.new("L", fr[0].size, 255)
    ImageDraw.Draw(mask).rectangle(box, fill=0)
    for f in fr[1:]:
        diff = ImageChops.difference(fr[0], f).convert("L")
        assert ImageChops.multiply(diff, mask).getbbox() is None


def test_gif_fits_each_platform_budget_and_loops(pic, tmp_path):
    for target, cfg in MO.TARGETS.items():
        out = tmp_path / f"{target}.gif"
        r = MO.make(pic, "glow", (0.5, 0.2, 0.3, 0.4), target, out)
        assert out.stat().st_size <= cfg["budget"] and r["frames"] > 1
        with Image.open(out) as g:
            assert g.n_frames == r["frames"] and g.info.get("loop") == 0
            if cfg["square"]:
                assert g.width == g.height <= cfg["max_w"]


def test_over_budget_is_refused_and_leaves_no_file(pic, tmp_path, monkeypatch):
    monkeypatch.setitem(MO.TARGETS, "wechat-sticker", {"max_w": 240, "budget": 100, "square": True})  # 真实编码，预算极小
    out = tmp_path / "x.gif"
    with pytest.raises(MO.MotionError):
        MO.make(pic, "particles", (0.1, 0.1, 0.8, 0.8), "wechat-sticker", out)
    assert not out.exists()


@pytest.mark.parametrize("region", [(0, 0, 0, 0.5), (0.9, 0.9, 0.5, 0.5), (-0.1, 0, 0.5, 0.5)])
def test_bad_region_is_rejected(pic, region):
    with pytest.raises(MO.MotionError):
        MO.frames(pic, "glow", region)


def test_unknown_template_and_target_are_rejected(pic, tmp_path):
    with pytest.raises(MO.MotionError):
        MO.frames(pic, "spin", (0.1, 0.1, 0.5, 0.5))
    with pytest.raises(MO.MotionError):
        MO.encode(MO.frames(pic, "glow", (0.1, 0.1, 0.5, 0.5)), tmp_path / "y.gif", "weibo")
