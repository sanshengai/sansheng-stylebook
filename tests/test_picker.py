"""网站选择器：页面本体体积、样图齐全，浏览器里复制出的 sb2 码必须能被 CLI 的解析器接受并还原选择。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import build as BD  # noqa: E402
from stylebook import stylecode as SC  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("picker")
    return d, BD.picker(d)


def test_page_is_small_and_images_are_external(built):
    d, html = built
    assert html.stat().st_size < 200_000, "页面本体应只含文字与数据"
    imgs = list((d / "img").glob("*.webp"))
    assert len(imgs) >= 57 * 3
    assert "data:image" not in html.read_text(encoding="utf-8")


def test_build_is_deterministic(built, tmp_path):
    d, html = built
    again = BD.picker(tmp_path)
    assert again.read_bytes() == html.read_bytes()
    assert sorted(p.name for p in (tmp_path / "img").iterdir()) == sorted(p.name for p in (d / "img").iterdir())


def test_public_page_has_no_private_styles(built):
    import re
    _, html = built
    assert not re.search(r'"id":\s*"S\d', html.read_text(encoding="utf-8"))


@pytest.fixture
def tab(built):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium 不可用：{exc}")
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(built[1].resolve().as_uri())
        yield page
        browser.close()
        assert not errors


def test_copied_code_parses_and_roundtrips(tab):
    tab.goto(tab.url.split("#")[0] + "#u=xhs")
    tab.reload()
    code = tab.inner_text("#code")
    sc = SC.parse(code)
    assert sc.scene == "xhs" and sc.style == "C31" and sc.palette == "orig"
    tab.click("[data-p=macaron]")
    tab.click('[data-k=light][data-v="-1"]')
    tab.click('[data-k=sat][data-v="1"]')
    sc = SC.parse(tab.inner_text("#code"))
    assert (sc.palette, sc.light, sc.sat) == ("macaron", -1, 1)
    assert SC.validate(sc) == []
    # 状态写进网址，刷新后还原
    tab.reload()
    assert tab.inner_text("#code") == "sb2:xhs/C31-macaron.L-1S1"


def test_locked_style_cannot_be_recolored_and_brand_needs_hex(tab):
    import json
    meta = json.loads(tab.evaluate("document.getElementById('meta').textContent"))
    locked = next(c["id"] for c in meta["cands"] if c["recolor"] == "locked")
    sc = next(s for s in meta["scenes"] if locked in s["pool"])
    tab.goto(tab.url.split("#")[0] + f"#u={sc['id']}&s={locked}&p=macaron")
    tab.reload()
    assert "-macaron" not in tab.inner_text("#code") or tab.locator("[data-p=macaron]").is_disabled()
    assert tab.locator("[data-p=macaron]").is_disabled()
    tab.click("[data-p=brand]") if not tab.locator("[data-p=brand]").is_disabled() else None
    tab.goto(tab.url.split("#")[0] + "#u=info&s=C40")
    tab.reload()
    tab.click("[data-p=brand]")
    assert tab.locator("#copy").is_disabled()
    tab.fill("#hex", "1F6F8B F4F1E8")
    code = tab.inner_text("#code")
    assert code.endswith("-hex.1F6F8B.F4F1E8") and SC.parse(code).custom == ("#1F6F8B", "#F4F1E8")
