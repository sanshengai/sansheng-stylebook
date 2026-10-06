"""样图维护：样图只在本机，不进 Git；status 对比合同登记，backup 只增不删，restore 不误覆盖。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import samples_sync as S  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "styles/C01/samples").mkdir(parents=True)
    (r / "styles/C01/contract.json").write_text(json.dumps(
        {"samples": [{"file": "samples/cv.webp", "ratio": 1}, {"file": "samples/gone.webp", "ratio": 1}]}))
    (r / "styles/C01/samples/cv.webp").write_bytes(b"cv1")
    (r / "styles/C01/samples/extra.webp").write_bytes(b"x")
    return r


def test_status_reports_missing_and_unregistered(repo):
    st = S.status(repo)
    assert st["files"] == 2 and st["registered"] == 2
    assert st["missing"] == ["styles/C01/samples/gone.webp"]
    assert st["unregistered"] == ["styles/C01/samples/extra.webp"]


def test_backup_adds_only_and_never_deletes(repo, tmp_path):
    dest = tmp_path / "bak"
    assert S.backup(dest, repo)["added"] == 2
    again = S.backup(dest, repo)
    assert (again["added"], again["updated"], again["same"]) == (0, 0, 2)
    (repo / "styles/C01/samples/cv.webp").write_bytes(b"cv2")
    (repo / "styles/C01/samples/extra.webp").unlink()
    r = S.backup(dest, repo)
    assert r["updated"] == 1 and (dest / "styles/C01/samples/cv.webp").read_bytes() == b"cv2"
    assert (dest / "styles/C01/samples/extra.webp").is_file()  # 本地删了，备份保留


def test_backup_destination_must_be_outside_repo(repo):
    with pytest.raises(S.SyncError, match="仓库外"):
        S.backup(repo / "styles/bak", repo)


def test_backup_with_no_samples_is_rejected(repo, tmp_path):
    for p in (repo / "styles/C01/samples").iterdir():
        p.unlink()
    with pytest.raises(S.SyncError, match="没有样图"):
        S.backup(tmp_path / "bak", repo)


def test_restore_fills_missing_and_keeps_local_edits(repo, tmp_path):
    dest = tmp_path / "bak"
    S.backup(dest, repo)
    (repo / "styles/C01/samples/cv.webp").write_bytes(b"local edit")
    (repo / "styles/C01/samples/extra.webp").unlink()
    r = S.restore(dest, repo)
    assert (r["added"], r["skipped"]) == (1, 1)
    assert (repo / "styles/C01/samples/cv.webp").read_bytes() == b"local edit"
    S.restore(dest, repo, overwrite=True)
    assert (repo / "styles/C01/samples/cv.webp").read_bytes() == b"cv1"


def test_restore_from_missing_dir_reports_clearly(repo, tmp_path):
    with pytest.raises(S.SyncError, match="不存在"):
        S.restore(tmp_path / "nope", repo)


def test_cli_exit_codes(repo, tmp_path):
    assert S.main(["--repo", str(repo), "status"]) == 0
    assert S.main(["--repo", str(repo), "backup", "--dest", str(tmp_path / "b")]) == 0
    assert S.main(["--repo", str(repo), "restore", "--src", str(tmp_path / "none")]) == 1


def test_anchors_and_exemplars_never_live_under_samples():
    """锚点与范例图属于仓库（用户安装要用）；一旦指向 samples/，样图不进仓库就会让出图缺参考图。"""
    bad = []
    for cj in sorted((ROOT / "styles").glob("C*/contract.json")):
        c = json.loads(cj.read_text(encoding="utf-8"))
        files = [(c.get("anchor") or {}).get("file")] + [e.get("file") for e in c.get("exemplars", [])]
        bad += [(cj.parent.name, f) for f in files if f and f.startswith("samples/")]
    assert bad == [], bad
