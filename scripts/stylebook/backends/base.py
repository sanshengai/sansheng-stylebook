"""接口层公共部分：错误分类、HTTP、.env 读取、地址脱敏。只用标准库。"""
from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_DIR = Path(os.environ.get("STYLEBOOK_CONFIG_DIR", Path.home() / ".config" / "sansheng-stylebook"))


class BackendError(RuntimeError):
    """kind: busy / auth / verify / policy / bad_request / network / unconfigured / unknown"""

    def __init__(self, kind: str, message: str, *, retryable: bool = False, status: int | None = None):
        self.kind, self.retryable, self.status = kind, retryable, status
        super().__init__(message)


@dataclass
class Result:
    image: bytes
    provider: str
    model: str
    attempts: int
    seconds: float
    est_usd: float | None = None


def redact(url: str) -> str:
    """诊断输出只留协议与主机，防止带 token 或密码的地址进日志。"""
    try:
        p = urlsplit(url)
        return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")
    except Exception:
        return "<地址无法解析>"


def load_dotenv() -> None:
    """读 ~/.config/sansheng-stylebook/.env 与项目 .stylebook/.env；已存在的环境变量不覆盖，不打印任何值。"""
    for f in (Path.cwd() / ".stylebook" / ".env", CONFIG_DIR / ".env"):
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


BUSY_HINTS = ("系统繁忙", "busy", "overloaded", "capacity", "try again", "稍后再试", "no available channel", "无可用渠道")


def classify(status: int | None, body: str) -> BackendError:
    low = (body or "").lower()
    short = (body or "")[:300]
    if status in (401,):
        return BackendError("auth", f"密钥无效或已过期（401）。检查对应服务的 API Key。{short}", status=status)
    if status == 403 and ("verif" in low or "organization" in low):
        return BackendError("verify", "OpenAI 要求先完成组织验证才能用 gpt-image 系列：platform.openai.com → Settings → Organization → Verify。", status=status)
    if status == 403:
        return BackendError("auth", f"没有权限（403）。{short}", status=status)
    # 内容被拒要先判：有的中转把审核拦截包成 429 返回（2026-09-25 实测 "may violate our content policies"），按繁忙重试只会白跑
    if any(h in low for h in ("safety", "content polic", "content_policy", "moderation", "violate", "usage polic")):
        return BackendError("policy", f"内容被服务方拒绝（{status}）。换一种描述再试。{short}", status=status)
    if status == 429 or any(h in low for h in BUSY_HINTS) or (status is not None and status >= 500):
        return BackendError("busy", f"服务繁忙或限流（{status}）。{short}", retryable=True, status=status)
    if "policy" in low:
        return BackendError("policy", f"内容被服务方拒绝（{status}）。换一种描述再试。{short}", status=status)
    if status is not None and 400 <= status < 500:
        return BackendError("bad_request", f"请求参数有误（{status}）。{short}", status=status)
    return BackendError("unknown", f"未知错误（{status}）。{short}", retryable=True, status=status)


def _open(req: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise BackendError("network", f"连不上 {redact(req.full_url)}：{e}", retryable=True) from None


def post_json(url: str, payload: dict, headers: dict, timeout: float = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    status, raw = _open(req, timeout)
    text = raw.decode("utf-8", "replace")
    if status >= 400:
        raise classify(status, text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise classify(status, text) from None


def post_multipart(url: str, fields: dict, files: list[tuple[str, Path]], headers: dict, timeout: float = 300) -> dict:
    boundary = "----stylebook" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for name, path in files:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
                     f"Content-Type: {mime}\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(url, data=b"".join(parts), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **headers})
    status, raw = _open(req, timeout)
    text = raw.decode("utf-8", "replace")
    if status >= 400:
        raise classify(status, text)
    return json.loads(text)


def get(url: str, headers: dict, timeout: float = 30) -> tuple[int, bytes]:
    return _open(urllib.request.Request(url, headers=headers), timeout)


def fetch_bytes(url: str, timeout: float = 120) -> bytes:
    status, raw = get(url, {}, timeout)
    if status >= 400:
        raise classify(status, raw.decode("utf-8", "replace"))
    return raw


def now() -> float:
    return time.monotonic()
