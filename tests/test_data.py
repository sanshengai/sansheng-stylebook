import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import data as D  # noqa: E402


def test_counts():
    assert len(D.structures()) == 23
    assert len(D.palettes()["palettes"]) == 12
    assert len(D.scenes()) == 10
    fams = {f["family"] for f in D.formats().values()}
    assert fams == {"单张封面", "多张轮播", "叙事分格", "信息结构", "视频帧", "透明底多宫格", "透明底单图"}
    single = D.formats()["sticker-single"]
    assert single["transparent"] and single["export_px"] == [512, 512] and single["text"]["default"] == "none"
    assert D.scenes()["sticker"]["formats"] == ["sticker-grid", "sticker-single"]
    assert len(json.loads((ROOT / "styles/catalog.json").read_text())["styles"]) == 53


def test_removed_styles_absent():
    cat = json.loads((ROOT / "styles/catalog.json").read_text())
    codes = {s["code"] for s in cat["styles"]}
    assert not codes & {"C23", "C33", "C37", "C43", "C47"}


def test_scene_references_resolve():
    fmts, cat = D.formats(), {s["code"] for s in json.loads((ROOT / "styles/catalog.json").read_text())["styles"]}
    for sc in D.scenes().values():
        for f in sc["formats"]:
            assert f in fmts, (sc["id"], f)
        for code in [sc["default"], *sc["alternates"]]:
            assert code in cat, (sc["id"], code)
            assert code.startswith("C"), "公开出厂默认不得引用私有风格"


# 出厂默认（2026-09-25 定稿）：含私有风格的原始选择，逐项机器比对
LEDGER_1247 = {"xhs": "S01", "wxillus": "S01", "wxcover": "S02", "ppt": "C32", "info": "C31",
               "comic4": "C58", "book": "C08", "board": "C01", "audio": "C25", "sticker": "C24"}


def test_public_defaults_follow_ledger():
    for sid, code in LEDGER_1247.items():
        sc = D.scenes()[sid]
        if code.startswith("C"):
            assert sc["default"] == code, sid
        else:  # 私有风格在公开版里退到第一个公开备选
            assert sc["default"] != code and sc["default"].startswith("C"), sid


def test_author_profile_matches_ledger():
    import os
    import pytest
    if not os.environ.get("STYLEBOOK_PROFILE"):
        pytest.skip("未设置私有 profile")
    for sid, code in LEDGER_1247.items():
        d, _, src = D.scene_choice(sid)
        assert (d, src) == (code, "作者档案"), sid
