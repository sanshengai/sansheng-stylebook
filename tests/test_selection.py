import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import contract as CT  # noqa: E402
from stylebook import plan as PL  # noqa: E402
from stylebook import selection as S  # noqa: E402


@pytest.fixture(autouse=True)
def no_private_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("SANSHENG_IMAGE_PROFILE", str(tmp_path / "none"))
    monkeypatch.setattr(S.CT.Path, "home", staticmethod(lambda: tmp_path))


def record(code="C31", *, palette=None, items=None):
    return {"version": 1, "scene": "wxillus", "series_id": "article-1",
            "style": {"code": code, "source": "explicit", "locked": True},
            "palette": palette or {"family": "orig", "source": "factory"},
            "expression": {"form": "auto", "source": "factory"}, "items": items or {}}


def plan():
    return {"scene": "wxillus", "series": {"id": "article-1", "master_id": "02"},
            "style": {"code": "C31", "source": "explicit", "why": "用户选定此画风用于整组文章配图"},
            "items": [{"id": f"0{i}", "position": f"「这一节的最后一句话{i}」之后", "shape": "steps",
                       "form": "structure", "structure": "flow", "points": ["先确认条件", "再完成动作"],
                       "what": "展示步骤", "subject": "two process steps", "why": "该段落明确包含有先后关系的两个步骤"}
                      for i in (1, 2, 3)]}


def test_local_change_only_affects_target_and_applies_manual_structure():
    before = S.normalize(record(), item_ids={"01", "02", "03"})
    after = copy.deepcopy(before)
    after["items"]["03"] = {"expression": {"form": "structure", "structure": "compare", "source": "explicit"},
                            "text_direction": "短标签，但仍保留条件"}
    assert S.affected(before, after, plan()) == ["03"]
    result = S.apply(plan(), after)
    assert result["items"][2]["structure"] == "compare"
    assert result["items"][2]["manual"] is True
    assert result["items"][0]["structure"] == "flow"
    assert result["items"][2]["text_direction"] == "短标签，但仍保留条件"
    assert PL.check(result)[0] == []


def test_master_and_group_palette_invalidate_dependents():
    before = S.normalize(record())
    after = copy.deepcopy(before)
    after["items"]["02"] = {"text_direction": "减少文字"}
    assert S.affected(before, after, plan()) == ["02"]
    assert S.affected(before, after, plan(), replace_master=True) == ["01", "02", "03"]
    after = copy.deepcopy(before)
    after["palette"] = {"family": "macaron", "source": "explicit", "locked": True}
    assert S.affected(before, after, plan()) == ["01", "02", "03"]
    after = copy.deepcopy(before)
    after["style"]["source"] = "project"
    assert S.affected(before, after, plan()) == []


def test_conflicts_and_unknown_versions_fail_closed():
    with pytest.raises(S.SelectionError, match="锁色"):
        S.normalize(record("C02", palette={"family": "macaron"}))
    with pytest.raises(S.SelectionError, match="只允许调整原色深浅"):
        S.normalize(record("C32", palette={"family": "orig", "sat": 1}))
    bad = record()
    bad["style"]["revision"] = 999
    with pytest.raises(S.SelectionError, match="修订"):
        S.normalize(bad)
    bad = record()
    bad["version"] = 2
    with pytest.raises(S.SelectionError, match="版本"):
        S.normalize(bad)
    with pytest.raises(S.SelectionError, match="未知图片 ID"):
        S.normalize(record(items={"99": {"text_direction": "简化"}}), item_ids={"01"})
    with pytest.raises(S.SelectionError, match="具体 HEX"):
        S.normalize("sb1:C31-brand.L0S0", scene="wxillus")


def test_legacy_code_and_brand_hex_roundtrip():
    legacy = S.normalize(f"sb1:C31@r{CT.load('C31')['revision']}-compare-balanced-orig", scene="wxillus")
    assert legacy["style"]["revision"] == CT.load("C31")["revision"]
    assert legacy["expression"]["structure"] == "compare"
    assert legacy["expression"]["density"] == "balanced"
    brand = record(palette={"family": "brand", "custom": ["#aabbcc"], "source": "explicit"})
    normalized = S.normalize(brand)
    assert normalized["palette"]["custom"] == ["#AABBCC"]
    assert S.normalize(json.loads(S.dumps(normalized))) == normalized
    with pytest.raises(S.SelectionError, match="密度"):
        S.apply(plan(), {**record(), "expression": {"form": "structure", "structure": "flow", "density": "balanced"}})


def test_empty_and_unsupported_inputs_do_not_pass():
    for value in ({}, {"version": 1, "scene": "wxillus"}, {"version": 1, "scene": "wxillus", "style": {"code": "C31"}, "items": []}):
        with pytest.raises(S.SelectionError):
            S.normalize(value)


def test_recommend_keeps_content_expression_separate_from_scene_style():
    result = S.recommend("wxillus", shapes=["story", "parts"], explicit="C31")
    assert result["chosen"]["code"] == "C31"
    assert result["expression_by_content"][0]["forms"] == ["scene"]
    assert result["expression_by_content"][1]["structures"][0] == "grid"
    assert result["candidates"][0]["code"] == "C31"
    assert result["candidates"][0]["content_fit"] in {"suggested", "unverified"}


def test_sb2_binds_scene_revision_and_custom_palette():
    revision = S.CT.load("C42")["revision"]
    result = S.normalize(f"sb2:info/C42@r{revision}-hex.1f6f8b.F4F1E8")
    assert result["scene"] == "info"
    assert result["style"]["revision"] == revision
    assert result["palette"]["custom"] == ["#1F6F8B", "#F4F1E8"]
    with pytest.raises(S.SelectionError, match="不一致"):
        S.normalize("sb2:info/C42", scene="wxillus")
    with pytest.raises(S.SelectionError, match="不可用"):
        S.normalize("sb2:info/C42@r999")
    locked = next(c for c in S.CT.contract_paths() if S.CT.load(c.parent.name)["palette"]["recolor"] == "locked")
    with pytest.raises(S.SelectionError, match="锁色"):
        S.normalize(f"sb2:info/{locked.parent.name}-hex.1F6F8B")
