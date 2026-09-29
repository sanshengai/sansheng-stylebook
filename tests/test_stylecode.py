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
    s = "用叁笙画风手册 sb1:C31-flow-balanced-macaron.L1S0（C31 / 流程），把下面的内容做成「一张信息图（3:4）」"
    assert SC.find(s) == ["sb1:C31-flow-balanced-macaron.L1S0"]


def test_validate_against_data():
    assert SC.validate(SC.parse("sb1:C31-flow-balanced-macaron.L1S0")) == []
    assert SC.validate(SC.parse("sb1:C99-nosuch-auto-plaid")) != []
