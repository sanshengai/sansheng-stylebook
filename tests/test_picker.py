"""网站选择器：页面体积、样图齐全；用不带结尾斜杠的网址打开时图片必须能显示（曾因相对路径全部裂图）；
复制的 sb2 码能被 CLI 解析；「设为默认」与「只用一次」两条路径；任何用途下都不把选择面缩窄。"""
import contextlib
import http.server
import json
import sys
import threading
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
    assert html.stat().st_size < 250_000, "页面本体应只含文字与数据"
    assert len(list((d / "img").glob("*.webp"))) >= 57 * 3
    assert "data:image/webp" not in html.read_text(encoding="utf-8")


def test_build_is_deterministic(built, tmp_path):
    d, html = built
    again = BD.picker(tmp_path)
    assert again.read_bytes() == html.read_bytes()
    assert sorted(p.name for p in (tmp_path / "img").iterdir()) == sorted(p.name for p in (d / "img").iterdir())


def test_public_page_has_no_private_styles(built):
    import re
    _, html = built
    assert not re.search(r'"id":\s*"S\d', html.read_text(encoding="utf-8"))


def test_every_use_has_its_own_sample_kind_and_palettes_have_stories(built):
    _, html = built
    meta = json.loads(html.read_text(encoding="utf-8").split('<script id="meta" type="application/json">')[1].split("</script>")[0])
    assert {s["id"] for s in meta["scenes"]} >= {"wxcover", "wxillus", "xhs", "ppt", "info", "comic4"}
    named = [p for p in meta["pals"] if p["colors"]]
    assert len(named) >= 16 and all(p["story"] and p["en"] and p["group"] for p in named)


@contextlib.contextmanager
def serve(directory: Path):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(directory), **k)

        def translate_path(self, path):
            if path.split("?")[0].rstrip("/") == "/tools/stylebook":  # 线上就是这样：不带斜杠也直接给页面
                path = "/index.html"
            elif path.startswith("/tools/img/"):
                return str(directory / "__missing__")            # 相对路径写错时会落到这里
            elif path.startswith("/tools/stylebook/"):
                path = path[len("/tools/stylebook"):]
            return super().translate_path(path)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()


