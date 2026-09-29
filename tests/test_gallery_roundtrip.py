"""浏览器实际导出与 CLI 入口往返；只测协议边界，不把页面 DOM 当实现合同。"""
import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import build as BD  # noqa: E402


def _cli_normalize(tmp_path: Path, exported: str) -> dict:
    key = hashlib.sha256(exported.encode()).hexdigest()[:12]
    src, dst = tmp_path / f"selection-{key}.json", tmp_path / f"normalized-{key}.json"
    src.write_text(exported, encoding="utf-8")
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "sb.py"), "selection", "normalize",
                           "--input", str(src), "-o", str(dst)], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stderr or done.stdout
    return json.loads(dst.read_text(encoding="utf-8"))


@pytest.fixture
def page(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium 不可用：{exc}")
        html = BD.gallery(tmp_path / "gallery.html", private=False)
        tab = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.goto(html.resolve().as_uri())
        tab.locator('[data-tab="proto"]').click()
        yield tab, tmp_path, errors
        browser.close()
        assert not errors


def _export(page) -> dict:
    raw = page.locator("#selectionOut").input_value()
    assert raw, page.locator("#selectionError").text_content()
    return json.loads(raw)


def _import(page, data):
    page.locator("#selectionIn").fill(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
    page.locator("#importSelection").click()


def test_browser_exports_brand_and_local_edit_to_cli(page):
    tab, temp, _ = page
    tab.locator('#sceneOpts [data-s="wxillus"]').click()
    tab.locator('#palOpts [data-p="brand"]').click()
    tab.locator("#brandHex").fill("#AABBCC, #112233")
    tab.locator("#seriesId").fill("article-1")
    tab.locator("#itemId").fill("03")
    tab.locator("#itemForm").select_option("structure")
    tab.locator("#itemStructure").select_option("compare")
    tab.locator("#itemText").fill("标签短一些，条件不能省")
    tab.locator("#addItem").click()
    selected = _export(tab)
    assert selected["palette"]["custom"] == ["#AABBCC", "#112233"]
    assert selected["items"]["03"]["expression"]["structure"] == "compare"
    assert selected["items"]["03"]["text_direction"] == "标签短一些，条件不能省"
    normalized = _cli_normalize(temp, json.dumps(selected, ensure_ascii=False))
    assert normalized["series_id"] == "article-1"
    assert normalized["palette"]["custom"] == selected["palette"]["custom"]
    assert normalized["items"] == selected["items"]
    tab.locator('#palOpts [data-p="macaron"]').click()
    changed = _cli_normalize(temp, tab.locator("#selectionOut").input_value())
    assert changed["palette"]["family"] == "macaron" and "custom" not in changed["palette"]
    assert changed["items"]["03"] == normalized["items"]["03"]


def test_browser_import_roundtrip_and_conflicts(page):
    tab, temp, _ = page
    record = {"version": 1, "scene": "wxillus", "series_id": "trial-2",
              "style": {"code": "C31", "revision": 4, "source": "project", "scope": "series", "locked": True},
              "palette": {"family": "orig", "light": 0, "sat": 0, "source": "factory", "scope": "series", "locked": False},
              "expression": {"form": "auto", "structure": "auto", "source": "factory", "scope": "series", "locked": False},
              "items": {"03": {"expression": {"form": "structure", "structure": "compare", "source": "explicit", "scope": "item", "locked": True},
                               "text_direction": "短标签"}}}
    _import(tab, record)
    assert _cli_normalize(temp, tab.locator("#selectionOut").input_value()) == _cli_normalize(temp, json.dumps(record, ensure_ascii=False))
    _import(tab, "sb1:C31@r4-compare-balanced-orig")
    assert _export(tab)["expression"]["structure"] == "compare"
    assert _export(tab)["expression"]["density"] == "balanced"
    for broken, error in [({**record, "version": 2}, "版本"),
                          ({**record, "style": {"code": "C31", "revision": 999}}, "修订"),
                          ({**record, "style": {"code": "S01"}}, "不可用"),
                          ({**record, "style": {"code": "C02"}, "palette": {"family": "macaron"}}, "锁色")]:
        _import(tab, broken)
        assert error in tab.locator("#selectionError").text_content()
    _import(tab, "sb1:C31-brand.L0S0")
    assert "具体 HEX" in tab.locator("#selectionError").text_content()


def test_public_gallery_mobile_and_keyboard(page):
    tab, _, _ = page
    assert tab.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    tab.keyboard.press("Tab")
    assert tab.evaluate("document.activeElement && document.activeElement.tagName") == "BUTTON"
    assert "私有" not in json.dumps(json.loads(tab.locator("#meta").text_content())["cands"], ensure_ascii=False)


def test_browser_preference_file_imports_into_agent_and_can_forget(page):
    tab, temp, _ = page
    tab.locator('[data-tab="prefs"]').click()
    tab.locator("#prefScene").select_option("wxillus")
    tab.locator("#prefProject").fill("article-1")
    tab.locator("#prefValue").fill("C31")
    tab.locator("#prefSet").click()
    assert "C31" in tab.locator("#prefExplicit").text_content()
    first = temp / "pref-first.json"
    with tab.expect_download() as dl:
        tab.locator("#prefDownload").click()
    dl.value.save_as(first)
    env = {**os.environ, "STYLEBOOK_PROFILE": str(temp / "agent-profile")}
    def cli(*args):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "sb.py"), *args], env=env,
                              capture_output=True, text=True, cwd=ROOT)
        assert done.returncode == 0, done.stderr or done.stdout
        return json.loads(done.stdout)
    assert cli("preferences", "import", "--file", str(first))["imported"] == 1
    assert cli("preferences", "show", "--scene", "wxillus", "--project", "article-1")["effective"]["style"]["value"] == "C31"
    exported = temp / "pref-from-agent.json"
    cli("preferences", "export", "--file", str(exported))
    tab.locator("#prefFile").set_input_files(exported)
    tab.locator("#prefExplicit [data-pref-forget]").click()
    tab.locator("#prefPause").click()
    second = temp / "pref-second.json"
    with tab.expect_download() as dl:
        tab.locator("#prefDownload").click()
    dl.value.save_as(second)
    assert cli("preferences", "import", "--file", str(second))["imported"] == 0
    current = cli("preferences", "show", "--scene", "wxillus", "--project", "article-1")
    assert current["paused"] and current["effective"]["style"] is None
