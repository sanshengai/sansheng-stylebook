"""图片型 PPT 的规划层：页预算（由论点数推）和页规格卡检查。

公式与阈值来自 references/scenes/ppt.md（调研报告 03），常数是建议值，没有用真实稿件回测，所以结果里带 `calibrated: false`。
本模块只做确定性运算与检查，不调用模型、不出图。
"""
from __future__ import annotations

import re

MODES = ("talk", "talk-read", "read")  # 演讲式 / 讲读兼顾（默认）/ 阅读式
BODY_LIMIT = {"talk": 50, "talk-read": 100, "read": 180}   # 每页正文汉字上限
TITLE_LIMIT = 24
R_RANGE = {"talk": (500, 900), "talk-read": (350, 600), "read": (250, 450)}
MAIN_CAP = 28
INCLUDE = {"talk": {"must"}, "talk-read": {"must", "should"}, "read": {"must", "should"}}
STRUCT_TYPES = {"cover", "summary", "agenda", "chapter", "closing", "appendix", "recap"}
CHAR = re.compile(r"[一-鿿]")


class DeckError(ValueError):
    pass


def infer_mode(scene_text: str) -> str:
    """用户没说就按场景推；不确定归讲读兼顾。"""
    if re.search(r"上台|讲课|课堂|直播|开会讲|演讲", scene_text):
        return "talk"
    if re.search(r"公众号|小红书|群里|转发|给同事看|留存|发给", scene_text):
        return "read"
    return "talk-read"


def _validate_ledger(ledger: list[dict]) -> None:
    if not ledger:
        raise DeckError("论点台账为空")
    ids = set()
    for c in ledger:
        for k in ("id", "statement", "level", "priority"):
            if not c.get(k):
                raise DeckError(f"论点缺字段 {k}：{c}")
        if c["id"] in ids:
            raise DeckError(f"论点编号重复：{c['id']}")
        ids.add(c["id"])
        if c["level"] not in ("thesis", "pillar", "sub"):
            raise DeckError(f"level 只接受 thesis/pillar/sub：{c['id']}")
        if c["priority"] not in ("must", "should", "optional"):
            raise DeckError(f"priority 只接受 must/should/optional：{c['id']}")
    if sum(1 for c in ledger if c["level"] == "thesis") != 1:
        raise DeckError("台账必须恰好有 1 个总论点（thesis）")
    pillars = [c for c in ledger if c["level"] == "pillar"]
    if not 3 <= len(pillars) <= 5:
        raise DeckError(f"支柱必须 3–5 根，现在 {len(pillars)} 根")
    pids = {p["id"] for p in pillars}
    for c in ledger:
        if c["level"] == "sub" and c.get("pillar") not in pids:
            raise DeckError(f"分论点 {c['id']} 没有挂到存在的支柱")


def page_budget(ledger: list[dict], mode: str, chars: int, *, user_pages: int | None = None, user_minutes: float | None = None) -> dict:
    if mode not in MODES:
        raise DeckError(f"mode 只接受 {MODES}")
    if chars <= 0:
        raise DeckError("源文字数必须为正")
    _validate_ledger(ledger)
    keep = INCLUDE[mode]
    subs = [c for c in ledger if c["level"] == "sub"]
    pillars = [c for c in ledger if c["level"] == "pillar"]
    chosen = [c for c in subs if c["priority"] in keep]
    # 有独立论断却没有分论点的支柱，按 1 条处理
    have = {c["pillar"] for c in chosen}
    lone = [p for p in pillars if p["id"] not in have and p["priority"] in keep]
    core_units = chosen + lone
    appendix_items = [c for c in subs if c["priority"] == "optional" and mode == "read"]
    pages = sum(2 if c.get("split") else 1 for c in core_units)
    k = len(pillars)
    agenda = 1 if (k >= 4 or pages >= 10) else 0
    summary = 1 if (mode != "talk" and pages >= 8) else 0
    chapters = k if pages >= 18 else 0
    struct = 2 + agenda + summary + chapters
    total = pages + struct
    notes: list[str] = []
    if mode == "talk":
        notes.append("演讲式：结尾页兼作收束，不另加总结页")
    r = round(chars / max(1, pages))
    lo, hi = R_RANGE[mode]
    r_state = "ok" if lo <= r <= hi else ("high" if r > hi else "low")
    if r_state != "ok":
        notes.append(f"每个核心页承载 {r} 字，参考区间 {lo}–{hi}：只回头查原因，不为凑区间硬改页数")
    # 用户硬约束
    limit = user_pages
    if user_minutes and mode != "read":
        limit = min(limit or 10**9, int(user_minutes * 1.0))  # 演讲式约每页 1 分钟
    adjusted = None
    if limit is not None and total > limit:
        adjusted = _shrink(total, pages, agenda, summary, chapters, limit, notes)
    elif limit is not None and total < limit:
        notes.append(f"用户要 {limit} 页、公式给 {total} 页：先拆证据最重的分论点（split），不补装饰页，不引入原文没有的内容")
    volumes = None
    if total - struct > MAIN_CAP and limit is None:
        volumes = "超过单卷主线上限 28 页：先把「应该」论点降级进附录；仍超就先出 8–12 页总览卷，再每根支柱一卷"
    return {"calibrated": False, "mode": mode, "core_pages": pages, "structure_pages": struct, "total": total,
            "parts": {"agenda": agenda, "summary": summary, "chapters": chapters, "cover_and_closing": 2},
            "r": r, "r_range": [lo, hi], "r_state": r_state, "appendix": [c["id"] for c in appendix_items],
            "main_cap": MAIN_CAP, "volumes": volumes, "user_limit": limit, "after_user_limit": adjusted, "notes": notes}


