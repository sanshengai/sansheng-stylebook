import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture()
def B(tmp_path, monkeypatch):
    for k in ("GOOGLE_BASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ARK_API_KEY", "ARK_BASE_URL", "DASHSCOPE_API_KEY",
              "DASHSCOPE_BASE_URL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)  # 本机真实环境里可能设着这些，测试必须隔离
    monkeypatch.setenv("SANSHENG_IMAGE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("SANSHENG_IMAGE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://relay.example.com/v1")
    monkeypatch.chdir(tmp_path)
    import stylebook.backends.base as base
    importlib.reload(base)
    import stylebook.backends.providers as prov
    importlib.reload(prov)
    import stylebook.backends as b
    importlib.reload(b)
    return b


def test_busy_switches_to_backup_line(B, tmp_path, monkeypatch):
    calls = []

    def fake(prompt, size, quality, refs, model, **kw):
        calls.append(model)
        if model == "gpt-image-2":
            raise B.BackendError("busy", "系统繁忙，请稍后再试", retryable=True, status=500)
        return b"PNG"
    monkeypatch.setitem(B.PROVIDERS["openai"], "fn", fake)
    r = B.generate("p", tmp_path / "o.png", size=(1024, 1024), sleep=lambda s: None)
    assert r.model == "gpt-image-2-c" and calls == ["gpt-image-2", "gpt-image-2", "gpt-image-2-c"]
    assert (tmp_path / "o.png").read_bytes() == b"PNG"
    log = (tmp_path / "logs" / "cost.jsonl").read_text()
    assert '"ok": true' in log and '"kind": "busy"' in log


def test_auth_error_not_retried(B, tmp_path, monkeypatch):
    n = []

    def fake(*a, **k):
        n.append(1)
        raise B.BackendError("auth", "密钥无效", status=401)
    monkeypatch.setitem(B.PROVIDERS["openai"], "fn", fake)
    with pytest.raises(B.BackendError) as e:
        B.generate("p", tmp_path / "o.png", size=(1024, 1024), sleep=lambda s: None)
    assert e.value.kind == "auth" and len(n) == 1


def test_request_log_records_attempt_and_total_elapsed_including_backoff(B, tmp_path, monkeypatch):
    clock = iter([100.0, 100.0, 102.0, 107.0, 110.0])
    monkeypatch.setattr(B, "now", lambda: next(clock))
    calls = []

    def fake(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise B.BackendError("busy", "busy", retryable=True)
        return b"PNG"

    monkeypatch.setitem(B.PROVIDERS["openai"], "fn", fake)
    result = B.generate("p", tmp_path / "timed.png", size=(1024, 1024), sleep=lambda _: None)
    records = [json.loads(line) for line in (tmp_path / "logs" / "cost.jsonl").read_text().splitlines()]
    assert [(r["ok"], r["attempt_seconds"], r["seconds"]) for r in records] == [
        (False, 2.0, 2.0), (True, 3.0, 10.0)]
    assert result.seconds == records[-1]["seconds"] == 10.0


def test_terminal_failure_logs_elapsed(B, tmp_path, monkeypatch):
    clock = iter([20.0, 20.0, 23.5])
    monkeypatch.setattr(B, "now", lambda: next(clock))

    def fail(*args, **kwargs):
        raise B.BackendError("auth", "invalid", retryable=False)

    monkeypatch.setitem(B.PROVIDERS["openai"], "fn", fail)
    with pytest.raises(B.BackendError):
        B.generate("p", tmp_path / "failed.png", size=(1024, 1024))
    record = json.loads((tmp_path / "logs" / "cost.jsonl").read_text())
    assert record["seconds"] == record["attempt_seconds"] == 3.5
    assert not (tmp_path / "failed.png").exists()


def test_config_refuses_secrets(B):
    with pytest.raises(ValueError, match="不存密钥"):
        B.save_config({"provider": "openai", "api_key": "x"})
    assert B.save_config({"provider": "openai", "model": "gpt-image-2"}).exists()


def test_classify():
    from stylebook.backends.base import classify
    assert classify(403, '{"error":"organization must be verified"}').kind == "verify"
    assert classify(500, "系统繁忙，请稍后再试").kind == "busy"
    assert classify(429, "rate").kind == "busy"
    assert classify(400, "rejected by safety system").kind == "policy"
    assert classify(401, "").kind == "auth"
    assert classify(400, "bad size").kind == "bad_request"


def test_redact():
    from stylebook.backends.base import redact
    assert redact("https://user:pass@api.example.com:8443/v1/x?key=SECRET#f") == "https://api.example.com:8443"


def test_inbox(B, tmp_path):
    f = B.inbox([{"id": "p01", "prompt": "hello", "aspect": "3:4", "references": [{"path": "a.png", "role": "style"}]}], tmp_path / "inbox")
    t = f.read_text()
    assert "`p01.png`" in t and "hello" in t and "参考图 1（style）" in t


def test_request_shapes(B, monkeypatch, tmp_path):
    import stylebook.backends.providers as P
    seen = {}

    def cap(url, payload, headers, timeout=300):
        seen.update(url=url, payload=payload, headers=headers)
        return {"data": [{"b64_json": "UE5H"}], "candidates": [{"content": {"parts": [{"inlineData": {"data": "UE5H"}}]}}],
                "choices": [{"message": {"images": [{"image_url": {"url": "data:image/png;base64,UE5H"}}]}}]}
    monkeypatch.setattr(P, "post_json", cap)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert P.gemini_generate("x", (1024, 1024), "normal", [], "gemini-3.1-flash-image", aspect="3:4") == b"PNG"
    assert seen["url"].endswith("/models/gemini-3.1-flash-image:generateContent") and seen["headers"]["x-goog-api-key"] == "g"
    assert seen["payload"]["generationConfig"]["imageConfig"]["aspectRatio"] == "3:4"
    monkeypatch.setenv("GOOGLE_BASE_URL", "https://aiplatform.googleapis.com/v1/publishers/google")
    P.gemini_generate("x", (1024, 1024), "normal", [], "gemini-3-pro-image")
    assert "aiplatform" in seen["url"] and "key=g" in seen["url"]
    monkeypatch.setenv("ARK_API_KEY", "a")
    P.seedream_generate("x", (1152, 1536), "normal", [], "doubao-seedream-4-0-250828")
    assert seen["payload"]["size"] == "1152x1536" and seen["payload"]["watermark"] is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    P.openrouter_generate("x", (1024, 1024), "normal", [], "google/gemini-3.1-flash-image")
    assert seen["payload"]["modalities"] == ["image", "text"]
    P.openai_generate("x", (1536, 864), "normal", [], "gpt-image-2")
    assert seen["url"] == "https://relay.example.com/v1/images/generations" and seen["payload"]["quality"] == "medium"
    assert seen["payload"]["size"] == "1536x864"


def test_unconfigured_message(B, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ARK_API_KEY", "DASHSCOPE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(B.BackendError) as e:
        B.choose()
    assert e.value.kind == "unconfigured" and "inbox" in str(e.value)


def test_policy_block_wrapped_as_429_is_not_retried():
    from stylebook.backends.base import classify
    body = '{"error":{"message":"We’re so sorry, but the prompt may violate our content policies. (request id: x)"}}'
    e = classify(429, body)
    assert e.kind == "policy" and not e.retryable
    assert classify(429, '{"error":"rate limit"}').kind == "busy"
    assert classify(400, '{"error":{"code":"content_policy_violation"}}').kind == "policy"
