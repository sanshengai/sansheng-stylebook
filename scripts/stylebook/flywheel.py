"""成长飞轮：脚本自动记录，攒够证据只问一次，确认才改默认。

规范版本 1（跨 Skill 通用，画风手册与写作 Skill 各带一份同版本副本）：
- 事件由脚本在关键命令里自动写入，不靠 Agent 自觉调用：选择（choice）、采用（accept）、返修（fix）。
- 同一维度、同一方向，在 3 个不同任务里出现，才生成一次待问；同一任务里改多次只算一次。
- 待问只在下次任务开头提一次，三个答案：设为默认 / 只在这个项目 / 不用；「不用」60 天内不再问。
- 只存字段与产物路径，不存对话原文。
- 连续 5 次任务没有留下任何采用 / 返修 / 选择记录，提示“飞轮可能断了”。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import data as D
from . import profile as P

SPEC_VERSION = 1
NEED_TASKS = 3
DECLINE_DAYS = 60
STALL_TASKS = 5


def _dir(create: bool = False) -> Path:
    d = P.profile_path().parent / "flywheel"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _append(name: str, rec: dict) -> dict:
    rec = {"at": _now().isoformat(timespec="seconds"), "spec": SPEC_VERSION, **rec}
    with (_dir(True) / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _read(name: str) -> list[dict]:
    f = _dir() / name
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ---------------- 记录 ----------------
def record_outcome(kind: str, style: str, use: str | None, *, task_id: str, detail: str = "") -> dict:
    """accept：用户采用了这张图；fix：像素预检失败或需要返修。detail 只写原因类别，不写原文。"""
    if kind not in {"accept", "fix"}:
        raise ValueError(f"未知结果类型：{kind}")
    return _append("outcomes.jsonl", {"kind": kind, "style": style.split("@")[0], "use": use, "task_id": task_id, "detail": detail[:120]})


def record_task(task_id: str, scene: str | None, captured: int) -> None:
    _append("tasks.jsonl", {"task_id": task_id, "scene": scene, "captured": captured})


def capture_choice(field: str, value, *, scene: str, task_id: str, candidates: list, project: str | None = None) -> dict | None:
    """用户主动选了与推荐不同的值 → 写观察事件。委托 profile，沿用暂停、去重与撤销规则。"""
    try:
        return P.record_change(field, value, scene=scene, task_id=task_id, candidates=candidates, project=project)
    except P.ProfileError:
        return None


# ---------------- 待问 ----------------
def _declined(events: list[dict], scope: dict, field: str, value) -> bool:
    limit = _now() - timedelta(days=DECLINE_DAYS)
    for e in events:
        if e.get("kind") == "declined" and e.get("scope") == scope and e.get("field") == field and e.get("value") == value:
            if datetime.fromisoformat(e["at"]) >= limit:
                return True
    return False


def pending(scene: str | None = None, project: str | None = None) -> list[dict]:
    """满足“同方向 3 个不同任务”、尚未设为默认、未被拒绝过的待问。"""
    data = P.read()
    if data["paused"]:
        return []
    events = P._active(data)
    scopes = ([{"scene": scene, "project": project}] if scene and project else []) + ([{"scene": scene}] if scene else [{}])
    out = []
    for scope in scopes:
        for field in sorted(P.FIELDS):
            tasks: dict[str, tuple[object, str]] = {}
            for e in events:
                if e.get("kind") == "active_change" and e.get("field") == field and e.get("scope") == scope:
                    tasks[e["task_id"]] = (e["value"], e["id"])
            if len(tasks) < NEED_TASKS:
                continue
            values = {json.dumps(v, sort_keys=True, ensure_ascii=False) for v, _ in tasks.values()}
            if len(values) != 1:
                continue
            value = next(iter(tasks.values()))[0]
            current = P.lookup(field, scene=scope.get("scene"), project=scope.get("project"), include_inferred=False)
            if current and current["value"] == value:
                continue
            if _declined(data["events"], scope, field, value):
                continue
            label = D.scenes()[scope["scene"]]["zh"] if scope.get("scene") else "所有用途"
            noun = {"style": "画风", "palette": "色系"}.get(field, field)
            shown = value if isinstance(value, str) else value.get("family", value)
            out.append({"scope": scope, "field": field, "value": value, "evidence": [eid for _, eid in tasks.values()],
                        "question": f"你最近 {len(tasks)} 次做「{label}」都把{noun}换成了 {shown}。要设成默认吗？（设为默认 / 只在这个项目 / 不用）"})
    return out


def answer(scope: dict, field: str, value, choice: str) -> dict:
    """choice：default 设为该用途默认；project 只在这个项目（scope 里须有 project）；no 不用（60 天内不再问）。"""
    scene, project = scope.get("scene"), scope.get("project")
    if choice == "default":
        return P.set_explicit(field, value, scene=scene, note="飞轮确认：观察到连续同向选择，用户确认设为默认")
    if choice == "project":
        if not project:
            raise P.ProfileError("“只在这个项目”需要 scope.project")
        return P.set_explicit(field, value, scene=scene, project=project, note="飞轮确认：只在该项目")
    if choice == "no":
        return P._append(P._event("declined", P._scope(scene, project), field, P._value(field, value), note="飞轮：用户选择不用"))
    raise P.ProfileError("choice 只能是 default / project / no")


# ---------------- 汇总与断流 ----------------
def ledger() -> dict:
    """用途 × 画风的采用 / 返修账；网站的“已验证 / 试用中”标签从这里来。"""
    acc: dict[str, dict] = {}
    for r in _read("outcomes.jsonl"):
        cell = acc.setdefault(f"{r.get('use') or '-'}|{r['style']}", {"use": r.get("use"), "style": r["style"], "accept": 0, "fix": 0})
        cell[r["kind"]] += 1
    return acc


def stalled() -> bool:
    tasks = _read("tasks.jsonl")[-STALL_TASKS:]
    return len(tasks) >= STALL_TASKS and all(t.get("captured", 0) == 0 for t in tasks)


def status(scene: str | None = None, project: str | None = None) -> dict:
    data = P.read()
    active = P._active(data)
    return {"spec": SPEC_VERSION, "paused": data["paused"],
            "explicit": [e for e in active if e["kind"] == "explicit_set"],
            "observed_events": sum(1 for e in active if e["kind"] == "active_change"),
            "declined": [e for e in data["events"] if e["kind"] == "declined"],
            "pending": pending(scene, project), "outcomes": len(_read("outcomes.jsonl")),
            "ledger": list(ledger().values()), "tasks": len(_read("tasks.jsonl")), "stalled": stalled(),
            "note": "飞轮可能断了：最近 5 次任务没有留下采用 / 返修 / 选择记录，检查是否用了 make 与 accept。" if stalled() else ""}


def _task_id(brief: dict, out_dir: Path) -> str:
    src = brief.get("source")
    basis = f"{src}|{brief.get('scene')}" if src else str(Path(out_dir).name)
    return "task-" + hashlib.sha256(basis.encode()).hexdigest()[:12]


def after_make(brief: dict, report: dict, out_dir: Path) -> dict:
    """make 结束后自动调用：写选择 / 返修记录、任务记录，并返回待问与提示。异常一律吞掉，飞轮不能拖垮出图。"""
    info: dict = {"captured": 0, "pending": [], "notes": []}
    try:
        from . import plan as PL
        selection = report.get("selection") or {}
        scene = brief.get("scene") or selection.get("scene")
        if scene not in D.scenes():
            return info
        code = str(selection.get("code", "")).split("@")[0]
        use = D.use_of_scene(scene)
        task_id = brief.get("task_id") or _task_id(brief, out_dir)
        rec = PL.resolve_style(scene, explicit=None, include_inferred=False)
        recommended = str(rec["code"]).split("@")[0]
        if selection.get("source") == "preference":
            info["notes"].append(f"沿用你的默认：{code}")
        user_chosen = brief.get("chosen_by") == "user" or bool(brief.get("code"))
        if user_chosen and code and code != recommended and capture_choice("style", code, scene=scene, task_id=task_id, candidates=[recommended, code]):
            info["captured"] += 1
        pal = brief.get("palette")
        if user_chosen and isinstance(pal, dict) and pal.get("family") not in (None, "orig"):
            value = {k: pal[k] for k in ("family", "light", "sat", "custom") if k in pal}
            if capture_choice("palette", value, scene=scene, task_id=task_id, candidates=[{"family": "orig"}, value]):
                info["captured"] += 1
        for item in report.get("items") or []:
            if item.get("status") == "pixel_failed" and code:
                record_outcome("fix", code, use, task_id=task_id, detail="pixel_preflight")
                info["captured"] += 1
        record_task(task_id, scene, info["captured"])
        info["pending"] = pending(scene)
        if stalled():
            info["notes"].append("飞轮可能断了：最近 5 次出图都没有留下任何记录；出图后请用 sb.py accept 记录采用的图。")
    except Exception as exc:  # noqa: BLE001  飞轮不能拖垮出图
        info["notes"].append(f"飞轮记录跳过：{type(exc).__name__}")
    return info


def accept(out_dir: Path, ids: list[str] | None = None) -> list[dict]:
    """用户采用了 out_dir 里的图 → 记 accept，供“已验证”标签与推荐排序使用。"""
    report = json.loads((Path(out_dir) / "report.json").read_text(encoding="utf-8"))
    brief = json.loads((Path(out_dir) / "brief.json").read_text(encoding="utf-8"))
    sel = report.get("selection") or {}
    code = str(sel.get("code", "")).split("@")[0]
    scene = brief.get("scene") or sel.get("scene")
    use = D.use_of_scene(scene) if scene in D.scenes() else None
    task_id = brief.get("task_id") or _task_id(brief, Path(out_dir))
    return [record_outcome("accept", code, use, task_id=task_id, detail=item["id"])
            for item in report.get("items", []) if item.get("status") == "pending_visual_review" and (not ids or item["id"] in ids)]
