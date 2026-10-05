"""PPT 规划层：页预算公式、用户硬约束、页规格卡的每类违规都要被拒绝。"""
import copy

import pytest

from scripts.stylebook import deck as DK


def ledger(subs=9, should_every=4):
    out = [{"id": "T", "statement": "总论点", "level": "thesis", "priority": "must"}]
    out += [{"id": f"P{i}", "statement": "支柱", "level": "pillar", "priority": "must"} for i in (1, 2, 3)]
    out += [{"id": f"S{i}", "statement": "分论点", "level": "sub", "pillar": f"P{i % 3 + 1}",
             "priority": "must" if i % should_every else "should"} for i in range(subs)]
    return out


def test_budget_follows_ledger_and_modes():
    L = ledger()
    talk = DK.page_budget(L, "talk", 5000)
    both = DK.page_budget(L, "talk-read", 5000)
    assert talk["core_pages"] == 6 and both["core_pages"] == 9           # 演讲式只留「必须」
    assert both["parts"]["summary"] == 1 and talk["parts"]["summary"] == 0
    assert both["total"] == both["core_pages"] + both["structure_pages"] and both["calibrated"] is False


def test_split_agenda_and_chapter_triggers():
    L = ledger(subs=12, should_every=99)
    for i in range(12):
        L[4 + i]["split"] = True
    b = DK.page_budget(L, "talk-read", 9000)
    assert b["core_pages"] == 24 and b["parts"]["chapters"] == 3 and b["parts"]["agenda"] == 1


def test_main_cap_flags_volumes():
    L = ledger(subs=30, should_every=99)
    assert DK.page_budget(L, "talk-read", 20000)["volumes"]


def test_user_page_limit_shrinks_structure_first_and_never_pads():
    L = ledger()
    b = DK.page_budget(L, "talk-read", 5000, user_pages=10)
    assert b["after_user_limit"]["steps"] and b["total"] > 10
    more = DK.page_budget(L, "talk-read", 5000, user_pages=20)
    assert any("不补装饰页" in n for n in more["notes"])


@pytest.mark.parametrize("mutate", [
    lambda L: L.pop(0),                                             # 没有总论点
    lambda L: L.__setitem__(1, dict(L[1], level="sub", pillar="X")),  # 支柱不足且悬空
    lambda L: L.append(dict(L[-1])),                                 # 编号重复
    lambda L: L[5].__setitem__("priority", "urgent"),
])
def test_bad_ledger_is_rejected(mutate):
    L = ledger()
    mutate(L)
    with pytest.raises(DK.DeckError):
        DK.page_budget(L, "talk-read", 5000)


def test_empty_inputs_are_rejected():
    with pytest.raises(DK.DeckError):
        DK.page_budget([], "talk-read", 5000)
    with pytest.raises(DK.DeckError):
        DK.page_budget(ledger(), "talk-read", 0)
    assert DK.check_cards([]) == ["没有页规格卡"]


def card(n, typ="compare", rhythm="breathing", **kw):
    base = {"n": n, "type": typ, "rhythm": rhythm, "text_mode": "baked",
            "rendered_text": [{"role": "title", "text": "午后是最大的增长机会"}, {"role": "label", "text": "增长 37%"}]}
    base.update(kw)
    return base


def good_deck():
    return [card(1, "cover", "anchor"), card(2, "compare"), card(3, "flow", "dense"), card(4, "bignumber"), card(5, "table")]


def test_good_deck_passes_and_each_defect_is_caught():
    assert DK.check_cards(good_deck()) == []
    cases = {
        "页号": lambda d: d[2].__setitem__("n", 9),
        "禁止渲染": lambda d: d[1].__setitem__("forbid_render", ["37%"]),
        "必须保留": lambda d: d[1].__setitem__("must_keep", ["2023 年"]),
        "text_mode": lambda d: d[1].__setitem__("text_mode", "later"),
        "rhythm": lambda d: d[1].__setitem__("rhythm", "fast"),
        "正文": lambda d: d[1]["rendered_text"].append({"role": "label", "text": "字" * 150}),
        "标题": lambda d: d[1]["rendered_text"].__setitem__(0, {"role": "title", "text": "字" * 30}),
        "相邻": lambda d: d[2].__setitem__("type", "compare"),
    }
    for needle, mutate in cases.items():
        d = copy.deepcopy(good_deck())
        mutate(d)
        assert any(needle in p for p in DK.check_cards(d)), needle


def test_rhythm_and_repetition_rules():
    d = [card(i, f"t{i}", "dense") for i in range(1, 6)]
    assert any("dense" in p for p in DK.check_cards(d))
    d = [card(1, "a"), card(2, "b"), card(3, "a"), card(4, "b"), card(5, "a")]
    assert any("8 页内" in p for p in DK.check_cards(d))


def test_prompt_must_contain_exact_text_and_nothing_extra():
    c = card(2)
    ok = "title 「午后是最大的增长机会」 and label 「增长 37%」"
    assert DK.check_prompt(c, ok) == []
    assert DK.check_prompt(c, "title 「午后是最大的增长机会」") != []
    assert any("规格卡之外" in p for p in DK.check_prompt(c, ok + " 另有 「谢谢观看」"))


def test_infer_mode():
    assert DK.infer_mode("明天上台汇报") == "talk" and DK.infer_mode("发公众号") == "read" and DK.infer_mode("讲个事") == "talk-read"
