"""色板偏差检查：在色板内的图偏差为 0；主色整片偏离色板必须被标出；空色板拒绝。"""
import pytest
from PIL import Image

from scripts.stylebook.qa.palette_check import check

BLUE_ORANGE = ["#1F6F8B", "#F2A541"]


def _flat(tmp_path, color, name="x.png"):
    p = tmp_path / name
    Image.new("RGB", (200, 200), color).save(p)
    return p


def test_image_inside_palette_has_no_off_palette_share(tmp_path):
    r = check(_flat(tmp_path, "#1F6F8B"), BLUE_ORANGE)
    assert r["mode"] == "report_only" and r["off_palette_share"] == 0


def test_saturated_off_palette_colour_is_flagged(tmp_path):
    r = check(_flat(tmp_path, "#D81B60"), BLUE_ORANGE)  # 品红，离蓝橙很远
    assert r["off_palette_share"] > 0.9


def test_neutral_paper_is_not_a_deviation(tmp_path):
    assert check(_flat(tmp_path, "#F4EFE6"), BLUE_ORANGE)["off_palette_share"] == 0


def test_empty_palette_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        check(_flat(tmp_path, "#1F6F8B"), [])
