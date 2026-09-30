"""成长飞轮：3 个不同任务同向才问；同一任务重复不算；拒绝 60 天内不再问；确认才写默认。"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import flywheel as FW  # noqa: E402
from stylebook import profile as P  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("STYLEBOOK_PROFILE", str(tmp_path / "profile"))
    return tmp_path


def choose(task, value="C19", scene="wxcover"):
    return FW.capture_choice("style", value, scene=scene, task_id=task, candidates=["C30", value])


def test_three_distinct_tasks_same_direction_ask_once():
    choose("a"); choose("b")
    assert FW.pending("wxcover") == []
    choose("c")
    q = FW.pending("wxcover")
    assert len(q) == 1 and q[0]["value"] == "C19" and "要设成默认吗" in q[0]["question"] and "封面" in q[0]["question"]


def test_same_task_repeated_counts_once_and_mixed_direction_never_asks():
    for _ in range(4):
        choose("only-one-task")
    assert FW.pending("wxcover") == []
    choose("b", "C01"); choose("c", "C19"); choose("d", "C01")
    assert FW.pending("wxcover") == []  # 方向不一致


def test_confirming_sets_explicit_default_and_stops_asking():
    for t in "abc":
        choose(t)
    q = FW.pending("wxcover")[0]
    FW.answer(q["scope"], q["field"], q["value"], "default")
    assert P.lookup("style", scene="wxcover", include_inferred=False)["value"] == "C19"
    assert FW.pending("wxcover") == []


def test_declined_is_silent_for_60_days_then_asks_again():
    for t in "abc":
        choose(t)
    q = FW.pending("wxcover")[0]
    FW.answer(q["scope"], q["field"], q["value"], "no")
    assert FW.pending("wxcover") == []
    path = P.profile_path()
    data = json.loads(path.read_text())
    old = (datetime.now(timezone.utc) - timedelta(days=61)).isoformat()
    for e in data["events"]:
        if e["kind"] == "declined":
            e["at"] = old
    path.write_text(json.dumps(data))
    assert len(FW.pending("wxcover")) == 1


def test_project_scoped_answer_needs_project_and_paused_never_asks():
    for t in "abc":
        choose(t)
    q = FW.pending("wxcover")[0]
    with pytest.raises(P.ProfileError):
        FW.answer({"scene": "wxcover"}, "style", "C19", "project")
    P.pause(True)
    assert FW.pending("wxcover") == []


def fake_report(code="C19@r2", status="pending_visual_review", source="factory"):
    return {"selection": {"code": code, "source": source}, "items": [{"id": "01", "status": status}]}


def test_after_make_captures_only_user_choices_and_failures(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    agent = FW.after_make({"scene": "wxcover", "source": None}, fake_report(), out)
    assert agent["captured"] == 0  # Agent 自己挑的画风不算用户偏好
    user = FW.after_make({"scene": "wxcover", "chosen_by": "user"}, fake_report(), out)
    assert user["captured"] == 1
    same = FW.after_make({"scene": "wxcover", "chosen_by": "user"}, fake_report("C30@r1"), out)
    assert same["captured"] == 0  # 选的就是推荐值，不是改选
    failed = FW.after_make({"scene": "wxcover"}, fake_report(status="pixel_failed"), out)
    assert failed["captured"] == 1 and FW.ledger()["封面|C19"]["fix"] == 1


def test_stall_warning_after_five_silent_tasks_and_cleared_by_a_record(tmp_path):
    for i in range(5):
        FW.record_task(f"t{i}", "wxcover", 0)
    assert FW.stalled() and "飞轮可能断了" in FW.status()["note"]
    FW.record_task("t5", "wxcover", 1)
    assert not FW.stalled()


def test_accept_builds_use_by_style_ledger(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "report.json").write_text(json.dumps(fake_report("C30@r2")))
    (out / "brief.json").write_text(json.dumps({"scene": "wxcover", "source": "a.md"}))
    FW.accept(out)
    FW.accept(out, ["01"])
    assert FW.ledger()["封面|C30"]["accept"] == 2
