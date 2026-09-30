import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stylebook.qa import plan_review as PR


def test_cover_review_is_optional_for_old_plans_but_complete_when_requested():
    plan = {"items": [], "coverage": []}
    answer = {"items": [], "missed_positions": []}
    assert PR._complete(answer, plan)
    assert "cover_review" not in PR.schema(plan)["required"]
    plan["cover_brief"] = {"content": {"subject": "文章主题"}, "text": {"mode": "none"}}
    assert not PR._complete(answer, plan)
    assert "cover_review" in PR.schema(plan)["required"]
    assert "独立封面主题复核" in PR.prompt(plan, Path("article.md"))
    valid = {**answer, "cover_review": {"fidelity_ok": True, "theme_ok": True,
                                       "no_unrequested_claims": False, "why": "测试：有额外承诺"}}
    assert PR._complete(valid, plan)  # Complete does not mean qualified.
    for key, value in [("fidelity_ok", "true"), ("why", " "), ("no_unrequested_claims", None)]:
        bad = copy.deepcopy(valid)
        bad["cover_review"][key] = value
        assert not PR._complete(bad, plan)
