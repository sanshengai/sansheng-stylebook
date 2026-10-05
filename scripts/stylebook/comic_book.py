"""整册漫画的分镜文档检查（知识漫画 / 概念漫画 / 四格寓言）。规则见 references/scenes/comic.md。

只做确定性检查：页数档位、逐格要素、对白长度、页末钩子、概念到道具的映射、「对着黑板讲」的连续讲课格、结尾四要素、页标题不是章节名、
角色圣经（复用 character.validate）。不出图、不调用模型。
"""
from __future__ import annotations

import re

from . import character as CH

TIERS = {"short": (5, 8), "medium": (9, 15), "full": (16, 25)}
PRESETS = ("knowledge", "concept", "fable4")
SHOTS = {"大远景", "远景", "全景", "中景", "近景", "特写", "俯拍", "仰拍"}
KINDS = {"talk", "action", "reveal"}
CLOSING = ("takeaway", "action", "callback", "open_question")
TALK_RUN = {"knowledge": 2, "concept": 4, "fable4": 99}   # 连续讲课格上限
DIALOGUE_MAX = 12
PAGE_DIALOGUE_MAX = 6
CHAPTER_TITLE = re.compile(r"^(第.{1,3}[章节页回]|chapter\s*\d+|page\s*\d+)", re.I)
IP = re.compile(r"哆啦|多啦|doraemon|柯南|conan|皮卡丘|pikachu|米老鼠|mickey|海绵宝宝|spongebob|蜡笔小新|hello\s*kitty", re.I)


def check(doc: dict) -> list[str]:
    p: list[str] = []
    preset = doc.get("preset")
    if preset not in PRESETS:
        return [f"preset 只接受 {PRESETS}"]
    pages = doc.get("pages")
    if not isinstance(pages, list) or not pages:
        return ["pages 为空"]
    if preset == "fable4":
        if len(pages) != 1:
            p.append("四格寓言只能 1 页")
        elif len(pages[0].get("panels", [])) != 4:
            p.append("四格寓言必须正好 4 格，不许第 5 格")
    else:
        tier = doc.get("tier")
        if tier not in TIERS:
            p.append(f"tier 只接受 {list(TIERS)}")
        elif not TIERS[tier][0] <= len(pages) <= TIERS[tier][1]:
            p.append(f"{tier} 档要 {TIERS[tier][0]}–{TIERS[tier][1]} 页，现在 {len(pages)} 页")
    # 角色
    chars = doc.get("characters") or []
    if not chars:
        p.append("没有角色设定；多页漫画要先有角色圣经和角色参考表" if preset != "fable4" else "四格寓言也要写角色")
    for ch in chars:
        p += [f"角色 {ch.get('id', '?')}：{x}" for x in CH.validate(ch)]
        if IP.search(" ".join(str(v) for v in ch.values())):
            p.append(f"角色 {ch.get('id', '?')}：出现了现成角色的名字，班底必须原创")
    # 概念到道具
    concepts = {c.get("id"): c for c in doc.get("concepts", []) if isinstance(c, dict)}
    if preset in ("knowledge", "concept"):
        if not concepts:
            p.append("缺 concepts：每个核心概念都要映射到一件道具或一个场景")
        for cid, c in concepts.items():
            if not c.get("prop"):
                p.append(f"概念 {cid} 没有对应的道具或场景")
    used: set[str] = set()
    for i, page in enumerate(pages, 1):
        tag = f"第 {i} 页"
        if page.get("n") != i:
            p.append(f"{tag}：页号 n 必须依次为 {i}")
        if not str(page.get("core", "")).strip():
            p.append(f"{tag}：缺本页核心信息（一句话）")
        title = str(page.get("title", ""))
        if preset != "fable4" and (not title.strip() or CHAPTER_TITLE.match(title.strip())):
            p.append(f"{tag}：页标题要写成叙事式，不要写成「{title or '空'}」这样的章节名")
        panels = page.get("panels")
        if not isinstance(panels, list) or not panels:
            p.append(f"{tag}：没有分格")
            continue
        sentences = 0
        run = 0
        has_action = False
        for j, pn in enumerate(panels, 1):
            pt = f"{tag}第 {j} 格"
            if pn.get("shot") not in SHOTS:
                p.append(f"{pt}：景别要写成 {sorted(SHOTS)} 之一")
            for k, name in (("scene", "场景"), ("light", "时间光线"), ("action", "动作表情")):
                if not str(pn.get(k, "")).strip():
                    p.append(f"{pt}：缺{name}")
            kind = pn.get("kind")
            if kind not in KINDS:
                p.append(f"{pt}：kind 只接受 {sorted(KINDS)}")
            for line in pn.get("dialogue", []):
                sentences += 1
                if len(re.sub(r"\s", "", line)) > DIALOGUE_MAX:
                    p.append(f"{pt}：对白超过 {DIALOGUE_MAX} 字：{line}")
            if kind == "talk":
                run += 1
                if run > TALK_RUN[preset]:
                    p.append(f"{tag}：连续 {run} 格都在讲课，最多 {TALK_RUN[preset]} 格；用道具或行动讲")
                if preset == "knowledge" and not pn.get("concept"):
                    p.append(f"{pt}：知识漫画的讲课格必须挂一个概念道具，不能「对着黑板讲」")
            else:
                run = 0
                has_action = has_action or kind in ("action", "reveal")
            if pn.get("concept"):
                if pn["concept"] not in concepts:
                    p.append(f"{pt}：引用了不存在的概念 {pn['concept']}")
                used.add(pn["concept"])
        if sentences > PAGE_DIALOGUE_MAX:
            p.append(f"{tag}：全页对白 {sentences} 句，超过 {PAGE_DIALOGUE_MAX} 句")
        if preset == "concept" and not has_action:
            p.append(f"{tag}：每页至少 1 个行动格")
        if i < len(pages) and preset != "fable4" and not str(page.get("hook", "")).strip():
            p.append(f"{tag}：缺页末钩子（让读者翻页的悬念）")
    for cid in concepts:
        if cid not in used and preset in ("knowledge", "concept"):
            p.append(f"概念 {cid} 的道具从没出现在任何一格")
    if preset == "knowledge":
        closing = doc.get("closing") or {}
        for k in CLOSING:
            if not str(closing.get(k, "")).strip():
                p.append(f"知识漫画结尾缺 {k}（需要一句结论、一个可带走的动作、一个回扣开头的画面、一个未解的问题）")
    return p
