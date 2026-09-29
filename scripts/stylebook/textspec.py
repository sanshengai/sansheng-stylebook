"""文字清单的原生字与后期精确排字分工。"""
from __future__ import annotations


MODES = {"none", "native", "overlay", "hybrid"}


def native_items(spec: dict) -> list[dict]:
    items = spec.get("items") or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("render") == "native"] if spec.get("mode") == "hybrid" else items


def overlay_items(spec: dict) -> list[dict]:
    items = spec.get("items") or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("render") == "overlay"] if spec.get("mode") == "hybrid" else items


def validate_hybrid(spec: dict) -> list[str]:
    """混合模式须同时指定原生字与可排入成品的精确字。"""
    problems: list[str] = []
    if not isinstance(spec.get("reserve"), str) or not spec["reserve"].strip():
        problems.append("hybrid 须写 reserve，说明给精确文字预留的空白位置")
    items = spec.get("items")
    if not isinstance(items, list) or not items:
        return problems + ["hybrid 须提供 text.items"]
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            problems.append(f"hybrid 第 {i} 条须为对象")
            continue
        if item.get("render") not in ("native", "overlay"):
            problems.append(f"hybrid 第 {i} 条 render 只能是 native 或 overlay")
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            problems.append(f"hybrid 第 {i} 条缺文字")
        if item.get("render") == "native" and "box" in item:
            problems.append(f"hybrid 第 {i} 条原生字不能带 box；box 只给后期叠字")
    if problems:
        return problems
    native, overlay = native_items(spec), overlay_items(spec)
    if not native or not overlay:
        problems.append("hybrid 须同时有 native 原生字和 overlay 精确叠字")
    if overlay:
        from .overlay import validate as validate_overlay
        problems.extend(validate_overlay({"mode": "overlay", "items": overlay}))
    return problems
