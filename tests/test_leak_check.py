"""串味检查：原样搬进成图的块必须被标出；无关图不能报警；纹理太少的参考图必须拒绝。"""
import numpy as np
import pytest
from PIL import Image, ImageFilter

from scripts.stylebook.qa import leak_check as LK


def textured(seed, size=(640, 480)):
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 255, size=(size[1] // 8, size[0] // 8, 3), dtype=np.uint8)
    return Image.fromarray(a).resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))


def test_copied_patch_is_flagged_and_unrelated_is_not(tmp_path):
    ref = textured(1)
    out = textured(2)
    crop = ref.crop((180, 100, 440, 300))
    out.paste(crop, (60, 90))
    ref.save(tmp_path / "ref.png")
    out.save(tmp_path / "leak.png")
    textured(3).save(tmp_path / "other.png")
    leaked = LK.check(tmp_path / "leak.png", tmp_path / "ref.png")
    clean = LK.check(tmp_path / "other.png", tmp_path / "ref.png")
    assert leaked["mode"] == "report_only" and leaked["flag"] is True and leaked["max_ncc"] >= 0.9
    assert clean["flag"] is False


def test_flat_reference_is_rejected(tmp_path):
    Image.new("RGB", (400, 300), "#EEEEEE").save(tmp_path / "flat.png")
    textured(4).save(tmp_path / "out.png")
    with pytest.raises(ValueError):
        LK.check(tmp_path / "out.png", tmp_path / "flat.png")
