"""整册漫画分镜检查：合格文档通过，每类违规都要被拒绝。"""
import copy

import pytest

from scripts.stylebook import comic_book as CB


def panel(kind="action", **kw):
    base = {"shot": "中景", "scene": "教室", "light": "午后", "action": "举起天平", "kind": kind, "dialogue": ["这个够重吗"], "concept": "c1"}
    base.update(kw)
    return base


def doc(pages=6):
    return {"preset": "knowledge", "tier": "short",
            "characters": [{"id": "xue", "name": "小学", "desc": "a curious student",
                            "markers": ["round glasses with a square frame", "a crescent hair clip on the left", "a patched backpack"]}],
            "concepts": [{"id": "c1", "prop": "一架天平"}],
            "pages": [{"n": i, "title": "天平为什么会倾斜", "core": "同样重量放在不同位置结果不同",
                       "hook": "可门外传来奇怪的声音", "panels": [panel("action"), panel("talk"), panel("reveal")]} for i in range(1, pages + 1)],
            "closing": {"takeaway": "位置决定力矩", "action": "回家试一次", "callback": "回到那架天平", "open_question": "那月亮呢"}}


def test_good_doc_passes():
    assert CB.check(doc()) == []


@pytest.mark.parametrize("needle,mutate", [
    ("档要", lambda d: d.update(pages=d["pages"][:3])),
    ("景别", lambda d: d["pages"][0]["panels"][0].update(shot="很近")),
    ("对白超过", lambda d: d["pages"][0]["panels"][0].update(dialogue=["这是一句明显超过十二个字的很长很长的对白"])),
    ("缺页末钩子", lambda d: d["pages"][0].pop("hook")),
    ("叙事式", lambda d: d["pages"][1].update(title="第三章")),
    ("道具", lambda d: d["concepts"][0].pop("prop")),
    ("现成角色", lambda d: d["characters"][0].update(desc="looks like Doraemon")),
    ("连续", lambda d: d["pages"][0].update(panels=[panel("talk"), panel("talk"), panel("talk")])),
    ("结尾缺", lambda d: d["closing"].pop("callback")),
    ("不存在的概念", lambda d: d["pages"][0]["panels"][0].update(concept="zzz")),
    ("全页对白", lambda d: d["pages"][0]["panels"][0].update(dialogue=["一二三"] * 7)),
    ("页号", lambda d: d["pages"][2].update(n=9)),
])
def test_each_defect_is_caught(needle, mutate):
    d = copy.deepcopy(doc())
    mutate(d)
    assert any(needle in x for x in CB.check(d)), needle


def test_knowledge_talk_panel_needs_a_prop():
    d = doc()
    d["pages"][0]["panels"][1].pop("concept")
    assert any("对着黑板" in x for x in CB.check(d))


def test_unused_concept_is_flagged():
    d = doc()
    d["concepts"].append({"id": "c2", "prop": "一面镜子"})
    assert any("c2" in x for x in CB.check(d))


def test_fable4_needs_exactly_one_page_of_four_panels():
    d = {"preset": "fable4", "characters": doc()["characters"],
         "pages": [{"n": 1, "core": "寓意", "panels": [panel("action", concept=None) for _ in range(4)]}]}
    assert CB.check(d) == []
    d["pages"][0]["panels"].append(panel("action", concept=None))
    assert any("正好 4 格" in x for x in CB.check(d))


def test_bad_preset_and_empty_pages_rejected():
    assert CB.check({"preset": "x", "pages": [1]})
    assert CB.check({"preset": "knowledge", "pages": []})
