"""局部绝对复核：已知问题必须拒绝，两次分歧也不能放行。"""
import json

import pytest

from stylebook.qa.focus import check


CRITERION = "broad connected mirror-like reflections crossing multiple paving stones"


def _answer(present):
    return {"must_not_see": [{"item": CRITERION, "present": present,
                               "why": "逐块观察了路面反光与接缝"}]}


def _image(tmp_path):
    path = tmp_path / "road.png"
    path.write_bytes(b"cropped road pixels")
    return path


def test_known_bad_crop_is_rejected_twice(tmp_path):
    crop = _image(tmp_path)
    result = check(crop, CRITERION, ask=lambda *_: _answer(True))
    assert result["passed"] is False
    assert len(result["reviews"]) == 2
    assert all(not r["passed"] for r in result["reviews"])
    assert result["crop"]["sha256"]
    assert "not full-image QA" in result["scope"]


def test_candidate_requires_both_independent_reviews(tmp_path):
    crop = _image(tmp_path)
    answers = iter([_answer(False), _answer(True)])
    assert check(crop, CRITERION, ask=lambda *_: next(answers))["passed"] is False
    assert check(crop, CRITERION, ask=lambda *_: _answer(False))["passed"] is True


@pytest.mark.parametrize("answer", [
    {},
    {"must_not_see": []},
    {"must_not_see": [{"item": CRITERION, "present": "false", "why": "可见"}]},
    {"must_not_see": [{"item": CRITERION, "present": False, "why": " "}]},
    {"must_not_see": [_answer(False)["must_not_see"][0]] * 2},
])
def test_missing_ambiguous_or_duplicate_answer_fails_closed(tmp_path, answer):
    assert check(_image(tmp_path), CRITERION, ask=lambda *_: answer)["passed"] is False


def test_empty_criterion_and_missing_image_do_not_call_reviewer(tmp_path):
    crop = _image(tmp_path)
    def forbidden(*_):
        raise AssertionError("reviewer should not run")
    with pytest.raises(ValueError, match="判据|特征"):
        check(crop, " ", ask=forbidden)
    crop.unlink()
    with pytest.raises(FileNotFoundError):
        check(crop, CRITERION, ask=forbidden)


def test_cli_returns_failure_and_preserves_existing_report(tmp_path, monkeypatch):
    import sb
    from stylebook.qa import focus
    crop = _image(tmp_path)
    monkeypatch.setattr(focus, "review", lambda *_args, **_kw: _answer(True))
    monkeypatch.setattr(focus, "source", lambda: "ark_agent_plan")
    report = tmp_path / "report.json"
    args = ["qa-focus", str(crop), "--criterion", CRITERION, "--report", str(report)]
    assert sb.main(args) == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["review_source"] == "ark_agent_plan"
    assert data["reviews"][1]["passed"] is False
    assert sb.main(args) == 2
    assert json.loads(report.read_text(encoding="utf-8")) == data
