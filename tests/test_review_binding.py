import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stylebook.qa.binding import snapshot, verify


def test_binding_rejects_replaced_pixels_changed_parameters_and_old_report(tmp_path):
    image = tmp_path / "final.png"
    image.write_bytes(b"actual pixels v1")
    files = {"image": image}
    values = {"expected_text": ["原文"], "style": "C31@r4"}
    bound = snapshot("image", files=files, values=values)
    verify(bound, kind="image", files=files, values=values)
    image.write_bytes(b"replaced pixels v2")
    with pytest.raises(ValueError, match="输入已改变"):
        verify(bound, kind="image", files=files, values=values)
    image.write_bytes(b"actual pixels v1")
    with pytest.raises(ValueError, match="输入已改变"):
        verify(bound, kind="image", files=files, values={**values, "style": "C01@r1"})
    with pytest.raises(ValueError, match="未绑定"):
        verify(None, kind="image", files=files, values=values)


def test_binding_rejects_empty_input_and_changed_article_plan(tmp_path):
    article, plan = tmp_path / "article.md", tmp_path / "plan.json"
    article.write_text("完整文章")
    plan.write_text('{"items": []}')
    files = {"article": article, "plan": plan}
    bound = snapshot("article-plan", files=files, values={"items": []})
    article.write_text("换了一篇文章")
    with pytest.raises(ValueError):
        verify(bound, kind="article-plan", files=files, values={"items": []})
    article.write_bytes(b"")
    with pytest.raises(ValueError, match="为空"):
        snapshot("article-plan", files=files, values={"items": []})
    with pytest.raises(ValueError):
        snapshot("image", files={}, values={"items": []})


def test_actual_qa_entry_rejects_pixels_changed_during_review(tmp_path, monkeypatch):
    from argparse import Namespace
    from PIL import Image
    import sb
    from stylebook.qa import reviewer

    image, report = tmp_path / "image.png", tmp_path / "report.json"
    Image.new("RGB", (128, 128), "white").save(image)

    def replace_pixels(path, contract, expected, mode):
        Image.new("RGB", (128, 128), "black").save(path)
        return {"must_see": [], "must_not_see": [], "transcribed_text": []}

    monkeypatch.setattr(reviewer, "review", replace_pixels)
    args = Namespace(image=str(image), style="C31@r4", contract=None, manifest=None,
                     text=None, text_mode="none", format=None, review_json=None, report=str(report))
    with pytest.raises(ValueError, match="输入已改变"):
        sb.cmd_qa(args)
    assert not report.exists()
