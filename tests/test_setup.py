import importlib
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _fresh(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.endswith("_API_KEY") or k.endswith("_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STYLEBOOK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(tmp_path)
    import stylebook.backends.base as base
    importlib.reload(base)
    import stylebook.backends.providers as prov
    importlib.reload(prov)
    import stylebook.backends as b
    importlib.reload(b)
    import stylebook.setup as s
    importlib.reload(s)
    return s


def test_menu_lists_six_choices(monkeypatch, tmp_path):
    s = _fresh(monkeypatch, tmp_path)
    m = s.menu()
    for i in range(1, 7):
        assert f"{i}." in m
    assert "不要把密钥发到对话里" in m


def test_env_template_private_and_empty(monkeypatch, tmp_path):
    s = _fresh(monkeypatch, tmp_path)
    f = s.env_template()
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert [l for l in f.read_text().splitlines() if l and not l.startswith("#")] == []


def test_configure_without_key_does_not_save(monkeypatch, tmp_path):
    s = _fresh(monkeypatch, tmp_path)
    out = s.configure("seedream")
    assert "ARK_API_KEY" in out and not (tmp_path / "cfg" / "config.json").exists()


def test_doctor_unconfigured(monkeypatch, tmp_path):
    s = _fresh(monkeypatch, tmp_path)
    d = s.doctor()
    assert d.count("未配置") >= 5 and "--deep" in d
