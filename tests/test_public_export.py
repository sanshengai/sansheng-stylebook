"""The public snapshot gate must reject empty input and private-looking text."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_export import ExportError, scan_text, select  # noqa: E402


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
