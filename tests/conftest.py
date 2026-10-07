"""测试默认与本机环境隔离：不使用真实的 Codex 登录，也不读本机私有档。个别测试需要时自行覆盖。"""
import pytest


@pytest.fixture(autouse=True)
def _no_real_codex(monkeypatch):
    monkeypatch.setenv("SANSHENG_IMAGE_CODEX", "/nonexistent/codex")
    try:
        from stylebook.backends import providers
        providers._CODEX_LOGIN.clear()
    except Exception:  # 导入路径尚未就绪的测试文件里忽略
        pass
