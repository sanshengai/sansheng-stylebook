"""注册表与本地画廊。

registry.json 是网站与 Skill 共用的一份数据：样式目录 + 风格合同摘要 + 场景 / 表达结构 / 色系 / 格式。
- 公开版（仓库里那份）只含公开样式，任何 S 码、私有 profile 的内容都不许出现；
- 私有版（--private）叠加作者自己的 profile，只写到 gallery/build/ 这类不进仓库的位置；
- 每个风格合同都必须在目录里有一条、修订号一致；目录里有合同的条目必须与合同逐项对得上。

本地画廊：gallery/template.html（出厂默认 / 全部样式 / 选择器三页）+ 注册表 + 样图 → 单文件 HTML。
样图来源按优先级：测试矩阵出图（out/matrix/<码>@r<修订>/T*.png）→ --samples 目录（<码>-T3.png 或旧名 <码>-q1.png）。
合同锚点单独标为画风材质参考；公开示例单独标为单张测试图，均不冒充测试矩阵。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path

from . import contract as CT
from . import data as D

REGISTRY_PATH = CT.ROOT / "registry.json"
TEMPLATE = CT.ROOT / "gallery" / "template.html"
PICKER = CT.ROOT / "gallery" / "picker.html"
BUILD_DIR = CT.ROOT / "gallery" / "build"
# 旧同题测试的三题与标准测试题的对应：人物 → T3，场景 → T6，讲解 → T7
LEGACY_Q = {"q1": "T3", "q2": "T6", "q3": "T7"}
TEST_NAMES = {"T1": "半身表情", "T2": "两人互动", "T3": "老人与孩子", "T4": "动物", "T5": "静物", "T6": "远景",
              "T7": "抽象概念", "T8": "中文标题卡",
              "s1": "人物", "s2": "物件", "s3": "信息图"}  # s1–s3：画风库 v2 的同题样图（种树三题）


def _public_catalog() -> list[dict]:
    return json.loads((CT.ROOT / "styles" / "catalog.json").read_text(encoding="utf-8"))["styles"]


def _private_catalog() -> list[dict]:
    prof = CT.profile_dir()
    if not prof or not (prof / "catalog.json").is_file():
        return []
    return json.loads((prof / "catalog.json").read_text(encoding="utf-8"))["styles"]


def _contracts(private: bool) -> dict[str, dict]:
    out = {}
    for p in CT.contract_paths():
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("visibility") == "private" and not private:
            continue
        problems = CT.validate(c, where=p)
        if problems:
            raise CT.ContractError(c.get("code", p.parent.name), problems)
        out[c["code"]] = c
    return out


def _entry(cat: dict, visibility: str, c: dict | None) -> dict:
    e = {"code": cat["code"], "zh": cat["zh"], "family": cat["family"], "fit": cat["fit"], "visibility": visibility,
         "origin": cat.get("origin", ""), "status": cat.get("status", "draft"), "has_contract": c is not None,
         "recolor": cat.get("recolor", "free"), "recolor_note": cat.get("recolor_note", ""),
         "tone": cat.get("tone", []), "craft": cat.get("craft", "")}
    if c:
        pal = c["palette"]
        e.update({
            "en": c["name"]["en"], "revision": c["revision"], "essence": c["essence"],
            "recolor": pal["recolor"], "colors": pal.get("colors", []),
            "text_mode": c["recipe"].get("text_mode", []), "abilities": c.get("abilities", {}),
            "facets": c.get("facets", {}), "admission": (c.get("evidence") or {}).get("admission", "pending"),
            "tests": (c.get("evidence") or {}).get("tests", {}),
            "recipe_sha": hashlib.sha256(c["recipe"]["positive"].encode()).hexdigest()[:12],
        })
    return e


def registry(private: bool = False) -> dict:
    cons = _contracts(private)
    styles = [_entry(s, "public", cons.get(s["code"])) for s in _public_catalog()]
    if private:
        styles += [_entry(s, "private", cons.get(s["code"])) for s in _private_catalog()]
    scenes = []
    for sid, sc in D.scenes().items():
        s = dict(sc)
        if private:
            s["default"], s["alternates"], s["source"] = D.scene_choice(sid)
        scenes.append(s)
    return {
        "version": 1, "private": private,
        "styles": styles,
        "removed": json.loads((CT.ROOT / "styles" / "catalog.json").read_text(encoding="utf-8")).get("removed", []),
        "scenes": scenes,
        "structures": list(D.structures().values()),
        "palettes": D.palettes(),
        "formats": list(D.formats().values()),
        "tests": TEST_NAMES,
    }


def check(reg: dict) -> list[str]:
    """注册表自检：合同与目录一一对应、场景引用存在、公开版不漏私有内容。"""
    problems: list[str] = []
    codes = [s["code"] for s in reg["styles"]]
    dup = {c for c in codes if codes.count(c) > 1}
    if dup:
        problems.append(f"风格码重复：{sorted(dup)}")
    by = {s["code"]: s for s in reg["styles"]}
    removed = {r["code"] if isinstance(r, dict) else r for r in reg.get("removed", [])}
    for c in removed & set(codes):
        problems.append(f"已去掉的 {c} 又出现在目录里")
    cons = _contracts(reg["private"])
    for code, c in cons.items():
        e = by.get(code)
        if not e:
            problems.append(f"合同 {code} 在目录里没有条目")
        elif not e["has_contract"] or e.get("revision") != c["revision"] or e.get("recolor") != c["palette"]["recolor"]:
            problems.append(f"{code} 的注册表条目与合同对不上（修订 / 换色）")
    for code, e in by.items():
        if e["has_contract"] and code not in cons:
            problems.append(f"{code} 标着有合同，但找不到合同文件")
    for sc in reg["scenes"]:
        for code in [sc["default"], *sc["alternates"]]:
            if code not in by:
                problems.append(f"场景 {sc['id']} 引用了目录里没有的 {code}")
    if not reg["private"]:
        leaked = [c for c in codes if not c.startswith("C")] + [s["id"] for s in reg["scenes"] if s.get("source") == "作者档案"]
        blob = json.dumps(reg, ensure_ascii=False)
        if leaked or re.search(r"\bS\d{2,3}\b", blob):
            problems.append(f"公开注册表里出现了私有内容：{leaked or '文本里有 S 码'}")
    return problems


def write_registry(path: Path | None = None, private: bool = False) -> Path:
    reg = registry(private)
    problems = check(reg)
    if problems:
        raise ValueError("注册表自检不通过：" + "；".join(problems))
    path = Path(path) if path else (BUILD_DIR / "registry.private.json" if private else REGISTRY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------- 本地画廊 ----------------

def _enc(p: Path, m: int = 640, q: int = 72) -> str:
    from PIL import Image
    im = Image.open(p).convert("RGB")
    im.thumbnail((m, m))
    b = io.BytesIO()
    im.save(b, "WEBP", quality=q, method=6)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()


def _self_made_anchors() -> set[str]:
    """锚点是本项目自制风格参考板的画风：它已作为「风格参考板」样图展示，不再当「原作参考」重复列出。"""
    ledger = CT.ROOT / "styles" / "anchor-provenance.json"
    if not ledger.is_file():
        return set()
    return {e["style"] for e in json.loads(ledger.read_text(encoding="utf-8"))["anchors"]
            if (e.get("origin") or {}).get("repo") == "sanshengai/sansheng-stylebook"}


def collect_images(reg: dict, samples: list[Path] | None = None) -> dict[str, Path]:
    """键：<码>-<题号/anchor/example>。不同证据类型保留不同键。"""
    found: dict[str, Path] = {}
    mroot = CT.ROOT / "out" / "matrix"
    contract_paths = {p.parent.name: p for p in CT.contract_paths()}
    for s in reg["styles"]:
        code = s["code"]
        if s["has_contract"]:
            contract_path = contract_paths.get(code)
            if contract_path:
                contract = CT.load(code)
                anchor = contract.get("anchor") or {}
                if anchor and anchor.get("enabled", True) and code not in _self_made_anchors():
                    found[f"{code}-anchor"] = contract_path.parent / anchor["file"]
                for sample in contract.get("samples", []):  # 同题样图（人物 / 物件 / 信息图），键 s1/s2/s3
                    sp = contract_path.parent / sample["file"]
                    if sp.is_file():
                        found[f"{code}-{sp.stem}"] = sp
        if mroot.is_dir():
            runs = sorted(mroot.glob(f"{code}@r*"), key=lambda p: int(p.name.split("@r")[1]) if p.name.split("@r")[1].isdigit() else 0)
            if runs:
                for t in TEST_NAMES:
                    p = runs[-1] / f"{t}.png"
                    if p.is_file():
                        found.setdefault(f"{code}-{t}", p)
        for d in samples or []:
            for p in sorted(Path(d).glob(f"{code}-*.*")):
                m = re.fullmatch(rf"{code}-(T[1-8]|q[1-3])", p.stem)
                if m and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    t = LEGACY_Q.get(m.group(1), m.group(1))
                    found.setdefault(f"{code}-{t}", p)
    public_examples = {"C01": "C01-story-sample.png", "C32": "C32-infographic-sample.png"}
    for code, filename in public_examples.items():
        path = CT.ROOT / "assets" / filename
        if any(s["code"] == code for s in reg["styles"]) and path.is_file():
            found[f"{code}-example"] = path
    return found


def gallery(out: Path | None = None, private: bool = False, samples: list[Path] | None = None,
            legacy_prompts: Path | None = None) -> Path:
    reg = registry(private)
    problems = check(reg)
    if problems:
        raise ValueError("注册表自检不通过：" + "；".join(problems))
    imgs = {k: _enc(p) for k, p in collect_images(reg, samples).items()}
    cands = [{"id": s["code"], "name": s["zh"], "fam": s["family"], "tags": "·".join(s["fit"]), "src": s["origin"],
              "recolor": s["recolor"], "lock": s["recolor"] == "locked", "lockNote": s.get("recolor_note", ""), "vis": s["visibility"],
              "contract": s["has_contract"], "rev": s.get("revision"), "admission": s.get("admission", "pending"),
              "colors": s.get("colors", [])}
             for s in reg["styles"]]
    scenes = [{"id": sc["id"], "name": sc["zh"], "tag": sc["job"], "t": sc.get("preview_test", "T3"),
               "info": bool(sc.get("uses_structure")), "format": "、".join(D.formats()[f]["zh"] for f in sc["formats"] if f in D.formats()),
               "ar": D.formats()[sc["formats"][0]]["ratio"] if sc["formats"] and sc["formats"][0] in D.formats() else "1:1",
               "densAuto": sc.get("default_density", "balanced")} for sc in reg["scenes"] if not sc.get("hidden")]
    recs = {sc["id"]: [sc["default"], *sc["alternates"]] for sc in reg["scenes"] if not sc.get("hidden")}
    structs = [{"id": s["id"], "name": s["zh"], "fam": s["family"], "en": s["en"]} for s in reg["structures"]]
    meta = {"cands": cands, "recs": recs, "structs": structs, "pals": reg["palettes"]["palettes"], "scenes": scenes,
            "tests": TEST_NAMES,
            "private": private}
    h = TEMPLATE.read_text(encoding="utf-8")
    h = h.replace("__IMGS__", json.dumps(imgs)).replace("__META__", json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))
    out = Path(out) if out else BUILD_DIR / ("index.private.html" if private else "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(h, encoding="utf-8")
    return out


# ---------------- 选择器（浏览画风 → 选用途与色彩 → 设为默认 / 只用一次） ----------------
THUMB = 640  # 长边像素；外部文件，页面本体只放文字与数据
# 样图种类：同题三张（s1 人物 / s2 物件 / s3 信息图）是所有画风共有的横向对比；其余是按用途做的样图，每个用途看它最需要的东西。
SITE_KINDS = {
    "s1": "人物", "s2": "物件", "s3": "信息图（简）", "bd": "风格参考板",
    "cv": "封面", "au": "音乐封面", "wxi": "横版插图", "wxt": "竖版插图", "wxx": "推特单图", "xhs": "小红书", "ppt": "PPT", "inf": "信息图",
    "cm": "四格漫画", "cx": "日漫混排页", "ce": "知识条漫",
}
SET_KINDS = ["cv", "wxi", "wxt", "wxx", "xhs", "ppt", "inf", "cm", "cx", "ce"]
# 一组图：<种类> 是第一张，<种类>-2、-3…… 是同组后面的图
SET_RE = re.compile(r"^(" + "|".join(SET_KINDS) + r")(?:-(\d+))?$")
# 一组里每一张的名字（详情页缩略图下显示）
KIND_LABELS = {
    "ppt": ["封面", "目录", "章节页", "大数字", "数据", "对比", "四象限", "流程", "图文", "金句", "全幅图", "谢谢观看"],
    "inf": ["流程", "对比", "金字塔", "时间线", "数据看板", "便当格", "冰山", "循环", "中心辐射", "漏斗", "2×2 矩阵"],
    "xhs": ["封面", "第 2 页", "第 3 页", "第 4 页", "第 5 页", "总结卡"],
}
# 用途说明与网格里默认展示的样图：不同用途要的东西不一样，看图的角度也不一样。


PAL_SHOT_KEY = {"人物场景": "p", "物件静物": "o", "简易信息图": "i"}  # 色系真图的类别：人物、静物、信息图


def _pal_ids() -> set[str]:
    return {p["id"] for p in D.palettes()["palettes"] if p["id"] not in ("orig", "brand")}


def _pal_kind(stem: str) -> str | None:
    """色系真图的文件名是 pl-<色系 id>；返回色系 id，不是则 None。"""
    if stem.startswith("pl-") and stem[3:] in _pal_ids():
        return stem[3:]
    return None


def _sample_files(code: str, cp: Path | None) -> dict[str, tuple[Path, float | None]]:
    """合同登记的样图：键是样图种类（如 ppt-3），值是 (文件路径, 登记的宽高比)。

    公开下载包不带样图文件（样图在官网图片目录里），所以这里按合同登记返回，不要求文件存在；
    文件存在时由 picker() 校验登记比例与实际一致。"""
    out: dict[str, tuple[Path, float | None]] = {}
    if not cp:
        return out
    for sample in CT.load(code).get("samples", []):
        sp = cp.parent / sample["file"]
        if sp.stem in SITE_KINDS or SET_RE.match(sp.stem) or _pal_kind(sp.stem):
            out[sp.stem] = (sp, sample.get("ratio"))
    return out


def _thumb_bytes(p: Path, m: int = THUMB, q: int = 60) -> bytes:
    from PIL import Image
    im = Image.open(p).convert("RGB")
    im.thumbnail((m, m))
    b = io.BytesIO()
    im.save(b, "WEBP", quality=q, method=6)
    return b.getvalue()


def picker(out_dir: Path | None = None, private: bool = False) -> Path:
    """写出 index.html 与 img/<码>-<样图种类>.webp。样图缩成外部小文件懒加载；输出确定（无时间戳）。"""
    reg = registry(private)
    problems = check(reg)
    if problems:
        raise ValueError("注册表自检不通过：" + "；".join(problems))
    out_dir = Path(out_dir) if out_dir else BUILD_DIR
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob("*.webp"):
        old.unlink()
    contract_paths = {p.parent.name: p for p in CT.contract_paths()}
    self_anchors = _self_made_anchors()
    have: dict[str, list[str]] = {}
    ratios: dict[str, float] = {}
    pal_shots: dict[str, list[dict]] = {}
    expected_imgs: list[str] = []  # 页面会引用的全部缩略图文件名（含公开包里没有文件的样图）
    from PIL import Image
    for s in reg["styles"]:
        code = s["code"]
        cp = contract_paths.get(code)
        if not (s["has_contract"] and cp):
            continue
        files = _sample_files(code, cp)
        contract = CT.load(code)
        anchor = contract.get("anchor") or {}
        if anchor and anchor.get("enabled", True) and (cp.parent / anchor["file"]).is_file() and code not in self_anchors:
            files["anchor"] = cp.parent / anchor["file"]  # 开源原作样图；自制参考板已作为「风格参考板」展示
        for kind, entry in files.items():
            src, registered = entry if isinstance(entry, tuple) else (entry, None)
            base_kind = kind.split("-")[0]
            if src.is_file():
                (img_dir / f"{code}-{kind}.webp").write_bytes(_thumb_bytes(src))
                with Image.open(src) as im:
                    actual = round(im.width / im.height, 3)
                if registered is not None and abs(actual - registered) > 0.002:
                    raise ValueError(f"{code} 的样图 {kind} 登记比例 {registered} 与实际 {actual} 不一致")
                ratio = actual
            elif registered is not None:
                ratio = registered  # 无样图文件（公开包）：按合同登记
            else:
                raise ValueError(f"{code} 的样图 {kind} 缺少文件，合同里也没有登记宽高比")
            expected_imgs.append(f"{code}-{kind}.webp")
            if _pal_kind(kind):  # 色系真图：只出现在「色系」页，不进画风详情的样图列表
                topic = next((x.get("topic", "") for x in contract.get("samples", []) if Path(x["file"]).stem == kind), "")
                pal_shots.setdefault(_pal_kind(kind), []).append({"code": code, "kind": kind, "k": PAL_SHOT_KEY.get(topic.split("·")[-1], ""), "ratio": ratio})
                continue
            have.setdefault(code, []).append(kind)
            ratios.setdefault(base_kind, ratio)
    inspiration = {}
    for s in reg["styles"]:
        cp = contract_paths.get(s["code"])
        names = ((CT.load(s["code"]).get("inspiration") or {}).get("names") or []) if cp else []
        inspiration[s["code"]] = "、".join(names)
    scene_ids = [sc["id"] for sc in reg["scenes"] if not sc.get("hidden") and sc.get("use")]
    pools = {sc["id"]: [c for c in D.styles_for_use(sc["use"]) if c in have] for sc in reg["scenes"] if sc["id"] in scene_ids}
    cands = [{"id": s["code"], "name": s["zh"], "origin": inspiration.get(s["code"], ""), "recolor": s["recolor"],
              "recolorNote": s.get("recolor_note", ""), "essence": "；".join(s.get("essence", [])[:3]), "family": s.get("family", ""),
              "imgs": sorted(have[s["code"]]), "uses": [sid for sid in scene_ids if s["code"] in pools[sid]],
              "tone": s.get("tone", []), "craft": s.get("craft", "")}
             for s in reg["styles"] if s["code"] in have]
    scenes = []
    for sc in reg["scenes"]:
        if sc["id"] not in scene_ids:
            continue
        scenes.append({"id": sc["id"], "name": sc.get("site_name", sc["zh"]), "short": sc.get("site_short", sc.get("site_name", sc["zh"])),
                       "more": bool(sc.get("site_more")), "use": sc["use"], "sample": sc.get("site_sample", "s1"), "note": sc.get("site_note", ""), "default": sc["default"],
                       "alternates": [a for a in sc["alternates"] if a in have], "pool": pools[sc["id"]]})
    pals = [{"id": p["id"], "name": p["name"], "en": p.get("en", ""), "group": p.get("group", ""), "story": p.get("story", ""),
             "colors": p.get("colors", [])} for p in reg["palettes"]["palettes"]]
    meta = {"cands": cands, "scenes": scenes, "pals": pals, "kinds": SITE_KINDS, "labels": KIND_LABELS, "ratios": ratios, "first": "wxcover",
            "palShots": {k: sorted(v, key=lambda x: ("poi".find(x["k"]), x["code"])) for k, v in sorted(pal_shots.items())}}
    html = PICKER.read_text(encoding="utf-8").replace("__META__", json.dumps(meta, ensure_ascii=False, sort_keys=True).replace("</", "<\\/"))
    out = out_dir / ("index.private.html" if private else "index.html")
    out.write_text(html, encoding="utf-8")
    if not private:  # 官网投影检查据此核对官网图片目录：缺一张或多一张都要红
        (out_dir / "img-manifest.json").write_text(
            json.dumps({"schema_version": 1, "images": sorted(expected_imgs)}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out
