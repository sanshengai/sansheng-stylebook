import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import character as CH  # noqa: E402
from stylebook import compile as CP  # noqa: E402
from stylebook import contract as CT  # noqa: E402
from stylebook.qa import judge  # noqa: E402

GIRL = {"id": "xiaoyu", "name": "小雨", "desc": "A young student with a slim build",
        "markers": ["two small round hair buns on top of her head", "big round glasses",
                    "a crescent-moon hair clip above her left ear", "an oversized hoodie with a front pocket"]}


@pytest.fixture(autouse=True)
def _no_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("STYLEBOOK_PROFILE", str(tmp_path / "none"))
    monkeypatch.setattr(CT.Path, "home", staticmethod(lambda: tmp_path))


def test_valid_character_and_color_only_rejected():
    assert CH.validate(GIRL) == []
    bad = dict(GIRL, markers=["red scarf", "blue shoes", "yellow hat"])
    assert any("不能只靠颜色" in p for p in CH.validate(bad))
    assert any("至少 3 条" in p for p in CH.validate(dict(GIRL, markers=["big round glasses"])))
    assert any("id" in p for p in CH.validate(dict(GIRL, id="小雨")))
    assert any("未成年年龄" in p for p in CH.validate(dict(GIRL, desc="A twelve-year-old girl")))
    assert any("未成年年龄" in p for p in CH.validate(dict(GIRL, desc="A 12-year-old girl")))
    assert CH.validate(dict(GIRL, desc="A 30-year-old teacher")) == []


def test_sheet_and_scene_manifests_compile(tmp_path):
    c = CP.compile_manifest(CH.sheet_manifest(GIRL, "C58"))
    assert "reference sheet" in c.prompt and "crescent-moon hair clip" in c.prompt and c.aspect == "16:9"
    sheet = tmp_path / "sheet.png"
    m = CH.scene_manifest(GIRL, "C58", "She reads a book at her desk by the window", sheet)
    c = CP.compile_manifest(m)
    # 角色身份参考之外，合同有画风锚点时编译器会把锚点作为画风参考放在最前
    assert c.references[-1] == {"path": str(sheet), "role": "identity"}
    assert [r["role"] for r in c.references[:-1]] == (["style"] if CT.load("C58").get("anchor") else [])
    assert "character identity reference" in c.prompt and "big round glasses" in c.prompt


def test_consistency_contract_judges(tmp_path):
    from PIL import Image
    img = tmp_path / "grid.png"
    Image.new("RGB", (64, 64), (230, 230, 230)).save(img)
    cc = CH.consistency_contract(GIRL, CT.load("C58"))
    ok = {"must_see": [{"item": i, "ok": True, "why": "看到该特征"} for i in cc["qa"]["must_see"]],
          "must_not_see": [{"item": i, "present": False, "why": "未见"} for i in cc["qa"]["must_not_see"]], "transcribed_text": []}
    assert judge(img, cc, ok, [], "none").passed
    ok["must_see"][2]["ok"] = False  # 发夹在某一格丢了
    v = judge(img, cc, ok, [], "none")
    assert not v.passed and any("crescent-moon" in p for p in v.problems)


def test_project_lock_requires_revision(tmp_path):
    with pytest.raises(ValueError):
        CH.project_lock(tmp_path, "C58")
    p = CH.project_lock(tmp_path, "C58@r1", characters=["xiaoyu"])
    assert CH.project_load(tmp_path)["style"] == "C58@r1" and p.name == "stylebook.project.json"
    from stylebook import plan as PL
    assert PL.resolve_style("comic4", project=p) == {"code": "C58@r1", "source": "project", "palette": {"family": "orig"}}
