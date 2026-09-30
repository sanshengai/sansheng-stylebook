"""出图调度：选服务 → 重试 → 繁忙时切备用线路 → 记成本；都不行就走收件箱。

优先级：命令行参数 > 配置文件 config.json > 环境变量 / .env。配置文件只存「用哪家、哪个模型、什么质量」，不存密钥。
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from ..contract import ROOT
from .base import CONFIG_DIR, BackendError, Result, load_dotenv, now
from .providers import PROVIDERS

LOG_DIR = Path(os.environ.get("STYLEBOOK_LOG_DIR", ROOT / "logs"))

# gpt-image-2 官方价（2026-09，美元 / 张，按质量与画幅）；其余服务未登记则不估算
PRICE = {("gpt-image", "medium", "square"): 0.053, ("gpt-image", "medium", "rect"): 0.041,
         ("gpt-image", "high", "square"): 0.211, ("gpt-image", "high", "rect"): 0.165,
         ("gpt-image", "low", "square"): 0.006, ("gpt-image", "low", "rect"): 0.005}


def config() -> dict:
    f = CONFIG_DIR / "config.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}


def save_config(cfg: dict) -> Path:
    bad = [k for k in cfg if "key" in k.lower() or "token" in k.lower() or "secret" in k.lower()]
    if bad:
        raise ValueError(f"配置文件不存密钥：{bad}；密钥只放环境变量或 .env")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    f = CONFIG_DIR / "config.json"
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f


def configured(name: str) -> bool:
    env = PROVIDERS[name]["env"][0]
    return bool(os.environ.get(env) or (name == "gemini" and os.environ.get("GOOGLE_API_KEY")))


def choose(provider: str | None = None, model: str | None = None, need_refs: bool = False) -> tuple[str, str]:
    load_dotenv()
    cfg = config()
    name = provider or cfg.get("provider")
    if not name:
        for cand in ("openai", "seedream", "dashscope", "gemini", "openrouter"):
            if configured(cand) and (PROVIDERS[cand]["refs"] or not need_refs):
                name = cand
                break
    if not name:
        raise BackendError("unconfigured", "没有可用的生图服务。运行 setup 选一家，或用 inbox 生成提示词清单到任意工具里出图。")
    if name not in PROVIDERS:
        raise BackendError("bad_request", f"未知服务 {name}，可选：{list(PROVIDERS)}")
    mdl = model or (cfg.get("model") if cfg.get("provider") == name else None) or PROVIDERS[name]["default_model"]
    return name, mdl


def _estimate(model: str, quality: str, size: tuple[int, int]) -> float | None:
    fam = "gpt-image" if model.startswith("gpt-image") else None
    if not fam:
        return None
    q = {"normal": "medium"}.get(quality, quality)
    shape = "square" if abs(size[0] - size[1]) < 16 else "rect"
    return PRICE.get((fam, q, shape))


def _log(rec: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec}
    with (LOG_DIR / "cost.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def generate(prompt: str, out: Path, *, size: tuple[int, int], aspect: str = "1:1", refs: list[Path] | None = None,
             provider: str | None = None, model: str | None = None, quality: str | None = None,
             max_attempts: int = 4, sleep=time.sleep, tag: str = "") -> Result:
    """繁忙类错误：指数退避重试；连续两次繁忙且配置了备用模型 / 线路，就切过去。密钥、组织验证、内容被拒：不重试。"""
    refs = refs or []
    name, mdl = choose(provider, model, need_refs=bool(refs))
    cfg = config()
    quality = quality or cfg.get("quality", "normal")
    fallbacks = list(cfg.get("fallback_models", [])) if name == cfg.get("provider", name) else []
    if name == "openai" and mdl == "gpt-image-2" and "gpt-image-2-c" not in fallbacks and os.environ.get("OPENAI_BASE_URL", "").find("openai.com") < 0:
        fallbacks.append("gpt-image-2-c")  # 中转的同模型备用线路（2026-09-25 核对：尺寸与内嵌来源签名一致）
    fn = PROVIDERS[name]["fn"]
    t0, attempts, busy_streak, current = now(), 0, 0, mdl
    last: BackendError | None = None
    while attempts < max_attempts:
        attempts += 1
        attempt_t0 = now()
        try:
            kwargs = {"aspect": aspect} if name in ("gemini", "openrouter") else {}
            img = fn(prompt, size, quality, refs, current, **kwargs)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(img)
            est = _estimate(current, quality, size)
            finished = now()
            seconds = round(finished - t0, 1)
            _log({"tag": tag, "provider": name, "model": current, "size": list(size), "quality": quality, "ok": True,
                  "attempts": attempts, "est_usd": est, "refs": len(refs),
                  "seconds": seconds, "attempt_seconds": round(finished - attempt_t0, 1)})
            return Result(img, name, current, attempts, seconds, est)
        except BackendError as e:
            last = e
            finished = now()
            _log({"tag": tag, "provider": name, "model": current, "ok": False, "attempts": attempts, "kind": e.kind, "msg": str(e)[:160],
                  "seconds": round(finished - t0, 1), "attempt_seconds": round(finished - attempt_t0, 1)})
            if not e.retryable:
                break
            busy_streak = busy_streak + 1 if e.kind == "busy" else 0
            if busy_streak >= 2 and fallbacks:
                current, busy_streak = fallbacks.pop(0), 0
                continue
            sleep(min(60, 2 ** attempts + random.random()))
    assert last is not None
    raise last


def inbox(tasks: list[dict], folder: Path) -> Path:
    """没有可用服务时：把每张图的提示词与参考图写成清单，用户在任意工具（即梦、豆包、ChatGPT）里出图后按文件名放回。"""
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["# 待出图清单", "", "在任意生图工具里逐张生成，图片按「文件名」保存到本文件夹，然后运行 import 导回验收。", ""]
    for t in tasks:
        lines += [f"## {t['id']}", "", f"- 文件名：`{t['id']}.png`", f"- 画幅：{t.get('aspect', '1:1')}"]
        for i, r in enumerate(t.get("references", []), 1):
            lines.append(f"- 参考图 {i}（{r.get('role')}）：`{r.get('path')}`")
        lines += ["", "```", t["prompt"], "```", ""]
    f = folder / "待出图清单.md"
    f.write_text("\n".join(lines), encoding="utf-8")
    return f
