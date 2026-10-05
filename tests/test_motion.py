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


@pytest.mark.parametrize("template", [t for t in MO.TEMPLATES if t != "labels"])
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


# ---- labels：标签依次出现 ----
BOXES = [(0.05, 0.05, 0.2, 0.2), (0.4, 0.3, 0.2, 0.2), (0.7, 0.6, 0.25, 0.3)]


@pytest.fixture()
def lab(tmp_path):
    img = Image.new("RGB", (800, 450), "#F4EFE6")
    d = ImageDraw.Draw(img)
    for x, y, w, h in BOXES:                                    # 每个标签区域画上深色字块
        d.rectangle([x * 800 + 10, y * 450 + 10, (x + w) * 800 - 10, (y + h) * 450 - 10], fill=(30, 30, 30))
    p = tmp_path / "l.png"
    img.save(p)
    return p, img


def _same(a, b, box):
    return ImageChops.difference(a.crop(box), b.crop(box)).getbbox() is None


def test_labels_outside_unchanged_first_erased_last_original(lab):
    p, orig = lab
    fr = MO.frames(p, "labels", BOXES)
    boxes = [MO._box(orig.size, b) for b in BOXES]
    mask = Image.new("L", orig.size, 255)
    for b in boxes:
        ImageDraw.Draw(mask).rectangle([b[0], b[1], b[2] - 1, b[3] - 1], fill=0)
    for f in fr:                                                 # 区域外每一帧都等于原图
        assert ImageChops.multiply(ImageChops.difference(f, orig).convert("L"), mask).getbbox() is None
    assert all(not _same(fr[0], orig, b) for b in boxes)         # 第一帧标签被抹掉
    assert ImageChops.difference(fr[-1], orig).getbbox() is None  # 最后一帧与原图一致


def test_labels_appear_in_order(lab):
    p, orig = lab
    fr = MO.frames(p, "labels", BOXES)
    boxes = [MO._box(orig.size, b) for b in BOXES]
    first = [next(i for i, f in enumerate(fr) if not _same(f, fr[0], b)) for b in boxes]
    assert first == sorted(first) and len(set(first)) == len(first) and first[0] > 0


def test_labels_group_appears_together(lab):
    p, orig = lab
    fr = MO.frames(p, "labels", [BOXES[0], [BOXES[1], BOXES[2]]])
    b1, b2 = MO._box(orig.size, BOXES[1]), MO._box(orig.size, BOXES[2])
    i1 = next(i for i, f in enumerate(fr) if not _same(f, fr[0], b1))
    i2 = next(i for i, f in enumerate(fr) if not _same(f, fr[0], b2))
    assert i1 == i2


@pytest.mark.parametrize("regions", [[], [(0.9, 0.9, 0.3, 0.3)], [(0.1, 0.1, 0.3, 0.3), (0.2, 0.2, 0.3, 0.3)], [()], [[]]])
def test_labels_bad_input_rejected(lab, regions):
    with pytest.raises(MO.MotionError):
        MO.frames(lab[0], "labels", regions)


def test_labels_webp_is_animated_and_gif_no_loop(lab, tmp_path):
    p, _ = lab
    w = MO.make(p, "labels", BOXES, "web", tmp_path / "a.webp")
    with Image.open(tmp_path / "a.webp") as im:
        assert im.format == "WEBP" and im.n_frames == w["frames"] > 1 and im.info.get("loop") == 0
    MO.make(p, "labels", BOXES, "wechat-article", tmp_path / "b.gif", loop=False)
    with Image.open(tmp_path / "b.gif") as g:
        assert g.n_frames > 1 and "loop" not in g.info


def test_layout_json_boxes_follow_item_order(tmp_path):
    spec = tmp_path / "o.json"
    spec.write_text('{"items": [{"text": "a", "box": [0.1, 0.1, 0.2, 0.1]}, {"text": "b", "box": [0.5, 0.5, 0.2, 0.1]}]}', encoding="utf-8")
    assert MO.boxes_from_layout(spec) == [(0.1, 0.1, 0.2, 0.1), (0.5, 0.5, 0.2, 0.1)]
    spec.write_text('{"items": []}', encoding="utf-8")
    with pytest.raises(MO.MotionError):
        MO.boxes_from_layout(spec)
