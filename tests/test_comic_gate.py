"""四格关系必须在出图和验收前进入清单。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stylebook import plan as PL  # noqa: E402
from stylebook.comic import validate_content  # noqa: E402


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "sb.py"), *args],
                          cwd=ROOT, capture_output=True, text=True, check=False)


def test_empty_comic_content_is_rejected():
    problems = validate_content("comic-4panel", {})
    assert len(problems) == 2
    assert not validate_content("picturebook-page", {})


@pytest.mark.parametrize("mutation, expected", [
    ("missing_relations", "content.relations"),
    ("blank_relations", "content.relations"),
    ("three_panels", "content.panels"),
    ("blank_panel", "content.panels"),
])
def test_comic_mutation_fails_plan_compile_and_qa_before_review(tmp_path, mutation, expected):
    source = json.loads((ROOT / "examples" / "comic" / "plan.json").read_text(encoding="utf-8"))
    item = source["items"][0]
    if mutation == "missing_relations":
        item.pop("relations")
    elif mutation == "blank_relations":
        item["relations"] = "  "
    elif mutation == "three_panels":
        item["panels"].pop()
    else:
        item["panels"][2] = " "
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(source), encoding="utf-8")
    result = _run("plan", str(plan_file))
    assert result.returncode != 0 and expected in result.stdout + result.stderr

    manifest = PL.manifests(source)[0]
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    compiled = _run("compile", str(manifest_file))
    assert compiled.returncode != 0 and expected in compiled.stdout + compiled.stderr

    qa = _run("qa", str(tmp_path / "nonexistent.png"), "--style", "C58",
              "--manifest", str(manifest_file))
    assert qa.returncode == 2 and expected in qa.stderr