def _shrink(total, core, agenda, summary, chapters, limit, notes) -> dict:
    """用户页数少于公式：依次删可有可无、合并相邻分论点、删议程与章节页、再删摘要页。返回各步后的页数。"""
    steps = []
    cur = total
    for name, saved in (("章节过渡页", chapters), ("议程页", agenda), ("摘要页", summary)):
        if cur <= limit:
            break
        if saved:
            cur -= saved
            steps.append(f"删{name}")
    if cur > limit:
        steps.append(f"仍多 {cur - limit} 页：把同一支柱下相邻的分论点合并成「并列要点页」，并把优先级低的移入附录")
    notes.append("用户页数更少：" + "；".join(steps) if steps else "已满足用户页数")
    return {"limit": limit, "after_removing_optional_structure": max(cur, 0), "steps": steps}


# ------------------------------ 页规格卡 ------------------------------
def check_cards(cards: list[dict], mode: str = "talk-read") -> list[str]:
    """检查整套页规格卡；返回问题列表，空表示通过。"""
    if mode not in MODES:
        raise DeckError(f"mode 只接受 {MODES}")
    if not cards:
        return ["没有页规格卡"]
    problems: list[str] = []
    for i, c in enumerate(cards, 1):
        tag = f"第 {c.get('n', i)} 页"
        if c.get("n") != i:
            problems.append(f"{tag}：页号 n 必须依次为 {i}")
        texts = c.get("rendered_text")
        if not isinstance(texts, list) or not texts or any(not isinstance(t, dict) or not str(t.get("text", "")).strip() for t in texts):
            problems.append(f"{tag}：rendered_text 必须是非空文字列表")
            continue
        joined = "\n".join(t["text"] for t in texts)
        for bad in c.get("forbid_render", []):
            if bad and bad in joined:
                problems.append(f"{tag}：禁止渲染的「{bad}」混进了可见文字")
        title = next((t["text"] for t in texts if t.get("role") == "title"), "")
        if len(CHAR.findall(title)) > TITLE_LIMIT:
            problems.append(f"{tag}：标题 {len(CHAR.findall(title))} 字，超过 {TITLE_LIMIT}")
        body = sum(len(CHAR.findall(t["text"])) for t in texts if t.get("role") not in ("title",))
        if c.get("type") not in STRUCT_TYPES and body > BODY_LIMIT[mode]:
            problems.append(f"{tag}：正文 {body} 字，超过 {mode} 档上限 {BODY_LIMIT[mode]}")
        for must in c.get("must_keep", []):
            if must not in joined:
                problems.append(f"{tag}：必须保留的「{must}」没有出现在 rendered_text")
        if c.get("text_mode") not in ("baked", "plate_overlay"):
            problems.append(f"{tag}：text_mode 必须在设计阶段声明为 baked 或 plate_overlay")
        if c.get("rhythm") not in ("anchor", "dense", "breathing"):
            problems.append(f"{tag}：rhythm 必须是 anchor/dense/breathing")
    types = [c.get("type") for c in cards]
    for i in range(1, len(types)):
        if types[i] and types[i] == types[i - 1] and types[i] not in STRUCT_TYPES:
            problems.append(f"第 {i} 与第 {i + 1} 页页型相同（{types[i]}）：相邻页型要不同")
    for i in range(len(types)):
        win = types[i:i + 8]
        if win and types[i] not in STRUCT_TYPES and win.count(types[i]) > 2:
            problems.append(f"从第 {i + 1} 页起 8 页内「{types[i]}」出现 {win.count(types[i])} 次，超过 2 次")
            break
    run = 0
    for i, c in enumerate(cards, 1):
        run = run + 1 if c.get("rhythm") == "dense" else 0
        if run > 3:
            problems.append(f"第 {i} 页前连续 {run} 页都是 dense：要放一页 breathing")
            break
    for i in range(1, len(types)):
        if {types[i], types[i - 1]} == {"bignumber"} or (types[i] == "quote" and types[i - 1] == "bignumber") or (types[i] == "bignumber" and types[i - 1] == "quote"):
            problems.append(f"第 {i} 与第 {i + 1} 页：大数字页与引言页不连续出现")
    return problems


def check_prompt(card: dict, prompt: str) -> list[str]:
    """出图提示词必须逐字包含每条 rendered_text，且不得夹带规格卡之外的「」引文。"""
    problems = []
    for t in card.get("rendered_text", []):
        if t["text"] not in prompt:
            problems.append(f"提示词缺少 rendered_text：{t['text']}")
    allowed = {t["text"] for t in card.get("rendered_text", [])}
    for quoted in re.findall(r"「([^」]+)」", prompt):
        if quoted not in allowed:
            problems.append(f"提示词里有规格卡之外的可见文字：「{quoted}」")
    return problems
