"""两图匿名、交换顺序的相对缺陷复核；只证明候选相对参考图的变化。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .reviewer import (ARK_MODEL, ARK_PLAN_URL, QuotaExhausted, ReviewerAuthUnavailable, ReviewerNetworkUnavailable,
                       _ark_text, _image_uri)


PROMPT = """Compare two anonymous images of the same scene against ONE visual decision rule:
{criterion}
Inspect the relevant image region in each image. Apply the rule's stated meaning of defect to each image independently.
Choose the better image for this criterion, or TIE if neither is clearly better.
Do not infer which image was generated first. Return only JSON with exactly these fields:
A_observation and B_observation (nonempty strings with specific visible evidence);
A_defect and B_defect (JSON booleans, judge each image independently);
preferred (one of "A", "B", "TIE"); reason (nonempty comparison string)."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ask_ark(a: Path, b: Path, criterion: str) -> dict:
    base = os.environ.get("ARK_AGENT_PLAN_BASE_URL", "").rstrip("/")
    key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "")
    if base != ARK_PLAN_URL or not key:
        raise ReviewerAuthUnavailable("双图复核只使用已配置的 Ark Agent Plan 套餐地址与 Key")
    content = [{"type": "input_text", "text": PROMPT.format(criterion=criterion)},
               {"type": "input_text", "text": "Image A:"}, {"type": "input_image", "image_url": _image_uri(a)},
               {"type": "input_text", "text": "Image B:"}, {"type": "input_image", "image_url": _image_uri(b)}]
    body = json.dumps({"model": ARK_MODEL, "input": [{"role": "user", "content": content}],
                       "max_output_tokens": 2000, "thinking": {"type": "disabled"}},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(base + "/responses", body,
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as handle:
            response = json.loads(handle.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise QuotaExhausted("Ark Agent Plan 双图复核额度用尽或限流") from exc
        if exc.code in (401, 403):
            raise ReviewerAuthUnavailable("Ark Agent Plan 双图复核鉴权或套餐访问被拒") from exc
        detail = exc.read().decode("utf-8", errors="replace")[:300].replace(key, "[REDACTED]")
        raise RuntimeError(f"Ark Agent Plan 双图复核 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ReviewerNetworkUnavailable(f"Ark Agent Plan 双图复核网络不可用，本轮停止复核：{exc.reason}") from exc
    if response.get("status") != "completed":
        raise RuntimeError(f"Ark Agent Plan 双图复核未完成：{response.get('status')}")
    returned = str(response.get("model") or "")
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    if not norm(returned).startswith(norm(ARK_MODEL)):
        raise RuntimeError(f"Ark Agent Plan 双图复核模型漂移：{returned}")
    answer = _ark_text(response)
    try:
        data = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ark Agent Plan 双图复核未返回 JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Ark Agent Plan 双图复核未返回对象")
    data["_reviewer"] = returned + " via Ark Agent Plan"
    return data


def _valid(data: dict) -> bool:
    return (type(data.get("A_defect")) is bool and type(data.get("B_defect")) is bool
            and data.get("preferred") in ("A", "B", "TIE")
            and all(isinstance(data.get(k), str) and data[k].strip()
                    for k in ("A_observation", "B_observation", "reason")))


def compare(reference: Path, candidate: Path, criterion: str,
            ask: Callable[[Path, Path, str], dict] | None = None,
            *, criterion_mode: str = "desired") -> dict:
    """reference 为已知问题图。两次匿名交换顺序；结果不能替代绝对 QA 或准入。"""
    reference, candidate = Path(reference).resolve(), Path(candidate).resolve()
    criterion = criterion.strip()
    if not criterion:
        raise ValueError("对照复核必须写清可观察的单一判据")
    if criterion_mode not in ("desired", "forbidden"):
        raise ValueError("对照复核判据模式只能是 desired 或 forbidden")
    if not reference.is_file() or not candidate.is_file():
        raise FileNotFoundError("参考图或候选图不存在")
    ref_sha, can_sha = _sha(reference), _sha(candidate)
    if ref_sha == can_sha:
        raise ValueError("参考图与候选图内容相同，无法对照")
    ask = ask or _ask_ark
    if criterion_mode == "forbidden":
        review_rule = (f"Forbidden visual feature: {criterion}\n"
                       "A_defect/B_defect is true exactly when that forbidden feature is visibly PRESENT in that image.")
    else:
        review_rule = (f"Desired visual feature: {criterion}\n"
                       "A_defect/B_defect is true exactly when that desired feature is visibly ABSENT or violated in that image.")
    reviews = []
    for order in (("reference", "candidate"), ("candidate", "reference")):
        paths = {"reference": reference, "candidate": candidate}
        data = ask(paths[order[0]], paths[order[1]], review_rule)
        if not isinstance(data, dict) or not _valid(data):
            raise RuntimeError("双图复核缺少具体观察、布尔缺陷判断或 A/B/TIE 选择")
        reviews.append({"order": {"A": order[0], "B": order[1]}, "answer": data})

    def agrees(r: dict, better: str) -> bool:
        order, d = r["order"], r["answer"]
        chosen = next((label for label in ("A", "B") if order[label] == better), None)
        other = "B" if chosen == "A" else "A"
        return (d["preferred"] == chosen and d[f"{chosen}_defect"] is False
                and d[f"{other}_defect"] is True)

    if all(agrees(r, "candidate") for r in reviews):
        verdict = "candidate_better"
    elif all(agrees(r, "reference") for r in reviews):
        verdict = "reference_better"
    else:
        verdict = "inconclusive"
    return {"verdict": verdict, "scope": "relative defect comparison only; not absolute QA or style admission",
            "criterion": criterion, "criterion_mode": criterion_mode,
            "images": {"reference": {"path": str(reference), "sha256": ref_sha},
                       "candidate": {"path": str(candidate), "sha256": can_sha}},
            "reviews": reviews}
