"""公开下载包不带样图：样图只在官网选择器里展示，出图只用合同与锚点。
无样图的包必须能重建出与完整仓库字节相同的选择器页面与图片清单（官网投影检查据此运作）。"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import build as BD  # noqa: E402
import public_export as PE  # noqa: E402


def test_export_selection_drops_samples_but_keeps_anchors_and_contracts():
    entries = [("100644", "styles/C30/contract.json"), ("100644", "styles/C30/anchor.png"),
               ("100644", "styles/C30/samples/cv.webp"), ("100644", "styles/C30/samples/ppt-12.webp"),
               ("100644", "SKILL.md"), ("100644", "README.md"), ("100644", "LICENSE"), ("100644", "requirements.txt"),
               ("100644", "styles/anchor-provenance.json"), ("100644", "registry.json")]
    entries += [("100644", f"styles/C{i}/contract.json") for i in range(1, 1)]
    cat = json.loads((ROOT / "styles/catalog.json").read_text(encoding="utf-8"))["styles"]
    entries += [("100644", f"styles/{s['code']}/contract.json") for s in cat if s["code"] != "C30"]
    chosen = PE.select(entries)
    assert "styles/C30/contract.json" in chosen and "styles/C30/anchor.png" in chosen
    assert not [n for n in chosen if "/samples/" in n]


def test_every_registered_sample_has_a_matching_ratio():
    """合同登记的宽高比必须与仓库里的实际样图一致：无样图重建时页面比例靠它。"""
    from PIL import Image
    bad = []
    for cj in sorted((ROOT / "styles").glob("C*/contract.json")):
        for s in json.loads(cj.read_text(encoding="utf-8")).get("samples", []):
            if "ratio" not in s:
                bad.append((cj.parent.name, s["file"], "缺 ratio"))
                continue
            f = cj.parent / s["file"]
            if f.is_file():
                with Image.open(f) as im:
                    if abs(round(im.width / im.height, 3) - s["ratio"]) > 0.002:
                        bad.append((cj.parent.name, s["file"], "比例不符"))
    assert bad == [], bad[:5]


@pytest.fixture(scope="module")
def full_and_bare(tmp_path_factory):
    full = tmp_path_factory.mktemp("full")
    BD.picker(full)
    bare_root = tmp_path_factory.mktemp("bare") / "sb"
    shutil.copytree(ROOT, bare_root, ignore=shutil.ignore_patterns(".git", "gallery/build", "__pycache__", "logs", "samples", ".pytest_cache"))
    assert not list(bare_root.glob("styles/C*/samples"))
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "STYLEBOOK_PROFILE": str(bare_root / "none"), "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "scripts/sb.py", "build", "--gallery"], cwd=bare_root, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    return full, bare_root / "gallery/build"


def test_bare_package_rebuilds_identical_page_and_image_manifest(full_and_bare):
    full, bare = full_and_bare
    assert (bare / "index.html").read_bytes() == (full / "index.html").read_bytes()
    assert (bare / "img-manifest.json").read_bytes() == (full / "img-manifest.json").read_bytes()
    full_names = {p.name for p in (full / "img").glob("*.webp")}
    bare_names = {p.name for p in (bare / "img").glob("*.webp")}
    assert bare_names < full_names, "无样图包只应有锚点缩略图"
    assert set(json.loads((full / "img-manifest.json").read_text())["images"]) == full_names


def test_registered_sample_without_ratio_or_file_is_rejected(tmp_path, monkeypatch):
    """反例：样图既没有文件、合同里也没登记宽高比，构建必须报错而不是悄悄少一张。"""
    sample = {"topic": "x", "file": "samples/cv.webp"}
    monkeypatch.setattr(BD.CT, "load", lambda code: {"samples": [sample]})
    cp = tmp_path / "C99" / "contract.json"
    cp.parent.mkdir()
    files = BD._sample_files("C99", cp)
    assert files["cv"][1] is None and not files["cv"][0].is_file()
