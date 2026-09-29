"""Admit only fully reviewed batch outputs to comparative evaluations."""
from __future__ import annotations

import json
from pathlib import Path


def checked_images(run_dir: str | Path) -> list[str]:
    run = Path(run_dir)
    state_path = run / "state.json"
    if not state_path.is_file():
        raise ValueError(f"{run}: 缺少 state.json，无法证明图片已验收")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{run}: state.json 无法读取") from exc
    items, summary = state.get("items"), state.get("summary")
    if not isinstance(items, dict) or not items or not isinstance(summary, dict):
        raise ValueError(f"{run}: 没有可验收的图片记录")
    if summary.get("total") != len(items) or summary.get("passed") != len(items) or summary.get("failed"):
        raise ValueError(f"{run}: 批次未全部通过验收")
    names = []
    for item_id, record in items.items():
        if not isinstance(record, dict) or record.get("status") != "passed" or not record.get("review"):
            raise ValueError(f"{run}: {item_id} 未通过独立看图验收")
        name = record.get("image")
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".png"):
            raise ValueError(f"{run}: {item_id} 的图片文件名无效")
        if not (run / name).is_file():
            raise ValueError(f"{run}: 缺少已验收图片 {name}")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError(f"{run}: 验收记录重复指向同一张图片")
    return [str(run / name) for name in sorted(names)]
