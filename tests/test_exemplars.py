"""内容范例参考图：按内容命中挂载、总数 ≤ 3、没有范例时提示词与旧版逐字相同。"""
import copy
import json
from pathlib import Path

import pytest

from scripts.stylebook import compile as C
from scripts.stylebook import contract as K

ROOT = Path(__file__).resolve().parents[1]


def _contract():
    c = copy.deepcopy(K.load("C42"))
    base = Path(c["_path"]).parent
    c["exemplars"] = [
        {"kind": "character", "file": "samples/a.webp", "sha256": "0" * 64, "contains": ["person"], "isolation": "Borrow only how people are drawn."},
        {"kind": "graphic", "file": "samples/b.webp", "sha256": "1" * 64, "contains": ["arrows"], "isolation": "Borrow only how arrows are drawn."},
    ]
    return c, base


def _manifest(**extra):
    m = {"style": "C42", "format": "article-illustration", "content": {"subject": "A small team shares one idea."},
         "text": {"mode": "none"}}
    m.update(extra)
    return m


def test_no_exemplars_leaves_prompt_identical():
    base = C.compile_manifest(_manifest())
    c, _ = _contract()
    c.pop("exemplars")
    assert C.compile_manifest(_manifest(), c).prompt == base.prompt


def test_character_exemplar_mounted_only_when_requested():
    c, base = _contract()
    plain = C.compile_manifest(_manifest(), c)
    assert all(r["role"] != "exemplar_character" for r in plain.references)
    got = C.compile_manifest(_manifest(exemplars=["character"]), c)
    roles = [r["role"] for r in got.references]
    assert "exemplar_character" in roles and "exemplar_graphic" not in roles
    assert "Borrow only how people are drawn." in got.prompt
    assert str(base / "samples/a.webp") in [r["path"] for r in got.references]


def test_total_refs_never_exceed_three_and_user_refs_win(tmp_path):
    c, _ = _contract()
    user = [{"path": str(tmp_path / f"u{i}.png"), "role": "pose"} for i in range(2)]
    got = C.compile_manifest(_manifest(exemplars=["character", "graphic"], references=user), c)
    assert len(got.references) <= C.MAX_REFS
    assert [r["path"] for r in got.references if r["role"] == "pose"] == [u["path"] for u in user]


def test_unknown_exemplar_kind_is_rejected():
    c, _ = _contract()
    with pytest.raises(C.CompileError):
        C.compile_manifest(_manifest(exemplars=["video"]), c)


def test_schema_accepts_new_fields_and_rejects_bad_hash():
    import jsonschema
    schema = json.loads((ROOT / "styles/_schema/contract.schema.json").read_text(encoding="utf-8"))
    c, _ = _contract()
    c = {k: v for k, v in c.items() if not k.startswith("_")}
    jsonschema.validate(c, schema)
    c["exemplars"][0]["sha256"] = "bad"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(c, schema)
