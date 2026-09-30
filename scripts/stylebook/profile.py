"""本地偏好记忆。只收明确持久设置与主动修改；出图验收和沉默不构成偏好。"""
from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import contract as CT
from . import data as D

VERSION = 1
FIELDS = {"style", "palette", "form", "structure"}


class ProfileError(ValueError):
    pass


def profile_path() -> Path:
    env = os.environ.get("STYLEBOOK_PROFILE")
    root = Path(env).expanduser() if env else Path.home() / ".config" / "sansheng-stylebook" / "profile"
    return root / "memory.json"


def _empty() -> dict:
    return {"version": VERSION, "paused": False, "events": [], "forgotten_ids": []}


def _load(path: Path) -> dict:
    if not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProfileError(f"偏好文件无法读取：{path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise ProfileError(f"不支持的偏好文件版本：{data.get('version') if isinstance(data, dict) else type(data).__name__}")
    if not isinstance(data.get("events"), list) or not isinstance(data.get("forgotten_ids"), list) or type(data.get("paused")) is not bool:
        raise ProfileError("偏好文件的 events / forgotten_ids / paused 格式错误")
    if "apply_paused" in data and type(data["apply_paused"]) is not bool:
        raise ProfileError("apply_paused 必须是布尔值")
    ids = [event.get("id") for event in data["events"] if isinstance(event, dict)]
    if (len(ids) != len(data["events"]) or any(not isinstance(i, str) or not i for i in ids)
            or len(ids) != len(set(ids))):
        raise ProfileError("偏好事件 id 缺失或重复")
    for event in data["events"]:
        if event.get("kind") not in {"explicit_set", "explicit_clear", "active_change", "revoke", "declined"} or not isinstance(event.get("scope"), dict):
            raise ProfileError(f"偏好事件格式错误：{event['id']}")
        if event["kind"] == "revoke":
            if not isinstance(event.get("target"), str):
                raise ProfileError(f"撤销事件缺 target：{event['id']}")
        elif event.get("field") not in FIELDS:
            raise ProfileError(f"偏好事件字段错误：{event['id']}")
        elif event["kind"] in {"explicit_set", "active_change", "declined"}:
            if "value" not in event:
                raise ProfileError(f"偏好事件缺 value：{event['id']}")
            if event["kind"] == "active_change" and (not isinstance(event.get("task_id"), str) or not event["task_id"]
                                                       or not isinstance(event.get("candidates"), list)):
                raise ProfileError(f"主动改选事件缺 task_id / candidates：{event['id']}")
    if any(not isinstance(i, str) or not i for i in data["forgotten_ids"]):
        raise ProfileError("forgotten_ids 必须是非空 ID 列表")
    return data


def read() -> dict:
    return _load(profile_path())


def _write(mutator) -> dict:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(".memory.lock")
    with lock.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        data = _load(path)
        mutator(data)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".memory-", suffix=".tmp", delete=False) as tmp:
            name = tmp.name
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return data


def _scope(scene: str | None, project: str | None) -> dict:
    if scene is not None and scene not in D.scenes():
        raise ProfileError(f"未知场景：{scene}")
    if project is not None and (not isinstance(project, str) or not project.strip()):
        raise ProfileError("project 必须是非空标识")
    return {key: value for key, value in (("scene", scene), ("project", project)) if value is not None}


