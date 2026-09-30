import copy
import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import make as MK, profile as P  # noqa: E402
from stylebook.backends.base import Result  # noqa: E402

BRIEF = {"version": 1, "scene": "wxillus", "style": "C42", "reason": "清楚表现文章中的选择",
         "items": [{"position": "段落之后", "message": "两个方案有不同用途", "visual": "Two cards on a table", "text": []}]}


@pytest.fixture(autouse=True)
def private_preferences_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("STYLEBOOK_PREFERENCES", str(tmp_path / "prefs.json"))
    monkeypatch.setenv("STYLEBOOK_PROFILE", str(tmp_path / "absent-profile"))
    monkeypatch.setattr(P, "lookup", lambda *args, **kwargs: None)


def fake_generate(prompt, out, *, size, **kwargs):
    Image.new("RGB", size, "ivory").save(out)
    return Result(b"", "test", "test-image", 1, 0.1, None)


@pytest.mark.parametrize("change", [lambda b: b.update(items=[]),
                                  lambda b: b["items"][0].update(id="../escape"),
                                  lambda b: b["items"][0].update(visual=""),
                                  lambda b: b.update(palette="blue"),
                                  lambda b: b.update(scene="invalid"),
                                  lambda b: b.update(unrecognized=True)])
def test_invalid_brief_rejected_before_generation_or_output(tmp_path, change):
    brief = copy.deepcopy(BRIEF)
    change(brief)
    with pytest.raises(MK.BriefError):
        MK.run(brief, tmp_path / "out", base_path=tmp_path, gen_fn=fake_generate)
    assert not (tmp_path / "out").exists()


