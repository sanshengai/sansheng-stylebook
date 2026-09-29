"""编译器：配方清单 → 固定顺序的提示词 → 按目标模型改写。

原则（见 references/compile.md）：
- 锁定层（风格合同的 recipe.positive）原样使用，编译器与 Agent 都不许改写；
- 段落顺序固定：锁定层 → 主体 → 关系与空间 → 镜头 → 光线 → 色彩 → 背景 → 结构与密度 → 用途 → 文字 → 画幅 → 约束；
- 同一份清单编译两次必须逐字相同（不引入随机、时间、无序集合）；
- 内容里出现风格合同的冲突词就拦下来，不静默放行。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import contract as CT
from . import data as D
from .comic import validate_content as validate_comic_content
from .textspec import MODES, native_items, validate_hybrid
from . import palette as PL
from .sizes import gen_size

MODEL_FAMILY = {
    "gpt-image-2": "gpt-image", "gpt-image-2-c": "gpt-image", "gpt-image-2.5": "gpt-image", "gpt-image-1.5": "gpt-image",
    "gemini-3-pro-image": "gemini", "gemini-3.1-flash-image": "gemini", "gemini-3.1-flash-lite-image": "gemini",
    "doubao-seedream": "seedream", "seedream": "seedream", "qwen-image": "gemini", "wan2.7-image": "gemini",
    "flux": "flux", "midjourney": "midjourney",
}

DENSITY_TEXT = {
    "sparse": "Information density: sparse — only 1–2 key points, large and clear, with generous empty space.",
    "balanced": "Information density: balanced — 3–4 key points.",
    "dense": "Information density: dense — 5–8 key points arranged in clear modules.",
}
ROLE_TEXT = {
    "style": "use it only as a style reference — take its line work, brushwork, medium, texture, colour tendency and overall visual language; do not copy any subject, person, clothing, pose, setting, composition, layout, text or story from it",
    "identity": "character identity reference — keep this character's face, hairstyle, body shape and signature clothing exactly",
    "identity_face": "face identity reference only — preserve the character's facial features, hairstyle and distinctive face or hair accessories; take clothing, pose, body framing, setting and props only from the subject instructions, not from this image",
    "pose": "pose reference only",
    "composition": "composition guide only — preserve relative placement, scale, focal hierarchy and spatial relationships of required elements; do not copy its medium, colors, texture, lighting, character identity, incidental props or text",
    "background": "background and setting reference only",
    "product": "the real object that must appear, keep its shape and details",
}
ROLE_TEXT_ZH = {"style": "只作画风参考，只学线条、笔触、媒介、材质、色彩倾向与整体视觉语言，不照搬其中的人物、服装、姿势、场景、构图、文字或情节",
                "identity": "角色身份参考，保持这个角色的五官、发型、体型与标志性服装",
                "identity_face": "只作面部身份参考，保持五官、发型及有辨识度的眼镜或发饰；服装、姿势、取景、场景和道具只按主体说明，不从参考图照搬",
                "pose": "只作姿势参考",
                "composition": "只作构图参考，保持必要元素的相对位置、大小、视觉主次和空间关系；不照搬媒介、颜色、纹理、光线、角色身份、偶然道具或文字",
                "background": "只作背景与场景参考", "product": "必须出现的真实物件，保持其外形与细节"}


class CompileError(ValueError):
    pass


@dataclass
class Compiled:
    prompt: str
    model: str
    family: str
    style: str
    aspect: str
    size: tuple[int, int]
    export_px: tuple[int, int] | None
    references: list[dict] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    manifest_hash: str = ""

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


def manifest_hash(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _content_text(manifest: dict) -> str:
    c = manifest.get("content", {})
    parts = [c.get(k, "") for k in ("subject", "relations", "lighting", "background", "mood", "purpose")]
    cam = c.get("camera") or {}
    parts += [str(v) for v in cam.values()]
    for ch in c.get("characters", []) or []:
        parts.append(ch.get("desc", ""))
    return " ".join(p for p in parts if p).lower()


def _norm_words(s: str) -> str:
    """连字符、下划线、多个空白都当成一个空格，避免 mustard-yellow 绕过 mustard yellow。"""
    return " " + re.sub(r"[\s\-_/]+", " ", s.lower()).strip() + " "


def _check_bans(contract: dict, manifest: dict) -> None:
    text = _norm_words(_content_text(manifest))
    hits = [b for b in contract.get("prompt_bans", []) if _norm_words(b) in text]
    if hits:
        raise CompileError(f"{contract['code']} 的冲突词出现在内容里：{hits}。改写内容，或换一个样式")


def _palette_section(contract: dict, manifest: dict) -> str | None:
    p = manifest.get("palette") or {"family": "orig"}
    fam, light, sat = p.get("family", "orig"), int(p.get("light", 0)), int(p.get("sat", 0))
    rule = contract["palette"]["recolor"]
    if fam != "orig" and rule != "free":
        raise CompileError(f"{contract['code']} 的颜色{'锁定' if rule == 'locked' else '只允许调深浅'}，不能换成色系 {fam}")
    if fam == "orig":
        if not (light or sat):
            return None
        if rule == "locked":
            raise CompileError(f"{contract['code']} 的颜色锁定，不能调深浅或鲜灰")
        if rule == "lightness_only" and sat:
            raise CompileError(f"{contract['code']} 只允许调深浅，不能调鲜灰")
        base = contract["palette"].get("colors") or []
        if not base:
            raise CompileError(f"{contract['code']} 合同里没有登记原色，无法按原色调深浅")
        cols = [{"name": c["name"], "hex": PL.adjust(c["hex"], light, sat)} for c in base]
    else:
        cols = PL.resolve(fam, light, sat, p.get("custom"))
    listing = ", ".join(f"{c['name']} {c['hex']}" for c in cols)
    return (f"Colour palette (use only these colours; each name goes with its hex): {listing}. "
            "Only the colours change; keep the style's rendering technique, line work and texture unchanged.")


def _structure_section(manifest: dict, fmt: dict | None) -> list[str]:
    out = []
    st = manifest.get("structure")
    if st:
        if st == "auto":
            out.append("Layout structure: choose the clearest structure for this content (sequence → flow or timeline; "
                       "two or three options → comparison; hierarchy → pyramid or layers; parts of a whole → card grid; overlap → Venn).")
        else:
            s = D.structures().get(st)
            if not s:
                raise CompileError(f"未知表达结构 {st}")
            out.append(f"Layout structure: {s['en']}.")
    dens = manifest.get("density")
    if dens:
        if dens not in DENSITY_TEXT:
            raise CompileError(f"未知密度 {dens}")
        out.append(DENSITY_TEXT[dens])
    return out


def _text_section(manifest: dict, fmt: dict | None, family: str, text_style: str = "", *,
                  reserve_default: str = "the top area") -> str:
    t = manifest.get("text") or {}
    mode = t.get("mode") or ((fmt or {}).get("text") or {}).get("default", "none")
    if mode not in MODES:
        raise CompileError(f"未知文字档位 {mode!r}")
    if mode == "hybrid":
        problems = validate_hybrid(t)
        if problems:
            raise CompileError("hybrid 文字清单不合格：" + "；".join(problems))
    items = native_items(t) if mode in ("native", "hybrid") else []
    if items:
        q = "「{}」" if family == "gpt-image" else '"{}"'
        # 「label」会诱导模型给每条字加胶囊底板（S01 r3/r4、C24 同题测试都出现），改用中性说法
        role_word = {"label": "short text", "caption": "short text"}
        lines = "; ".join(f"{role_word.get(it.get('role', 'text'), it.get('role', 'text'))}: {q.format(it['text'])}"
                          + (f" at {it['position']}" if it.get("position") else "") for it in items)
        font = t.get("font")
        prompt = (f"Text in the image, exactly as written (no other text): {lines}." + (f" Lettering: {font}." if font else "")
                + " Every character must be correct and legible. Do not add step numbers or unrequested digits on props,"
                " timers, clocks, dials, screens, or diagrams; show sequence with arrows or unnumbered marks."
                + (f" {text_style.strip()}" if text_style else ""))
        if mode == "hybrid":
            prompt += (f" Reserve {t['reserve'].strip()} as clean, empty, material-matched space for exact text added"
                       " after image generation. Render no letters, symbols or pseudo-text in that reserved space."
                       " The native lettering instructions apply only to the text listed above.")
        return prompt
    if mode == "overlay":
        where = t.get("reserve", reserve_default)
        prompt = f"Leave clean, uncluttered empty space at {where} for text that will be added later; no text, letters or captions anywhere in the image."
        if t.get("items"):
            from .overlay import validate
            problems = validate(t)
            if problems:
                raise CompileError("overlay 文字清单不合格：" + "；".join(problems))
            boxes = [item["box"] for item in t["items"] if item.get("require_blank", False)]
            if boxes:
                prompt += (" Exact final text rectangles, normalized [x,y,width,height]: "
                           + json.dumps(boxes, separators=(",", ":"))
                           + ". Keep every rectangle free of outlines, arrows, icons, letters and dark marks;"
                           " a uniform material-matched background is allowed. These coordinates come from the"
                           " actual final lettering specification; place all non-text objects outside them.")
        return prompt
    return "No text, letters or captions anywhere in the image."


def compile_manifest(manifest: dict, contract: dict | None = None, *, stage: str | None = None) -> Compiled:
    """manifest 必须字段：style、model；content.subject。其余可选。"""
    if contract is None:
        contract = CT.load(manifest["style"])
    else:
        problems = CT.validate(contract)
        if problems:
            raise CompileError("合同不合格：" + "；".join(problems))
    want_rev = manifest["style"].split("@r")[1] if "@r" in manifest["style"] else None
    if want_rev and int(want_rev) != contract["revision"]:
        raise CompileError(f"项目锁定在 {manifest['style']}，当前合同是 r{contract['revision']}；先确认是否升级")
    model = manifest.get("model", "gpt-image-2")
    family = MODEL_FAMILY.get(model, "gpt-image")
    fmt = D.formats().get(manifest.get("format", "")) if manifest.get("format") else None
    text = manifest.get("text") or {}
    if fmt and text.get("mode", fmt.get("text", {}).get("default")) in ("native", "hybrid"):
        title_limit = fmt.get("text", {}).get("title_max_chars")
        if title_limit:
            for item in native_items(text):
                if item.get("role") == "title" and len(item["text"]) > title_limit:
                    raise CompileError(
                        f"标题「{item['text']}」{len(item['text'])} 字，超过「{fmt['zh']}」上限 {title_limit} 字"
                    )
    if stage not in (None, "center_square_master"):
        raise CompileError(f"未知编译阶段 {stage}")
    if stage == "center_square_master" and manifest.get("format") != "wechat-cover-head":
        raise CompileError("方形母版阶段目前只支持 wechat-cover-head")
    aspect = "1:1" if stage == "center_square_master" else manifest.get("aspect") or (fmt or {}).get("ratio", "1:1")
    content = manifest.get("content") or {}
    if not content.get("subject"):
        raise CompileError("content.subject 必填")
    comic_problems = validate_comic_content(manifest.get("format"), content)
    if comic_problems:
        raise CompileError("；".join(comic_problems))
    _check_bans(contract, manifest)

    rec = contract["recipe"]
    sec: list[tuple[str, str]] = []
    lock = rec["positive"].strip()
    if rec.get("constraints_first") and rec.get("hard_constraints"):
        lock = "Most important: " + " ".join(rec["hard_constraints"]) + "\n" + lock
    sec.append(("lock", "Visual style (follow exactly): " + lock))
    text_mode = (manifest.get("text") or {}).get("mode") or ((fmt or {}).get("text") or {}).get("default", "none")
    if stage == "center_square_master":
        square_content = ("Leave the left title zone clear for exact text added after generation; place the full "
                          "subject and every evidence badge " if text_mode == "overlay" else
                          "Place ALL meaningful letters, the full subject and every evidence badge ")
        sec.append(("stage", "Production stage: create the ORIGINAL 1:1 square master for a later 2.35:1 "
                    "WeChat headline banner. The entire square will be preserved as the centered square crop "
                    "of that banner. " + square_content +
                    "inside the central 70% of this square's width and central 70% of its height, with at "
                    "least 15% quiet background padding on every side. Keep the left title zone and right "
                    "open evidence collage distinct inside this square. Draw the main object and every badge "
                    "as simplified FLAT-VECTOR illustrations: a few solid tonal shapes, crisp contours and "
                    "restrained same-hue halftone, without photographic texture or realistic product rendering. "
                    "Do not add decorative facts or props absent from the subject brief. The square itself "
                    "must read at 383×383 pixels; do not make a full-bleed poster."))
    subj = content["subject"].strip()
    panels = content.get("panels") or []
    if panels:
        subj += " " + " ".join(f"Panel {i}: {p.strip()}" for i, p in enumerate(panels, 1))
    chars = content.get("characters") or []
    if chars:
        subj += " Characters: " + "; ".join(f"{c.get('id', '')} — {c['desc']}" for c in chars) + "."
    sec.append(("subject", "Subject: " + subj))
    inventory = content.get("inventory")
    if inventory is not None:
        if not isinstance(inventory, str) or not inventory.strip():
            raise CompileError("content.inventory 必须是非空文字")
        sec.append(("inventory", "Content inventory (literal): " + inventory.strip()))
    if content.get("relations"):
        sec.append(("relations", "Spatial relationships: " + content["relations"].strip()))
    points = content.get("points")
    if points is not None:
        if not isinstance(points, list) or not points or any(not isinstance(p, str) or not p.strip() for p in points):
            raise CompileError("content.points 必须是非空文字列表")
        sec.append(("points", "Required content points, in source order. Preserve each condition, negation, number and unit; depict their meaning even when the exact words are not printed: "
                    + " ".join(f"{i}. {point.strip()}" for i, point in enumerate(points, 1))))
    cam = content.get("camera") or {}
    if cam:
        order = ("shot", "angle", "lens", "focus", "composition")
        sec.append(("camera", "Camera: " + "; ".join(f"{k} {cam[k]}" for k in order if cam.get(k)) + "."))
    if content.get("lighting"):
        sec.append(("lighting", "Lighting: " + content["lighting"].strip()))
    pal = _palette_section(contract, manifest)
    if pal:
        sec.append(("palette", pal))
    if content.get("background"):
        sec.append(("background", "Background: " + content["background"].strip()))
    for s in _structure_section(manifest, fmt):
        sec.append(("structure", s))
    structure = manifest.get("structure")
    structure_prompt = (rec.get("structure_prompts") or {}).get(structure)
    if structure_prompt:
        sec.append(("structure_style", f"Style layout for {structure} (follow exactly): {structure_prompt}"))
    if content.get("purpose") or content.get("mood"):
        sec.append(("purpose", "Purpose and mood: " + " ".join(x for x in (content.get("purpose", ""), content.get("mood", "")) if x).strip()))
    text_style = (rec.get("text_style_hybrid", rec.get("text_style", "")) if text_mode == "hybrid"
                  else rec.get("text_style", ""))
    reserve_default = ("the left title zone inside the central 70% safe area"
                       if stage == "center_square_master" else "the top area")
    sec.append(("text", _text_section(manifest, fmt, family, text_style,
                                       reserve_default=reserve_default)))
    compose = ("A complete 1:1 square master with safe side margins; keep all high-contrast marks at "
               "least 15% in from each edge. The later landscape wings contain background only. "
               "The final image must stay flat-vector, without photographic collage." if stage == "center_square_master"
               else (fmt or {}).get("compose"))
    background = ("Keep the background fully opaque across the whole canvas, including every corner; "
                  "no transparency, alpha fade, or cutout edge. " if not (fmt or {}).get("transparent") else "")
    sec.append(("format", (f"{compose} " if compose else "") + background + f"Aspect ratio {aspect}."))
    fixes = manifest.get("fixes") or []
    if fixes:  # 返修：上一张没做到的地方，写成正面要求
        sec.append(("fixes", "Correct these points from the previous attempt: " + " ".join(f.strip().rstrip(".") + "." for f in fixes)))
    if not rec.get("constraints_first") and rec.get("hard_constraints"):
        sec.append(("constraints", " ".join(rec["hard_constraints"])))
    variant = (contract.get("model_variants") or {}).get(model, {}).get("append")
    if variant:
        sec.append(("variant", variant))

    refs = manifest.get("references") or []
    for r in refs:
        if r.get("role") not in ROLE_TEXT:
            raise CompileError(f"参考图职责必须是 {list(ROLE_TEXT)} 之一：{r}")
    anchor = contract.get("anchor") or {}
    ref_list = list(refs)
    anchor_enabled = bool(anchor.get("file") and manifest.get("use_anchor", True))
    if anchor_enabled:
        anchor_path = Path(anchor["file"])
        if not anchor_path.is_absolute() and contract.get("_path"):
            anchor_path = Path(contract["_path"]).parent / anchor_path
        ref_list = [{"path": str(anchor_path), "role": "style"}] + [r for r in refs if r.get("role") != "style"]

    anchor_isolation = anchor.get("isolation", "").strip() if anchor_enabled else ""
    prompt, params = _dialect(family, sec, ref_list, contract, aspect, anchor_isolation)
    return Compiled(prompt=prompt, model=model, family=family, style=f"{contract['code']}@r{contract['revision']}",
                    aspect=aspect, size=gen_size(aspect, model, max([1536, *((fmt or {}).get("export_px") or [])])),
                    export_px=None if stage == "center_square_master" else tuple((fmt or {}).get("export_px", [])) or None,
                    references=ref_list, params=params, manifest_hash=manifest_hash(manifest))


def _dialect(family: str, sec: list[tuple[str, str]], refs: list[dict], contract: dict,
             aspect: str, anchor_isolation: str = "") -> tuple[str, dict]:
    params: dict = {}
    if family == "gpt-image":
        head = [f"Image {i + 1}: {ROLE_TEXT[r['role']]}." for i, r in enumerate(refs)]
        if anchor_isolation:
            head[0] += f" Anchor isolation: {anchor_isolation}"
        body = [t for _, t in sec]
        return "\n".join(head + ([""] if head else []) + body), params
    if family in ("gemini", "seedream"):
        if family == "seedream":
            head = [f"图{'一二三四五六七八九十'[i]}：{ROLE_TEXT_ZH[r['role']]}。" for i, r in enumerate(refs)]
        else:
            head = [f"The {['first', 'second', 'third', 'fourth', 'fifth', 'sixth'][i]} image is a {ROLE_TEXT[r['role']]}." for i, r in enumerate(refs)]
        if anchor_isolation:
            head[0] += f" Anchor isolation: {anchor_isolation}"
        # 叙事段落：去掉标签式开头，合成连贯段落；不写排除清单
        body = " ".join(t.split(": ", 1)[1] if ": " in t[:40] else t for _, t in sec)
        return "\n".join(head + ([""] if head else []) + [body]), params
    if family == "flux":
        # 越靠前权重越高：锁定层与主体放最前，其余按原顺序
        first = [t for k, t in sec if k in ("lock", "subject")]
        rest = [t for k, t in sec if k not in ("lock", "subject")]
        head = [f"Image {i + 1}: {ROLE_TEXT[r['role']]}." for i, r in enumerate(refs)]
        if anchor_isolation:
            head[0] += f" Anchor isolation: {anchor_isolation}"
        return "\n".join(head + first + rest), params
    if family == "midjourney":
        body = " ".join(t for k, t in sec if k not in ("constraints",))
        if anchor_isolation:
            body = f"Anchor reference isolation: {anchor_isolation} " + body
        bans = [b for b in contract.get("prompt_bans", [])][:8]
        params = {"ar": aspect, "no": bans}
        tail = f" --ar {aspect}" + (f" --no {', '.join(bans)}" if bans else "")
        return body + tail, params
    raise CompileError(f"未知模型家族 {family}")
