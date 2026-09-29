import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stylebook.qa.admission import checked_images  # noqa: E402


def test_checked_images_accepts_reviewed_batch(tmp_path):
    (tmp_path / "01.png").write_bytes(b"png")
    state = {"items": {"01": {"status": "passed", "review": {"ok": True}, "image": "01.png"}},
             "summary": {"total": 1, "passed": 1, "failed": []}}
    (tmp_path / "state.json").write_text(json.dumps(state))
    assert checked_images(tmp_path) == [str(tmp_path / "01.png")]
    state["items"]["01"]["status"] = "review_failed"
    (tmp_path / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="未通过独立看图验收"):
        checked_images(tmp_path)


def test_checked_images_rejects_empty_and_missing_review(tmp_path):
    with pytest.raises(ValueError, match="缺少 state.json"):
        checked_images(tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({"items": {}, "summary": {"total": 0, "passed": 0}}))
    with pytest.raises(ValueError, match="没有可验收"):
        checked_images(tmp_path)