def test_source_quote_must_exist_and_source_is_bound(tmp_path):
    source = tmp_path / "article.md"
    source.write_text("段落之后", encoding="utf-8")
    brief = {**copy.deepcopy(BRIEF), "source": source.name}
    prepared = MK.prepare(brief, base_path=tmp_path)
    assert prepared["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    brief["items"][0]["position"] = "不存在的句子"
    with pytest.raises(MK.BriefError, match="原文"):
        MK.prepare(brief, base_path=tmp_path)


def test_user_reference_resolves_relative_to_brief_and_overrides_style_anchor(tmp_path):
    reference = tmp_path / "chosen.png"
    Image.new("RGB", (32, 32), "ivory").save(reference)
    brief = {**copy.deepcopy(BRIEF), "references": [{"role": "style", "path": reference.name}]}
    task = MK.prepare(brief, base_path=tmp_path)["tasks"][0]
    assert len(task["references"]) == 1
    assert task["references"][0]["path"] == str(reference)
    assert task["references"][0]["sha256"] == hashlib.sha256(reference.read_bytes()).hexdigest()


def test_code_overrides_style_and_palette(tmp_path):
    from stylebook import stylecode
    code = stylecode.StyleCode(style="C42", palette="orig", light=0, sat=0)
    # Use the actual encoder rather than guessing the wire format.
    encoded = code.format()
    prepared = MK.prepare({**BRIEF, "style": "C31", "code": encoded}, base_path=tmp_path)
    assert prepared["selection"]["source"] == "code"
    assert prepared["tasks"][0]["manifest"]["style"].startswith("C42@r")


def test_lightweight_uses_only_confirmed_preferences(tmp_path, monkeypatch):
    calls = []
    def lookup(field, **kwargs):
        calls.append(kwargs["include_inferred"])
        return {"value": "C42", "source": "explicit_memory", "evidence": ["confirmed"]} if field == "style" else None
    monkeypatch.setattr(P, "lookup", lookup)
    brief = copy.deepcopy(BRIEF)
    brief.pop("style")
    prepared = MK.prepare(brief, base_path=tmp_path)
    assert calls and all(v is False for v in calls)
    assert prepared["selection"]["source"] == "preference"


def test_parallel_group_export_and_receipts_never_claim_visual_acceptance(tmp_path):
    brief = copy.deepcopy(BRIEF)
    brief["items"] *= 4
    barrier = threading.Barrier(4)
    def gen(*args, **kwargs):
        barrier.wait(timeout=5)
        return fake_generate(*args, **kwargs)
    report = MK.run(brief, tmp_path / "out", base_path=tmp_path, gen_fn=gen)
    assert report["status"] == "pending_visual_review" and report["failed"] == 0
    assert report["accepted"] is False and report["visual_review"] == "not_run"
    for rec in report["items"]:
        assert rec["pixel_check"]["passed"]
        assert rec["final_sha256"] == hashlib.sha256(Path(rec["final"]).read_bytes()).hexdigest()
        assert not rec["accepted"]
    assert Path(report["overview"]).is_file()


def test_single_generation_failure_preserves_other_results(tmp_path):
    brief = copy.deepcopy(BRIEF)
    brief["items"] = [{**brief["items"][0], "id": "broken"}, {**brief["items"][0], "id": "good"}]
    def gen(prompt, out, **kwargs):
        if out.name.startswith("broken"):
            raise RuntimeError("provider unavailable")
        return fake_generate(prompt, out, **kwargs)
    report = MK.run(brief, tmp_path / "out", base_path=tmp_path, gen_fn=gen)
    assert report["status"] == "failed" and report["failed"] == 1
    assert report["items"][1]["status"] == "pending_visual_review"
    assert (tmp_path / "out" / "broken-receipt.json").is_file()


def test_existing_output_never_overwritten(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    sentinel = out / "prior.json"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        MK.run(BRIEF, out, base_path=tmp_path, gen_fn=fake_generate)
    assert sentinel.read_text() == "keep"


def test_source_mutation_during_generation_invalidates_group(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("段落之后", encoding="utf-8")
    brief = {**copy.deepcopy(BRIEF), "source": source.name}
    def gen(*args, **kwargs):
        source.write_text("changed", encoding="utf-8")
        return fake_generate(*args, **kwargs)
    report = MK.run(brief, tmp_path / "out", base_path=tmp_path, gen_fn=gen)
    assert report["status"] == "failed" and not report["source_unchanged"]


def test_reference_mutation_keeps_raw_but_rejects_candidate(tmp_path, monkeypatch):
    reference = tmp_path / "ref.png"
    Image.new("RGB", (32, 32), "white").save(reference)
    compile_real = MK.CP.compile_manifest
    def compile_with_reference(manifest):
        compiled = compile_real(manifest)
        compiled.references = [{"role": "style", "path": str(reference)}]
        return compiled
    monkeypatch.setattr(MK.CP, "compile_manifest", compile_with_reference)
    def gen(*args, **kwargs):
        result = fake_generate(*args, **kwargs)
        Image.new("RGB", (32, 32), "black").save(reference)
        return result
    report = MK.run(BRIEF, tmp_path / "out", base_path=tmp_path, gen_fn=gen)
    assert report["status"] == "failed"
    assert "参考图" in report["items"][0]["error"]["message"]
    assert (tmp_path / "out/01-raw.png").is_file()
    assert not (tmp_path / "out/01.png").exists()


def test_auth_failure_stops_queued_requests(tmp_path):
    from stylebook.backends.base import BackendError
    brief = copy.deepcopy(BRIEF)
    brief["items"] *= 5
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise BackendError("auth", "invalid", retryable=False)
    report = MK.run(brief, tmp_path / "out", base_path=tmp_path, gen_fn=fail, jobs=1)
    assert len(calls) == 1 and report["failed"] == 5


def test_cli_prepare_has_no_generation_and_binds_reference_files(tmp_path):
    brief_path = tmp_path / "brief.json"
    brief_path.write_text(json.dumps(BRIEF))
    out = tmp_path / "out"
    run = subprocess.run([sys.executable, str(ROOT / "scripts/sb.py"), "make", str(brief_path),
                          "-o", str(out), "--prepare"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["status"] == "pending_host" and report["accepted"] is False
    assert not list(out.glob("*-raw.png"))
    prepared = json.loads((out / "prepared.json").read_text())
    for ref in prepared["tasks"][0]["references"]:
        assert ref["sha256"] == hashlib.sha256(Path(ref["path"]).read_bytes()).hexdigest()