def _value(field: str, value):
    if field not in FIELDS:
        raise ProfileError(f"不支持的偏好字段：{field}")
    if field == "style":
        if not isinstance(value, str):
            raise ProfileError("style 必须是已有画风码")
        try:
            CT.load(value)
        except (KeyError, CT.ContractError) as exc:
            raise ProfileError(f"画风不可用：{value}") from exc
    elif field == "palette":
        if not isinstance(value, dict):
            raise ProfileError("palette 必须是 {family, light, sat} 对象")
        family = value.get("family")
        if family not in {p["id"] for p in D.palettes()["palettes"]}:
            raise ProfileError(f"未知色系：{family}")
        if any(type(value.get(key, 0)) is not int or value.get(key, 0) not in (-1, 0, 1) for key in ("light", "sat")):
            raise ProfileError("light / sat 只能是 -1、0、1")
        custom = value.get("custom")
        if family == "brand":
            if not isinstance(custom, list) or not custom or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in custom):
                raise ProfileError("品牌色须提供 custom: [\"#RRGGBB\", ...]")
        elif custom is not None:
            raise ProfileError("只有 brand 色系可以填写 custom")
        value = {"family": family, "light": value.get("light", 0), "sat": value.get("sat", 0),
                 **({"custom": [c.upper() for c in custom]} if custom else {})}
    elif field == "form":
        if value not in {"auto", "scene", "metaphor", "structure"}:
            raise ProfileError(f"未知表达形式：{value}")
    elif field == "structure":
        if value != "auto" and value not in D.structures():
            raise ProfileError(f"未知结构：{value}")
    return value


def _event(kind: str, scope: dict, field: str | None = None, value=None, *, event_id: str | None = None,
           task_id: str | None = None, note: str = "", candidates: list | None = None) -> dict:
    event = {"id": event_id or uuid.uuid4().hex, "at": datetime.now(timezone.utc).isoformat(),
             "kind": kind, "scope": scope}
    if field is not None:
        event["field"] = field
    if value is not None:
        event["value"] = value
    if task_id is not None:
        event["task_id"] = task_id
    if note:
        event["note"] = note[:200]
    if candidates is not None:
        event["candidates"] = candidates
    return event


def _append(event: dict) -> dict:
    def mutate(data: dict):
        if event["id"] in data["forgotten_ids"]:
            raise ProfileError(f"事件已被忘记，不能重新写入：{event['id']}")
        old = next((e for e in data["events"] if e["id"] == event["id"]), None)
        if old is not None:
            if {k: v for k, v in old.items() if k != "at"} != {k: v for k, v in event.items() if k != "at"}:
                raise ProfileError(f"事件 ID 冲突：{event['id']}")
            return
        data["events"].append(event)
    _write(mutate)
    return event


def set_explicit(field: str, value, *, scene: str | None = None, project: str | None = None,
                 event_id: str | None = None, note: str = "") -> dict:
    return _append(_event("explicit_set", _scope(scene, project), field, _value(field, value), event_id=event_id, note=note))


def clear_explicit(field: str, *, scene: str | None = None, project: str | None = None) -> dict:
    if field not in FIELDS:
        raise ProfileError(f"不支持的偏好字段：{field}")
    return _append(_event("explicit_clear", _scope(scene, project), field))


def record_change(field: str, value, *, scene: str, task_id: str, candidates: list,
                  project: str | None = None, reason: str = "preference", note: str = "",
                  event_id: str | None = None) -> dict | None:
    """只接收用户主动改动。正确性返修和未展示候选不得计入学习。"""
    if reason != "preference":
        return None
    if not task_id or not isinstance(candidates, list) or value not in candidates:
        raise ProfileError("主动偏好事件须有 task_id，并记录实际展示且包含本次选择的候选")
    if read()["paused"]:
        return None
    return _append(_event("active_change", _scope(scene, project), field, _value(field, value),
                          event_id=event_id, task_id=task_id, note=note, candidates=candidates))


def _active(data: dict) -> list[dict]:
    revoked = {event.get("target") for event in data["events"] if event.get("kind") == "revoke"}
    forgotten = set(data["forgotten_ids"])
    return [event for event in data["events"] if event["id"] not in revoked | forgotten and event.get("kind") != "revoke"]


