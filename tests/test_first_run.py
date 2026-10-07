import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import first_run as FR  # noqa: E402


@pytest.fixture
def req(tmp_path):
    p = tmp_path / "requirements.txt"
    p.write_text("fakepkg-a>=1,<2\n", encoding="utf-8")
    return p


def _inst(rc=0, calls=None, ver=None, monkeypatch=None):
    def run(path):
        if calls is not None:
            calls.append(path)
        return subprocess.CompletedProcess([], rc, "", "boom" if rc else "")
    return run


def test_deps_present_no_pip(monkeypatch, req):
    monkeypatch.setattr(FR.md, "version", lambda n: "1.5.0")
    calls = []
    assert FR.ensure_dependencies(["compile"], requirements=req, installer=_inst(calls=calls)) == 0
    assert calls == []


def test_missing_installs_then_ok(monkeypatch, req):
    state = {"ok": False}
    def version(n):
        if not state["ok"]:
            raise FR.md.PackageNotFoundError(n)
        return "1.2"
    monkeypatch.setattr(FR.md, "version", version)
    calls = []
    def inst(path):
        calls.append(path); state["ok"] = True
        return subprocess.CompletedProcess([], 0, "", "")
    assert FR.ensure_dependencies(["generate"], requirements=req, installer=inst) == 0
    assert calls == [req]


def test_install_failure_chinese_no_traceback(monkeypatch, req, capsys):
    monkeypatch.setattr(FR.md, "version", lambda n: (_ for _ in ()).throw(FR.md.PackageNotFoundError(n)))
    assert FR.ensure_dependencies(["generate"], requirements=req, installer=_inst(rc=1)) == 2
    err = capsys.readouterr().err
    assert "手动执行" in err and "Traceback" not in err and "sudo" in err and "--break-system-packages" not in err


def test_installer_exception_handled(monkeypatch, req, capsys):
    monkeypatch.setattr(FR.md, "version", lambda n: (_ for _ in ()).throw(FR.md.PackageNotFoundError(n)))
    def bad(path): raise OSError("no pip")
    assert FR.ensure_dependencies(["x"], requirements=req, installer=bad) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_version_out_of_range_is_missing(monkeypatch, req):
    monkeypatch.setattr(FR.md, "version", lambda n: "2.0.1")
    assert FR.missing_requirements(req) == ["fakepkg-a"]


def test_help_skips_install(monkeypatch, req):
    monkeypatch.setattr(FR.md, "version", lambda n: (_ for _ in ()).throw(FR.md.PackageNotFoundError(n)))
    calls = []
    assert FR.ensure_dependencies(["--help"], requirements=req, installer=_inst(calls=calls)) == 0
    assert calls == []


def test_pip_uses_current_interpreter(monkeypatch, req):
    seen = {}
    monkeypatch.setattr(FR.subprocess, "run", lambda cmd, **k: seen.setdefault("cmd", cmd) and subprocess.CompletedProcess(cmd, 0, "", ""))
    FR._pip_install(req)
    assert seen["cmd"][:4] == [sys.executable, "-m", "pip", "install"]
    assert "sudo" not in seen["cmd"] and "--break-system-packages" not in seen["cmd"]


def test_star_once_then_silent(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SANSHENG_IMAGE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert FR.maybe_show_star(3) is True
    assert "github.com/sanshengai/sansheng-image" in capsys.readouterr().err
    assert FR.maybe_show_star(3) is False
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("n,complete", [(0, True), (2, False)])
def test_no_star_on_failure_or_incomplete(monkeypatch, tmp_path, capsys, n, complete):
    monkeypatch.setenv("SANSHENG_IMAGE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert FR.maybe_show_star(n, complete) is False
    assert capsys.readouterr().err == ""
    assert not (tmp_path / "cfg" / FR.MARKER_NAME).exists()
    assert FR.maybe_show_star(1) is True  # failure did not burn the one-time hint


def test_unwritable_config_silent(monkeypatch, tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("SANSHENG_IMAGE_CONFIG_DIR", str(blocker / "sub"))
    assert FR.maybe_show_star(1) is False
    assert capsys.readouterr().err == ""