@pytest.fixture
def tab(built):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium 不可用：{exc}")
        with serve(built[0]) as base:
            page = browser.new_page(viewport={"width": 1280, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.base = base
            yield page
        browser.close()
        assert not errors


def _open(tab, frag=""):
    tab.goto(f"{tab.base}/tools/stylebook{frag}")   # 注意：没有结尾斜杠
    tab.wait_for_load_state("networkidle")


def test_images_load_when_opened_without_trailing_slash(tab):
    """不带结尾斜杠打开；每个用途下全部卡片（含「其余画风也能试试」）的图都要能加载，不能有裂图。"""
    for scene in ("wxcover", "xhs", "ppt", "comic4", "audio"):
        _open(tab, f"#u={scene}")
        tab.reload()
        tab.wait_for_selector(".card img")
        tab.evaluate("document.querySelectorAll('.card img').forEach(i=>{i.loading='eager'})")
        tab.wait_for_function("[...document.querySelectorAll('.card img')].every(i=>i.complete)", timeout=60000)
        # 本地测试服务器在几十张图同时请求时偶有连接失败：没加载出来的重新请求一次；路径写错的图重试也照样裂
        tab.evaluate("[...document.querySelectorAll('.card img')].filter(i=>!(i.naturalWidth>0)).forEach(i=>{const s=i.src;i.src='';i.src=s;})")
        tab.wait_for_function("[...document.querySelectorAll('.card img')].every(i=>i.complete)", timeout=60000)
        bad = tab.evaluate("[...document.querySelectorAll('.card img')].filter(i=>!(i.naturalWidth>0)).map(i=>i.src)")
        assert bad == [], (scene, bad[:5])


def test_selection_never_narrows_below_the_full_set(tab):
    _open(tab)
    total = len(json.loads(tab.evaluate("document.getElementById('meta').textContent"))["cands"])
    for scene in ("xhs", "ppt", "board", "info"):
        _open(tab, f"#u={scene}")
        assert tab.locator(".card").count() == total, scene


def test_copied_code_parses_roundtrips_and_modes_work(tab):
    _open(tab, "#u=xhs")
    tab.locator(".card").first.click()
    tab.click("[data-p=macaron]")
    tab.click('[data-k=light][data-v="-1"]')
    tab.click('[data-k=sat][data-v="1"]')
    code = tab.inner_text("#dCode")
    sc = SC.parse(code)
    assert (sc.scene, sc.palette, sc.light, sc.sat) == ("xhs", "macaron", -1, 1) and SC.validate(sc) == []
    tab.evaluate("window.__copied=null;navigator.clipboard.writeText=t=>{window.__copied=t;return Promise.resolve()}")
    tab.click("#btnOnce")
    once = tab.evaluate("window.__copied")
    assert code in once and "只用这一次" in once and "不要改我的默认" in once
    tab.click("#btnDefault")
    assert tab.inner_text("#trayN") == "1"
    tab.click("#dlgX")
    tab.click("#trayBtn")
    tab.click("#tCopy")
    text = tab.evaluate("window.__copied")
    assert code in text and "长期有效" in text
    # 刷新后「我的默认」仍在；网址还原同一选择
    tab.reload()
    assert tab.inner_text("#trayN") == "1"


def test_locked_style_cannot_be_recolored_and_brand_needs_hex(tab):
    _open(tab)
    meta = json.loads(tab.evaluate("document.getElementById('meta').textContent"))
    locked = next(c["id"] for c in meta["cands"] if c["recolor"] == "locked")
    _open(tab, f"#u=all&s={locked}")
    tab.wait_for_selector("#dlg[open]")
    assert tab.locator("[data-p=macaron]").is_disabled()
    _open(tab, "#u=info&s=C40")
    tab.wait_for_selector("#dlg[open]")
    tab.click("[data-p=brand]")
    assert tab.locator("#btnOnce").is_disabled()
    tab.fill("#hex", "1F6F8B F4F1E8")
    code = tab.inner_text("#dCode")
    assert code.endswith("-hex.1F6F8B.F4F1E8") and SC.parse(code).custom == ("#1F6F8B", "#F4F1E8")


def test_every_style_in_a_pool_has_that_uses_own_sample(built):
    _, html = built
    meta = json.loads(html.read_text(encoding="utf-8").split('<script id="meta" type="application/json">')[1].split("</script>")[0])
    imgs = {c["id"]: set(c["imgs"]) for c in meta["cands"]}
    # 音乐/播客封面必须有自己的 1:1 方形样图（不能拿 2.35:1 公众号封面充数）
    siblings = {"cm": {"cm", "cx", "ce"}, "wxi": {"wxi", "wxt", "wxx"}}  # 同组的兄弟种类也算本用途样图（页面同样按组回退）
    missing = [(s["id"], c) for s in meta["scenes"] for c in s["pool"]
               if not (siblings.get(s["sample"], {s["sample"]}) & imgs[c])]
    assert missing == [], f"这些画风缺它所属用途的样图：{missing[:8]}"


def test_set_labels_cover_every_page(built):
    """详情里每张图标页型名：PPT 12 页、信息图 11 种都要有名字，且与入库的张数对得上。"""
    _, html = built
    meta = json.loads(html.read_text(encoding="utf-8").split('<script id="meta" type="application/json">')[1].split("</script>")[0])
    assert len(meta["labels"]["ppt"]) == 12 and len(meta["labels"]["inf"]) == 11
    for c in meta["cands"]:
        for kind, cap in (("ppt", 12), ("inf", 11), ("xhs", 6)):
            n = sum(1 for k in c["imgs"] if k == kind or k.startswith(kind + "-"))
            assert n <= cap, (c["id"], kind, n)
    assert all(c.get("tone") and c.get("craft") for c in meta["cands"]), "三问推荐需要每个画风的气质与画法"


def test_quiz_recommends_only_from_the_chosen_use(tab):
    _open(tab, "#u=xhs")
    tab.click("#quizBtn")
    tab.wait_for_selector("#quiz[open]")
    tab.click("[data-qu=ppt]")
    tab.click("[data-qt=可爱童趣]")   # 黏土、毛绒、积木等立体可爱画风大多不做 PPT：过滤失效时它们会排进推荐
    tab.click("[data-qk=立体质感]")
    meta = json.loads(tab.evaluate("document.getElementById('meta').textContent"))
    pool = next(s["pool"] for s in meta["scenes"] if s["id"] == "ppt")
    tags = {c["id"]: c for c in meta["cands"]}
    picks = tab.eval_on_selector_all("[data-qpick]", "els=>els.map(e=>e.dataset.qpick)")
    assert 1 <= len(picks) <= 5 and all(p in pool for p in picks), picks
    first = tags[picks[0]]
    assert "可爱童趣" in first["tone"] or first["craft"] == "立体质感"
    tab.click(f"[data-qpick={picks[0]}]")
    tab.wait_for_selector("#dlg[open]")
    assert tab.inner_text("#dCode").startswith(f"sb2:ppt/{picks[0]}")
