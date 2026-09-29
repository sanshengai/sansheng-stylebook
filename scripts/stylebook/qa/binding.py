"""Bind a review to its exact inputs. A binding proves identity, not reviewer quality."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def snapshot(kind: str, *, files: dict[str, Path], values: dict) -> dict:
    if kind not in ("image", "article-plan") or not files or not values:
        raise ValueError("验收绑定需要已知类型、实际文件和判断参数")
    hashes = {}
    for name, path in files.items():
        content = Path(path).read_bytes()
        if not content:
            raise ValueError(f"验收输入为空：{name}")
        hashes[name] = hashlib.sha256(content).hexdigest()
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"schema": "stylebook-review-binding/v1", "kind": kind,
            "files_sha256": hashes, "values_sha256": hashlib.sha256(encoded.encode()).hexdigest()}


def verify(binding: dict | None, *, kind: str, files: dict[str, Path], values: dict) -> None:
    if binding != snapshot(kind, files=files, values=values):
        raise ValueError("验收报告未绑定当前输入，或输入已改变；须重新验收")
