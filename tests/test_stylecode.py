import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import stylecode as SC  # noqa: E402


@pytest.mark.parametrize("code", [
    "sb1:C01-orig", "sb1:C31-flow-balanced-macaron.L1S0", "sb1:C31@r2-auto-auto-orig",
    "sb1:C31-auto-dense-earth.L-1S-1", "sb1:C44-morandi.L0S1", "sb1:C08-film.L1S-1",
])
def test_round_trip(code):
    assert SC.parse(code).format() == code


def test_fields():
    sc = SC.parse("sb1:C31-flow-balanced-macaron.L-1S1")
    assert (sc.style, sc.structure, sc.density, sc.palette, sc.light, sc.sat) == ("C31", "flow", "balanced", "macaron", -1, 1)
    assert sc.manifest_fields() == {"style": "C31", "structure": "flow", "density": "balanced",
                                    "palette": {"family": "macaron", "light": -1, "sat": 1}}
    auto = SC.parse("sb1:C31-auto-auto-orig").manifest_fields()
    assert auto["structure"] == "auto" and "density" not in auto
    assert "structure" not in SC.parse("sb1:C01-orig").manifest_fields()


@pytest.mark.parametrize("bad", [
    "C31-orig", "sb1:C31", "sb1:C31-flow-orig", "sb1:X31-orig", "sb1:C31-orig.L1S0", "sb1:C31-flow-lots-orig",
    "sb1:C31-macaron.L2S0", "sb1:C31-Flow-auto-orig",
])
def test_rejects(bad):
    with pytest.raises(SC.StyleCodeError):
        SC.parse(bad)


def test_find_in_sentence():
    s = "用叁笙生图 sb1:C31-flow-balanced-macaron.L1S0（C31 / 流程），把下面的内容做成「一张信息图（3:4）」"
    assert SC.find(s) == ["sb1:C31-flow-balanced-macaron.L1S0"]


def test_validate_against_data():
    assert SC.validate(SC.parse("sb1:C31-flow-balanced-macaron.L1S0")) == []
    assert SC.validate(SC.parse("sb1:C99-nosuch-auto-plaid")) != []


@pytest.mark.parametrize("code", ["sb2:wxcover/C44", "sb2:xhs/C35-earth",
    "sb2:ppt/C32@r3-morandi.L1S-1", "sb2:info/C42-hex.1F6F8B.F4F1E8"])
def test_sb2_round_trip(code):
    sc = SC.parse(code)
    assert sc.format() == code
    assert sc.scene is not None


@pytest.mark.parametrize("code", ["sb2:wxcover/C44-orig.L0S0", "sb2:info/C42-hex.12345",
    "sb2:info/C42-earth-hex.123456", "sb2:wxcover/C44-brand", "sb2:wxcover/C44@r0",
    "sb2:info/C42-flow-balanced-earth", "sb2:/C42", "sb2:info/C42-morandi.L2S0"])
def test_sb2_rejects_malformed_or_conflicting_color(code):
    with pytest.raises(SC.StyleCodeError):
        SC.parse(code)


def test_sb2_hex_normalizes_and_extracts_from_sentence():
    sc = SC.parse("sb2:info/C42-hex.abcdef.123456")
    assert sc.custom == ("#ABCDEF", "#123456")
    assert sc.format() == "sb2:info/C42-hex.ABCDEF.123456"
    assert SC.find("用 sb2:info/C42-hex.abcdef.123456 做图，旧码 sb1:C01-orig") == [
        "sb2:info/C42-hex.abcdef.123456", "sb1:C01-orig"]
    assert SC.validate(SC.parse("sb2:missing/C42"))


@pytest.mark.parametrize("code", ["sb2:xhs/C30-ocean", "sb2:wxillus/C31-ocean.L-1S1", "sb2:xhs/C31-hex.FFFFFF.273D63"])
def test_find_picker_sentence(code):
    sentence = f"用叁笙生图帮我出一组小红书图：画风 C30 彩铅绘本，色系「海盐浅湾」（{code}）。内容是：学习方法。"
    assert SC.find(sentence) == [code]
    assert SC.parse(SC.find(sentence)[0]).format() == code
