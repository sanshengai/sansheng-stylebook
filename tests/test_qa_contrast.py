"""相对材质复核：两个匿名顺序必须给出同一方向的缺陷证据。"""
import pytest

from stylebook.qa.contrast import compare


def _images(tmp_path):
    a, b = tmp_path / "old.png", tmp_path / "new.png"
    a.write_bytes(b"reference-image")
    b.write_bytes(b"candidate-image")
    return a, b


def _answer(*, a_defect, b_defect, preferred):
    return {"A_observation": "road has visible patches", "B_observation": "road is visibly different",
            "A_defect": a_defect, "B_defect": b_defect, "preferred": preferred,
            "reason": "the road surfaces differ"}


def test_ark_contrast_network_error_stops_before_second_order(tmp_path, monkeypatch):
    from stylebook.qa import contrast
    from stylebook.qa.reviewer import ARK_PLAN_URL, ReviewerNetworkUnavailable

    old, new = _images(tmp_path)
    monkeypatch.setenv("ARK_AGENT_PLAN_BASE_URL", ARK_PLAN_URL)
    monkeypatch.setenv("ARK_AGENT_PLAN_API_KEY", "test-key")
    monkeypatch.setattr(contrast, "_image_uri", lambda _: "data:image/png;base64,dGVzdA==")
    calls = []

    def unavailable(request, timeout):
        calls.append(1)
        raise contrast.urllib.error.URLError(OSError(1, "Operation not permitted"))

    monkeypatch.setattr(contrast.urllib.request, "urlopen", unavailable)
    with pytest.raises(ReviewerNetworkUnavailable, match="网络不可用"):
        compare(old, new, "matte road")
    assert len(calls) == 1


def test_candidate_better_requires_both_image_orders(tmp_path):
    old, new = _images(tmp_path)
    called = []

    def ask(a, b, criterion):
        called.append((a, b, criterion))
        return (_answer(a_defect=True, b_defect=False, preferred="B") if a == old else
                _answer(a_defect=False, b_defect=True, preferred="A"))

    result = compare(old, new, "wet road uses sparse matte cel patches", ask=ask)
    assert result["verdict"] == "candidate_better"
    assert [(a.name, b.name) for a, b, _ in called] == [("old.png", "new.png"), ("new.png", "old.png")]
    assert result["images"]["reference"]["sha256"] != result["images"]["candidate"]["sha256"]
    assert "not absolute QA" in result["scope"]


def test_forbidden_feature_direction_is_explicit_and_catches_old_inversion(tmp_path):
    old, new = _images(tmp_path)

    def ask(a, b, rule):
        # The old generic 'criterion is violated' prompt inverted a forbidden feature.
        if "Forbidden visual feature:" not in rule or "visibly PRESENT" not in rule:
            return (_answer(a_defect=False, b_defect=True, preferred="A") if a == old else
                    _answer(a_defect=True, b_defect=False, preferred="B"))
        return (_answer(a_defect=True, b_defect=False, preferred="B") if a == old else
                _answer(a_defect=False, b_defect=True, preferred="A"))

    result = compare(old, new, "broad connected glossy reflection", ask=ask, criterion_mode="forbidden")
    assert result["verdict"] == "candidate_better"
    assert result["criterion_mode"] == "forbidden"


def test_desired_feature_direction_remains_explicit(tmp_path):
    old, new = _images(tmp_path)

    def ask(a, b, rule):
        assert "Desired visual feature:" in rule
        assert "visibly ABSENT" in rule
        return (_answer(a_defect=True, b_defect=False, preferred="B") if a == old else
                _answer(a_defect=False, b_defect=True, preferred="A"))

    assert compare(old, new, "matte separated paving", ask=ask)["verdict"] == "candidate_better"


def test_position_bias_is_inconclusive_even_if_first_order_prefers_candidate(tmp_path):
    old, new = _images(tmp_path)
    result = compare(old, new, "matte road", ask=lambda *_: _answer(a_defect=True, b_defect=False, preferred="B"))
    assert result["verdict"] == "inconclusive"


def test_reference_better_is_rejected_counterexample(tmp_path):
    old, new = _images(tmp_path)

    def ask(a, b, _):
        return (_answer(a_defect=False, b_defect=True, preferred="A") if a == old else
                _answer(a_defect=True, b_defect=False, preferred="B"))

    assert compare(old, new, "matte road", ask=ask)["verdict"] == "reference_better"


def test_empty_or_identical_inputs_do_not_call_reviewer(tmp_path):
    old, new = _images(tmp_path)
    def forbidden(*_):
        raise AssertionError("should not call reviewer")
    with pytest.raises(ValueError, match="判据"):
        compare(old, new, "  ", ask=forbidden)
    with pytest.raises(ValueError, match="模式"):
        compare(old, new, "matte road", ask=forbidden, criterion_mode="ambiguous")
    new.write_bytes(old.read_bytes())
    with pytest.raises(ValueError, match="相同"):
        compare(old, new, "matte road", ask=forbidden)
    new.unlink()
    with pytest.raises(FileNotFoundError):
        compare(old, new, "matte road", ask=forbidden)


@pytest.mark.parametrize("response", [
    {"preferred": "B", "A_defect": True, "B_defect": False},
    _answer(a_defect="true", b_defect=False, preferred="B"),
    _answer(a_defect=True, b_defect=False, preferred="unknown"),
])
def test_incomplete_or_malformed_review_cannot_pass(tmp_path, response):
    old, new = _images(tmp_path)
    with pytest.raises(RuntimeError, match="缺少"):
        compare(old, new, "matte road", ask=lambda *_: response)
