"""数据层：格式、表达结构、色系、场景、样式目录，以及私有 profile 覆盖。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .contract import ROOT, profile_dir


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def formats() -> dict[str, dict]:
    return {f["id"]: f for f in _load("formats/formats.json")["formats"]}


@lru_cache(maxsize=None)
def structures() -> dict[str, dict]:
    return {s["id"]: s for s in _load("structures/structures.json")["structures"]}


@lru_cache(maxsize=None)
def palettes() -> dict:
    return _load("palettes/palettes.json")


@lru_cache(maxsize=None)
def scenes() -> dict[str, dict]:
    return {s["id"]: s for s in _load("scenes/scenes.json")["scenes"]}


def catalog() -> dict[str, dict]:
    """公开目录 + 私有目录（若有 profile）。"""
    out = {s["code"]: dict(s, visibility="public") for s in _load("styles/catalog.json")["styles"]}
    prof = profile_dir()
    if prof and (prof / "catalog.json").exists():
        for s in json.loads((prof / "catalog.json").read_text(encoding="utf-8"))["styles"]:
            out[s["code"]] = dict(s, visibility="private")
    return out


def author() -> dict | None:
    prof = profile_dir()
    if prof and (prof / "author.json").exists():
        return json.loads((prof / "author.json").read_text(encoding="utf-8"))
    return None


def scene_choice(scene_id: str) -> tuple[str, list[str], str]:
    """返回（默认样式、备选、来源）：作者档案优先于公开出厂默认。"""
    sc = scenes()[scene_id]
    a = author()
    if a and scene_id in a.get("scene_defaults", {}):
        d = a["scene_defaults"][scene_id]
        return d["default"], d["alternates"], "作者档案"
    return sc["default"], sc["alternates"], "出厂默认"
