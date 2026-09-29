"""各家生图服务的适配。每家只做一件事：把（提示词、尺寸、质量、参考图）变成请求，把响应变成图片字节。

实测状态写在 PROVIDERS[...]["verified"]；未实测的按官方文档实现，doctor 会如实标注。
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from .base import BackendError, fetch_bytes, get, post_json, post_multipart


def _need(env: str, label: str) -> str:
    v = os.environ.get(env)
    if not v:
        raise BackendError("unconfigured", f"没有配置 {label} 的密钥（环境变量 {env}）。运行 setup 看申请与设置方法。")
    return v


def _decode(item: dict) -> bytes:
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return fetch_bytes(item["url"])
    raise BackendError("unknown", "响应里没有图片")


# ---------------- OpenAI 与 OpenAI 兼容中转 ----------------
def openai_generate(prompt: str, size: tuple[int, int], quality: str, refs: list[Path], model: str) -> bytes:
    key = _need("OPENAI_API_KEY", "OpenAI / 中转")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    q = {"normal": "medium", "high": "high", "low": "low"}.get(quality, quality)
    sz = f"{size[0]}x{size[1]}"
    headers = {"Authorization": f"Bearer {key}"}
    if refs:
        data = post_multipart(f"{base}/images/edits", {"model": model, "prompt": prompt, "size": sz, "quality": q},
                              [("image[]", p) for p in refs], headers)
    else:
        data = post_json(f"{base}/images/generations", {"model": model, "prompt": prompt, "size": sz, "quality": q, "n": 1}, headers)
    if not data.get("data"):
        raise BackendError("unknown", "响应里没有 data")
    return _decode(data["data"][0])


def openai_ping() -> tuple[bool, str]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False, "未配置"
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    status, raw = get(f"{base}/models", {"Authorization": f"Bearer {key}"})
    if status >= 400:
        why = {401: "密钥无效或已过期", 403: "没有权限（官方接口可能需要先做组织验证）", 404: "地址不对（检查 OPENAI_BASE_URL 是否以 /v1 结尾）"}.get(status, "被服务方拒绝")
        return False, f"{why}（{status}）"
    txt = raw.decode("utf-8", "replace")
    return True, "能列出模型" + ("，含 gpt-image" if "gpt-image" in txt else "，但清单里没有 gpt-image")


# ---------------- Google Gemini（AI Studio / Vertex Express） ----------------
def _gemini_url(model: str) -> tuple[str, dict]:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise BackendError("unconfigured", "没有配置 Google 的密钥（GEMINI_API_KEY 或 GOOGLE_API_KEY）。")
    base = os.environ.get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    if "aiplatform" in base:  # Vertex Express：key 走查询参数
        return f"{base}/models/{model}:generateContent?key={key}", {}
    return f"{base}/models/{model}:generateContent", {"x-goog-api-key": key}


def gemini_generate(prompt: str, size: tuple[int, int], quality: str, refs: list[Path], model: str, aspect: str = "1:1") -> bytes:
    url, headers = _gemini_url(model)
    parts: list[dict] = []
    for p in refs:
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(p.read_bytes()).decode()}})
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    data = post_json(url, body, headers)
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise BackendError("policy" if data.get("promptFeedback") else "unknown", f"Gemini 没有返回图片：{str(data)[:200]}")


# ---------------- OpenRouter ----------------
def openrouter_generate(prompt: str, size: tuple[int, int], quality: str, refs: list[Path], model: str, aspect: str = "1:1") -> bytes:
    key = _need("OPENROUTER_API_KEY", "OpenRouter")
    content: list[dict] = [{"type": "text", "text": prompt}]
    for p in refs:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()}})
    body = {"model": model, "messages": [{"role": "user", "content": content}], "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": aspect}}
    data = post_json("https://openrouter.ai/api/v1/chat/completions", body, {"Authorization": f"Bearer {key}"})
    for ch in data.get("choices", []):
        for img in (ch.get("message") or {}).get("images", []) or []:
            url = (img.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                return base64.b64decode(url.split(",", 1)[1])
            if url:
                return fetch_bytes(url)
    raise BackendError("unknown", f"OpenRouter 没有返回图片：{str(data)[:200]}")


# ---------------- 火山方舟 Seedream（即梦同源） ----------------
def seedream_generate(prompt: str, size: tuple[int, int], quality: str, refs: list[Path], model: str) -> bytes:
    key = _need("ARK_API_KEY", "火山方舟 Seedream")
    base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    body = {"model": model, "prompt": prompt, "size": f"{size[0]}x{size[1]}", "response_format": "b64_json", "watermark": False}
    if refs:
        body["image"] = ["data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() for p in refs]
    data = post_json(f"{base}/images/generations", body, {"Authorization": f"Bearer {key}"})
    if not data.get("data"):
        raise BackendError("unknown", f"Seedream 没有返回图片：{str(data)[:200]}")
    return _decode(data["data"][0])


# ---------------- 阿里云百炼（通义万相 / Qwen-Image） ----------------
def dashscope_generate(prompt: str, size: tuple[int, int], quality: str, refs: list[Path], model: str) -> bytes:
    key = _need("DASHSCOPE_API_KEY", "阿里云百炼")
    base = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
    content: list[dict] = [{"image": "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()} for p in refs]
    content.append({"text": prompt})
    body = {"model": model, "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"size": f"{size[0]}*{size[1]}", "watermark": False}}
    data = post_json(f"{base}/services/aigc/multimodal-generation/generation", body, {"Authorization": f"Bearer {key}"})
    for ch in ((data.get("output") or {}).get("choices") or []):
        for c in (ch.get("message") or {}).get("content", []):
            if c.get("image"):
                return fetch_bytes(c["image"])
    raise BackendError("unknown", f"百炼没有返回图片：{str(data)[:200]}")


PROVIDERS: dict[str, dict] = {
    "openai": {"zh": "OpenAI / OpenAI 兼容中转", "fn": openai_generate, "ping": openai_ping, "env": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
               "default_model": "gpt-image-2", "refs": True, "verified": True,
               "blurb": "质量高、中文字准；官方直连需境外网络且要先做组织验证；国内可用兼容中转（改 OPENAI_BASE_URL）",
               "apply": "https://platform.openai.com/api-keys"},
    "gemini": {"zh": "Google Gemini（Nano Banana）", "fn": gemini_generate, "env": ["GEMINI_API_KEY", "GOOGLE_BASE_URL"],
               "default_model": "gemini-3.1-flash-image", "refs": True, "verified": False,
               "blurb": "有免费额度、参考图能力强（角色与风格可分开给）；需境外网络", "apply": "https://aistudio.google.com/apikey"},
    "openrouter": {"zh": "OpenRouter（一个 Key 用多家）", "fn": openrouter_generate, "env": ["OPENROUTER_API_KEY"],
                   "default_model": "google/gemini-3.1-flash-image", "refs": True, "verified": False,
                   "blurb": "还没想好用哪家时最省事；需境外网络与支付方式", "apply": "https://openrouter.ai/keys"},
    "seedream": {"zh": "火山方舟 Seedream（即梦同源）", "fn": seedream_generate, "env": ["ARK_API_KEY"],
                 "default_model": "doubao-seedream-4-0-250828", "refs": True, "verified": False,
                 "blurb": "大陆直连；组图与角色一致性好", "apply": "https://console.volcengine.com/ark"},
    "dashscope": {"zh": "阿里云百炼（通义万相 / Qwen-Image）", "fn": dashscope_generate, "env": ["DASHSCOPE_API_KEY"],
                  "default_model": "qwen-image-plus", "refs": True, "verified": False,
                  "blurb": "大陆直连；中文字渲染强", "apply": "https://bailian.console.aliyun.com/"},
}
