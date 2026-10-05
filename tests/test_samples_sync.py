"""样图同步：样图在孤儿分支 samples，main 不跟踪；push 幂等、不动 main 索引，pull 能还原。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import samples_sync as S  # noqa: E402


def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}.items():
        monkeypatch.setenv(k, v)
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / ".gitignore").write_text("styles/*/samples/\n")
    (r / "styles/C01/samples").mkdir(parents=True)
    (r / "styles/C01/contract.json").write_text("{}")
    (r / "styles/C01/anchor.png").write_bytes(b"anchor")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    (r / "styles/C01/samples/cv.webp").write_bytes(b"cv1")
    (r / "styles/C01/samples/ppt-3.webp").write_bytes(b"ppt")
    return r


def test_push_creates_orphan_branch_without_touching_main(repo):
    main_head = git(repo, "rev-parse", "main")
    index_before = git(repo, "ls-files", "-s")
    sha = S.push(repo)
    assert git(repo, "rev-parse", "samples") == sha
    assert git(repo, "rev-parse", "main") == main_head and git(repo, "ls-files", "-s") == index_before
    assert git(repo, "branch", "--show-current") == "main"
    assert git(repo, "rev-list", "--parents", "-n1", sha).split() == [sha]  # 无父
    assert subprocess.run(["git", "merge-base", main_head, sha], cwd=repo, capture_output=True).returncode != 0  # 无共同历史
    assert sorted(S.tree_files(repo, "samples")) == ["styles/C01/samples/cv.webp", "styles/C01/samples/ppt-3.webp"]
    assert not git(repo, "status", "--porcelain")  # 样图仍被忽略，工作区干净


def test_push_twice_without_change_makes_no_commit_and_change_makes_one(repo):
    first = S.push(repo)
    assert S.push(repo) == first
    (repo / "styles/C01/samples/cv.webp").write_bytes(b"cv2")
    second = S.push(repo)
    assert second != first and git(repo, "rev-parse", f"{second}^") == first


def test_pull_restores_files_and_keep_flag(repo):
    S.push(repo)
    f = repo / "styles/C01/samples/cv.webp"
    f.unlink()
    f2 = repo / "styles/C01/samples/ppt-3.webp"
    f2.write_bytes(b"locally edited")
    assert S.pull(repo, overwrite=False) == 2
    assert f.read_bytes() == b"cv1" and f2.read_bytes() == b"locally edited"
    S.pull(repo)
    assert f2.read_bytes() == b"ppt"


def test_status_counts(repo):
    S.push(repo)
    (repo / "styles/C01/samples/new.webp").write_bytes(b"n")
    (repo / "styles/C01/samples/cv.webp").write_bytes(b"changed")
    (repo / "styles/C01/samples/ppt-3.webp").unlink()
    st = S.status(repo)
    assert (st["local"], st["branch"], st["only_local"], st["only_branch"], st["different"]) == (2, 2, 1, 1, 1)


def test_push_with_no_samples_is_rejected_not_an_empty_tree(repo):
    for p in (repo / "styles/C01/samples").iterdir():
        p.unlink()
    with pytest.raises(S.SyncError, match="没有样图"):
        S.push(repo)
    assert subprocess.run(["git", "rev-parse", "--verify", "samples"], cwd=repo, capture_output=True).returncode != 0


def test_pull_without_any_samples_branch_reports_clearly(repo):
    with pytest.raises(S.SyncError, match="找不到样图分支"):
        S.pull(repo)


def test_pull_refuses_branch_with_files_outside_samples(repo):
    (repo / "evil.txt").write_text("x")
    blob = git(repo, "hash-object", "-w", "evil.txt")
    tree = subprocess.run(["git", "mktree"], cwd=repo, input=f"100644 blob {blob}\tevil.txt\n", text=True, capture_output=True, check=True).stdout.strip()
    commit = git(repo, "commit-tree", tree, "-m", "bad")
    git(repo, "update-ref", "refs/heads/samples", commit)
    with pytest.raises(S.SyncError, match="拒绝解包"):
        S.pull(repo)


def test_cli_exit_codes(repo):
    assert S.main(["--repo", str(repo), "push"]) == 0
    assert S.main(["--repo", str(repo), "status"]) == 0
    for p in (repo / "styles/C01/samples").iterdir():
        p.unlink()
    assert S.main(["--repo", str(repo), "push"]) == 1


def test_anchors_and_exemplars_never_live_under_samples():
    """锚点与范例图属于 main（用户安装要用）；一旦指向 samples/，移走样图就会让出图缺参考图。"""
    bad = []
    for cj in sorted((ROOT / "styles").glob("C*/contract.json")):
        c = json.loads(cj.read_text(encoding="utf-8"))
        files = [(c.get("anchor") or {}).get("file")] + [e.get("file") for e in c.get("exemplars", [])]
        bad += [(cj.parent.name, f) for f in files if f and f.startswith("samples/")]
    assert bad == [], bad
