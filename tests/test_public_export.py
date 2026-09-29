"""The public snapshot gate must reject empty input and private-looking text."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_export import ExportError, check_manifest, refresh_manifest, scan_text, select  # noqa: E402


def test_empty_public_selection_is_rejected():
    with pytest.raises(ExportError, match="为空"):
        select([])


@pytest.mark.parametrize("leak", ["/Users/" + "alice/private/file.json", "_work" + "space/notes",
                                   "sk-" + "A" * 30])
def test_private_content_is_rejected(leak):
    with pytest.raises(ExportError):
        scan_text("README.md", leak.encode())


def test_plain_public_text_is_allowed():
    scan_text("README.md", "Choose a style and export a JSON selection.".encode())


def test_hook_pattern_definition_is_ignored_but_other_lines_are_scanned():
    scan_text(".githooks/pre-commit", ("patterns='" + "sk-" + "A" * 30 + "'\nexit 0\n").encode())
    with pytest.raises(ExportError):
        scan_text(".githooks/pre-commit", ("patterns=''\n" + "sk-" + "A" * 30 + "\n").encode())


def test_manifest_check_detects_changed_and_missing_files(tmp_path):
    import hashlib
    import json

    (tmp_path / "SKILL.md").write_text("original", encoding="utf-8")
    receipt = {"schema_version": 1, "file_count": 1,
               "files": {"SKILL.md": hashlib.sha256(b"original").hexdigest()}}
    (tmp_path / "PUBLIC_EXPORT_MANIFEST.json").write_text(json.dumps(receipt), encoding="utf-8")
    assert check_manifest(tmp_path)["file_count"] == 1
    (tmp_path / "SKILL.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ExportError, match="变化"):
        check_manifest(tmp_path)
    refresh_manifest(tmp_path)
    assert check_manifest(tmp_path)["file_count"] == 1
    (tmp_path / "SKILL.md").unlink()
    with pytest.raises(ExportError, match="缺失"):
        check_manifest(tmp_path)
