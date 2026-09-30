"""Codex 内置生图后端：用假的 codex 命令验证参数顺序、画幅、错误分类、付费备用的开关与上限。"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import backends as B  # noqa: E402
from stylebook.backends import providers as P  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20_000

FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys
args = sys.argv[1:]
log = os.environ["FAKE_CODEX_LOG"]
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT"); sys.exit(0)
if args and args[0] == "exec":
    args = args[1:]
positional, images, i = [], [], 0
while i < len(args):
    a = args[i]
    if a in ("-s", "-C", "-c", "-m", "-p"):
        i += 2; continue
    if a == "-i":            # 真实 codex：-i 之后的非选项参数都被当成图片文件
        i += 1
        while i < len(args) and not args[i].startswith("-"):
            images.append(args[i]); i += 1
        continue
    if a.startswith("-"):
        i += 1; continue
    positional.append(a); i += 1
json.dump({"args": args, "prompt": positional[-1] if positional else None, "images": images}, open(log, "a"))
open(log, "a").write("\n")
mode = os.environ.get("FAKE_CODEX_MODE", "ok")
if not positional:
    print("error: no prompt", file=sys.stderr); sys.exit(2)
if mode == "quota":
    print("You have hit your usage limit", file=sys.stderr); sys.exit(1)
if mode == "silent":
    print("done"); sys.exit(0)
out = re.search(r"to (\S+out\.png)", positional[-1]).group(1)
open(out, "wb").write(bytes.fromhex("89504e470d0a1a0a") + b"0" * 20000)
print("tokens used\n12,345")
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    exe = tmp_path / "codex"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("STYLEBOOK_CODEX", str(exe))
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    monkeypatch.setenv("STYLEBOOK_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(B, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(B, "config", lambda: {})
    P._CODEX_LOGIN.clear()
    return log


def calls(log):
    return [json.loads(x) for x in log.read_text().splitlines() if x.strip().startswith("{")]


def test_prompt_precedes_image_flag_and_aspect_is_requested(fake, tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG)
    img = P.codex_generate("A calm lake. Image 1: style only.", (1880, 800), "normal", [ref], "codex-builtin", aspect="2.35:1")
    assert img.startswith(b"\x89PNG")
    call = calls(fake)[-1]
    assert call["images"] == [str(ref)], "参考图必须被识别为图片"
    assert call["prompt"] and "aspect ratio 2.35:1" in call["prompt"] and "A calm lake" in call["prompt"]
    assert call["args"].index("-i") > max(i for i, a in enumerate(call["args"]) if "A calm lake" in a)  # -i 在提示词之后
    assert P.META.tokens == 12345


def test_missing_prompt_would_fail_if_image_flag_came_first(fake, tmp_path):
    """反例：把 -i 放在提示词前面，假 codex（与真实行为一致）吞掉提示词并报错。"""
    import subprocess
    ref = tmp_path / "r.png"
    ref.write_bytes(PNG)
    r = subprocess.run([os.environ["STYLEBOOK_CODEX"], "exec", "-i", str(ref), "make an image"], capture_output=True, text=True,
                       env={**os.environ})
    assert r.returncode == 2


def test_quota_and_silent_failures_are_classified(fake, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_MODE", "quota")
    with pytest.raises(Exception) as e:  # 其他测试可能重载后端模块，按属性判断而不是按类
        P.codex_generate("x", (1024, 1024), "normal", [], "codex-builtin")
    assert e.value.kind == "quota" and not e.value.retryable
    monkeypatch.setenv("FAKE_CODEX_MODE", "silent")
    with pytest.raises(Exception) as e:  # 其他测试可能重载后端模块，按属性判断而不是按类
        P.codex_generate("x", (1024, 1024), "normal", [], "codex-builtin")
    assert e.value.kind == "unknown" and e.value.retryable


def test_auto_choice_prefers_codex_when_ready(fake, monkeypatch):
    for k in ("OPENAI_API_KEY",):
        monkeypatch.delenv(k, raising=False)
    assert B.choose(None, None)[0] == "codex"
    assert B.choose("openai", None)[0] == "openai"


def test_generate_writes_image_and_logs_tokens(fake, tmp_path):
    out = tmp_path / "o.png"
    r = B.generate("hello", out, size=(1024, 1024), aspect="1:1", tag="t")
    assert r.provider == "codex" and r.est_usd is None and out.read_bytes().startswith(b"\x89PNG")
    rec = json.loads((tmp_path / "logs" / "cost.jsonl").read_text().splitlines()[-1])
    assert rec["provider"] == "codex" and rec["tokens"] == 12345 and rec["est_usd"] is None


def test_paid_fallback_is_off_by_default_and_capped(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_MODE", "quota")
    out = tmp_path / "o.png"
    with pytest.raises(Exception):  # 其他测试可能重载后端模块，按属性判断而不是按类  # 默认不退到付费服务
        B.generate("hello", out, size=(1024, 1024), tag="t")
    calls_paid = []
    monkeypatch.setitem(P.PROVIDERS["openai"], "fn", lambda *a, **k: calls_paid.append(1) or PNG)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(B, "config", lambda: {"allow_paid_fallback": True, "paid_fallback_cap_usd": 1})
    r = B.generate("hello", out, size=(1024, 1024), tag="t")
    assert r.provider == "openai" and calls_paid
    log = [json.loads(x) for x in (tmp_path / "logs" / "cost.jsonl").read_text().splitlines()]
    assert any(x.get("fallback_to") == "openai" for x in log)
    # 当天估算花费达到上限后不再退到付费服务
    (tmp_path / "logs" / "cost.jsonl").write_text(json.dumps({"at": B.datetime.now(B.timezone.utc).isoformat(), "ok": True, "est_usd": 5.0}) + "\n")
    with pytest.raises(Exception):  # 其他测试可能重载后端模块，按属性判断而不是按类
        B.generate("hello", out, size=(1024, 1024), tag="t")
    # 用户明确指定了服务时不做自动备用
    monkeypatch.setattr(B, "_spent_today", lambda: 0.0)
    with pytest.raises(Exception):  # 其他测试可能重载后端模块，按属性判断而不是按类
        B.generate("hello", out, size=(1024, 1024), provider="codex", tag="t")
