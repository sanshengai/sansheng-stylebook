"""文档卫生检查：真实仓库必须通过；每类问题都要能被拒绝，空输入也要拒绝。"""
import json
import shutil
from pathlib import Path

from scripts.stylebook.docs_check import ROOT, check


def _mini(tmp_path: Path) -> Path:
    (tmp_path / "references").mkdir()
    (tmp_path / "styles" / "C01").mkdir(parents=True)
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "scenes.json").write_text(json.dumps({"scenes": [{"id": "xhs"}]}))
    (tmp_path / "SKILL.md").write_text("[a](references/a.md)\n")
    (tmp_path / "references" / "a.md").write_text("画风 C01，场景 id `xhs`。\n")
    return tmp_path


def test_real_repo_docs_are_clean():
    assert check(ROOT) == []


def test_mini_repo_passes_then_each_defect_is_rejected(tmp_path):
    root = _mini(tmp_path)
    assert check(root) == []
    (root / "references" / "b.md").write_text("无人链接\n")
    assert any("孤儿" in p for p in check(root))
    (root / "references" / "b.md").unlink()
    (root / "references" / "a.md").write_text("[x](gone.md)\n")
    assert any("不存在" in p for p in check(root))
    (root / "references" / "a.md").write_text("提到 C77。\n")
    assert any("C77" in p for p in check(root))
    (root / "references" / "a.md").write_text("场景 id `nope`。\n")
    assert any("nope" in p for p in check(root))


def test_empty_input_is_rejected(tmp_path):
    assert check(tmp_path) != []