def lookup(field: str, *, scene: str | None = None, project: str | None = None,
           include_inferred: bool = True) -> dict | None:
    """精确项目场景 > 场景 > 全局；显式设置始终高于观察倾向。"""
    scope = _scope(scene, project)
    events = _active(read())
    priorities = [scope]
    if project is not None and scene is not None:
        priorities += [{"scene": scene}, {"project": project}]
    if scope != {}:
        priorities.append({})
    for wanted in priorities:
        for event in reversed(events):
            if event.get("scope") == wanted and event.get("field") == field and event.get("kind") in {"explicit_set", "explicit_clear"}:
                if event["kind"] == "explicit_clear":
                    break
                return {"value": event["value"], "source": "explicit_memory", "evidence": [event["id"]], "scope": wanted}
    if not include_inferred or read()["paused"]:
        return None
    # 同一场景/项目，每个独立任务只计最后一次主动修改；其他项目的证据不能混入。
    inferred_scopes = ([{"scene": scene, "project": project}] if project and scene else []) + ([{"scene": scene}] if scene else [])
    for wanted in inferred_scopes:
        task_values: dict[str, tuple[object, str]] = {}
        for event in events:
            if event.get("kind") == "active_change" and event.get("field") == field and event.get("scope") == wanted:
                task_values[event["task_id"]] = (event["value"], event["id"])
        if len(task_values) >= 3:
            values = {json.dumps(value, sort_keys=True, ensure_ascii=False) for value, _ in task_values.values()}
            if len(values) == 1:
                value, _ = next(iter(task_values.values()))
                return {"value": value, "source": "observed", "evidence": [eid for _, eid in task_values.values()],
                        "scope": wanted}
    return None


def revoke(event_id: str) -> dict:
    data = read()
    original = next((event for event in data["events"] if event["id"] == event_id), None)
    if original is None:
        raise ProfileError(f"没有事件：{event_id}")
    if original["kind"] == "revoke":
        raise ProfileError("不能撤销撤销事件；请重新设置偏好")
    if any(event.get("kind") == "revoke" and event.get("target") == event_id for event in data["events"]):
        raise ProfileError(f"事件已经撤销：{event_id}")
    return _append({**_event("revoke", {}), "target": event_id})


def forget(event_id: str) -> None:
    def mutate(data: dict):
        if event_id not in {event["id"] for event in data["events"]}:
            raise ProfileError(f"没有事件：{event_id}")
        data["events"] = [event for event in data["events"] if event["id"] != event_id and event.get("target") != event_id]
        if event_id not in data["forgotten_ids"]:
            data["forgotten_ids"].append(event_id)
    _write(mutate)


def pause(value: bool) -> None:
    _write(lambda data: data.__setitem__("paused", bool(value)))


def export_to(path: Path, *, force: bool = False) -> None:
    target = Path(path)
    if target.exists() and not force:
        raise ProfileError(f"导出目标已存在：{target}；需要覆盖时加 --force")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(read(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def import_from(path: Path, *, replace_conflicts: bool = False) -> dict:
    incoming = _load(Path(path))
    if not Path(path).is_file():
        raise ProfileError(f"导入文件不存在：{path}")
    added = []
    def mutate(data: dict):
        existing = {event["id"]: event for event in data["events"]}
        forgotten = set(data["forgotten_ids"]) | set(incoming["forgotten_ids"])
        for event in incoming["events"]:
            if event["id"] in forgotten:
                continue
            old = existing.get(event["id"])
            if old is not None:
                if old != event:
                    raise ProfileError(f"导入事件 ID 冲突：{event['id']}")
                continue
            if event["kind"] == "explicit_set" and not replace_conflicts:
                for current in reversed(_active(data)):
                    if (current.get("kind") in {"explicit_set", "explicit_clear"} and current.get("scope") == event["scope"]
                            and current.get("field") == event["field"]):
                        if current["kind"] == "explicit_set" and current.get("value") != event["value"]:
                            raise ProfileError(f"明确偏好冲突：{event['scope']} / {event['field']}；检查后用 --replace-conflicts")
                        break
            data["events"].append(event)
            existing[event["id"]] = event
            added.append(event["id"])
        data["events"] = [event for event in data["events"] if event["id"] not in forgotten]
        data["forgotten_ids"] = sorted(forgotten)
        if incoming.get("apply_paused"):
            data["paused"] = incoming["paused"]
    _write(mutate)
    return {"imported": len(added), "event_ids": added}
