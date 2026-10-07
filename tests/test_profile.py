import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import plan as PL  # noqa: E402
from stylebook import profile as P  # noqa: E402
from stylebook import contract as CT  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("SANSHENG_IMAGE_PROFILE", str(tmp_path / "profile"))


def test_explicit_missing_profile_does_not_fall_back_to_host(tmp_path, monkeypatch):
    default = tmp_path / ".config" / "sansheng-image" / "profile"
    default.mkdir(parents=True)
    monkeypatch.setattr(CT.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("SANSHENG_IMAGE_PROFILE", str(tmp_path / "missing"))
    assert CT.profile_dir() is None
    assert PL.resolve_style("wxillus")["code"] == "C24"
    monkeypatch.delenv("SANSHENG_IMAGE_PROFILE")
    assert CT.profile_dir() == default


def test_explicit_preference_persists_without_overwriting_existing_author(tmp_path):
    root = tmp_path / "profile"
    root.mkdir()
    old = {"version": 1, "scene_defaults": {"wxillus": {"default": "C08", "alternates": ["C31"]}},
           "preferences": {"likes": ["soft"]}, "edits": []}
    (root / "author.json").write_text(json.dumps(old), encoding="utf-8")
    before = PL.resolve_style("wxillus")
    assert before["code"] == "C08"
    event = P.set_explicit("style", "C31", scene="wxillus")
    P.set_explicit("palette", {"family": "macaron", "light": 1, "sat": -1}, scene="wxillus")
    after = PL.resolve_style("wxillus")
    assert after["code"] == "C31" and after["source"] == "preference"
    assert after["palette"] == {"family": "macaron", "light": 1, "sat": -1}
    assert json.loads((root / "author.json").read_text()) == old
    assert P.lookup("style", scene="wxillus")["evidence"] == [event["id"]]
    assert PL.resolve_style("wxillus", explicit="C25")["code"] == "C25"
    assert PL.resolve_style("wxillus")["code"] == "C31"  # 本次指定不改长期设置
    P.revoke(event["id"])
    assert PL.resolve_style("wxillus")["code"] == "C08"


def test_three_independent_active_tasks_learn_only_consistent_tendency():
    for task in ("article-1", "article-2"):
        P.record_change("style", "C31", scene="wxillus", task_id=task, candidates=["C08", "C31"])
    assert P.lookup("style", scene="wxillus") is None
    P.record_change("style", "C31", scene="wxillus", task_id="article-2", candidates=["C08", "C31"])
    assert P.lookup("style", scene="wxillus") is None  # 同任务重复只计一次
    third = P.record_change("style", "C31", scene="wxillus", task_id="article-3", candidates=["C08", "C31"])
    assert P.lookup("style", scene="wxillus")["source"] == "observed"
    assert len(P.lookup("style", scene="wxillus")["evidence"]) == 3
    P.record_change("style", "C08", scene="wxillus", task_id="article-4", candidates=["C08", "C31"])
    assert P.lookup("style", scene="wxillus") is None  # 相反反馈暂停推断
    P.forget(third["id"])
    assert third["id"] in P.read()["forgotten_ids"]
    assert all(event["id"] != third["id"] for event in P.read()["events"])
    with pytest.raises(P.ProfileError, match="已被忘记"):
        P.record_change("style", "C31", scene="wxillus", task_id="article-3", candidates=["C31"], event_id=third["id"])


def test_correctness_and_paused_learning_do_not_record():
    assert P.record_change("style", "C31", scene="wxillus", task_id="a", candidates=["C31"], reason="correctness") is None
    P.pause(True)
    assert P.record_change("style", "C31", scene="wxillus", task_id="b", candidates=["C31"]) is None
    assert P.read()["events"] == []
    P.pause(False)
    with pytest.raises(P.ProfileError, match="实际展示"):
        P.record_change("style", "C31", scene="wxillus", task_id="c", candidates=["C08"])


def test_invalid_profile_and_concurrent_writes_fail_safely(tmp_path):
    root = tmp_path / "profile"
    root.mkdir()
    (root / "memory.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(P.ProfileError, match="无法读取"):
        P.read()
    fallback = PL.resolve_style("wxillus", explicit="C31")
    assert fallback["code"] == "C31" and "warning" in fallback
    assert PL.resolve_style("wxillus")["source"] == "factory"
    (root / "memory.json").unlink()

    def write(index):
        P.set_explicit("style", "C31", scene="wxillus", event_id=f"task-{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(20)))
    assert len(P.read()["events"]) == 20
    write(5)
    assert len(P.read()["events"]) == 20
    assert P.lookup("style", scene="wxillus")["value"] == "C31"


def test_project_scope_and_brand_colour_validation():
    P.set_explicit("style", "C31", scene="wxillus")
    P.set_explicit("style", "C25", scene="wxillus", project="paper-a")
    assert P.lookup("style", scene="wxillus", project="paper-a")["value"] == "C25"
    assert P.lookup("style", scene="wxillus", project="paper-b")["value"] == "C31"
    with pytest.raises(P.ProfileError, match="品牌色"):
        P.set_explicit("palette", {"family": "brand", "light": 0, "sat": 0}, scene="wxillus")
    colour = P.set_explicit("palette", {"family": "brand", "custom": ["#abcd12"]}, scene="wxillus")
    assert colour["value"]["custom"] == ["#ABCD12"]


def test_style_for_reports_admission_without_implying_scene_acceptance(tmp_path):
    def run(*args):
        cp = subprocess.run([sys.executable, str(ROOT / "scripts" / "sb.py"), "style-for", *args],
                            capture_output=True, text=True, check=True,
                            env={**os.environ, "SANSHENG_IMAGE_PROFILE": str(tmp_path / "fresh-profile")})
        return json.loads(cp.stdout)

    pending = run("wxillus")
    assert pending["code"] == "C24" and pending["use"] == "文章插图" and pending["admission"] == "pending"
    assert "尚未正式准入" in pending["admission_note"]
    demoted = run("ppt", "--explicit", "C32")  # C32 曾在 r4 通过准入，r5 换配方后待复测
    assert demoted["admission"] == "pending" and "尚未正式准入" in demoted["admission_note"]


def test_inferred_project_evidence_does_not_leak_to_another_project():
    for task in ("one", "two", "three"):
        P.record_change("style", "C31", scene="wxillus", project="project-a", task_id=task,
                        candidates=["C08", "C31"])
    assert P.lookup("style", scene="wxillus", project="project-a")["source"] == "observed"
    assert P.lookup("style", scene="wxillus", project="project-b") is None
    assert P.lookup("style", scene="wxillus") is None


def test_export_import_conflict_and_forgetting(tmp_path, monkeypatch):
    first = P.set_explicit("style", "C31", scene="wxillus")
    bundle = tmp_path / "export.json"
    P.export_to(bundle)
    with pytest.raises(P.ProfileError, match="已存在"):
        P.export_to(bundle)
    monkeypatch.setenv("SANSHENG_IMAGE_PROFILE", str(tmp_path / "second"))
    P.set_explicit("style", "C25", scene="wxillus")
    with pytest.raises(P.ProfileError, match="明确偏好冲突"):
        P.import_from(bundle)
    assert P.lookup("style", scene="wxillus")["value"] == "C25"
    assert P.import_from(bundle, replace_conflicts=True)["imported"] == 1
    assert P.lookup("style", scene="wxillus")["value"] == "C31"
    P.forget(first["id"])
    assert P.lookup("style", scene="wxillus")["value"] == "C25"
    assert P.import_from(bundle, replace_conflicts=True)["imported"] == 0
    assert P.lookup("style", scene="wxillus")["value"] == "C25"


def test_preferences_cli_persists_between_processes(tmp_path):
    env = {**os.environ, "SANSHENG_IMAGE_PROFILE": str(tmp_path / "cli-profile")}
    def cli(*args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "sb.py"), *args], env=env,
                              cwd=ROOT, text=True, capture_output=True, check=True).stdout
    event = json.loads(cli("preferences", "set", "--scene", "wxillus", "--field", "style", "--value", "C31"))
    assert json.loads(cli("style-for", "wxillus"))["source"] == "preference"
    assert json.loads(cli("preferences", "show", "--scene", "wxillus"))["effective"]["style"]["value"] == "C31"
    cli("preferences", "undo", "--event-id", event["id"])
    assert json.loads(cli("style-for", "wxillus"))["source"] == "factory"
