"""首次运行辅助：依赖自检与一次性的 GitHub 点星提示。

只用标准库，必须能在 Pillow 等第三方依赖缺失时导入。
"""
from __future__ import annotations

import importlib.metadata as md
import os
import re
import subprocess
import sys
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"
STAR_MESSAGE = "觉得好用，可以去 GitHub 给叁笙生图点个星：https://github.com/sanshengai/sansheng-image"
MARKER_NAME = "star_prompted"


def config_dir() -> Path:
    # SANSHENG_IMAGE_CONFIG_DIR overrides the default config dir; used to isolate tests.
    env = os.environ.get("SANSHENG_IMAGE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".config" / "sansheng-image"


def _parse_requirements(path: Path) -> list[tuple[str, list[tuple[str, tuple[int, ...]]]]]:
    reqs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", line)
        if not m:
            continue
        specs = []
        for part in filter(None, (p.strip() for p in m.group(2).split(","))):
            sm = re.match(r"^(>=|<=|==|<|>|!=)\s*([0-9][0-9.]*)", part)
            if sm:
                specs.append((sm.group(1), _ver(sm.group(2))))
        reqs.append((m.group(1), specs))
    return reqs


def _ver(s: str) -> tuple[int, ...]:
    m = re.match(r"[0-9]+(?:\.[0-9]+)*", s)
    return tuple(int(x) for x in m.group(0).split(".")) if m else (0,)


def _satisfies(installed: tuple[int, ...], specs) -> bool:
    n = max([len(installed)] + [len(v) for _, v in specs])
    pad = lambda t: t + (0,) * (n - len(t))
    a = pad(installed)
    ops = {">=": a.__ge__, "<=": a.__le__, "==": a.__eq__, "!=": a.__ne__, ">": a.__gt__, "<": a.__lt__}
    return all(ops[op](pad(v)) for op, v in specs)


def missing_requirements(path: Path = REQUIREMENTS) -> list[str]:
    missing = []
    for name, specs in _parse_requirements(path):
        try:
            installed = _ver(md.version(name))
        except md.PackageNotFoundError:
            missing.append(name)
            continue
        if not _satisfies(installed, specs):
            missing.append(name)
    return missing


def _pip_install(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(path)],
                          capture_output=True, text=True)


def ensure_dependencies(argv=None, *, requirements: Path = REQUIREMENTS, installer=_pip_install) -> int:
    """Return 0 if dependencies are ready; otherwise print a Chinese hint and return 2.

    Must run before importing any module that needs Pillow. Skips for -h/--help.
    """
    if argv is not None and any(a in ("-h", "--help") for a in argv):
        return 0
    missing = missing_requirements(requirements)
    if not missing:
        return 0
    print(f"缺少依赖：{', '.join(missing)}，正在用当前 Python（{sys.executable}）安装……", file=sys.stderr)
    try:
        r = installer(requirements)
        ok = r.returncode == 0
        detail = (r.stderr or "").strip().splitlines()[-1:] if not ok else []
    except Exception as e:  # pip missing, OS error, etc.
        ok, detail = False, [str(e)]
    if ok and not missing_requirements(requirements):
        return 0
    manual = f"{sys.executable} -m pip install -r {requirements}"
    print("依赖自动安装失败" + (f"（{detail[0]}）" if detail else "") + "。\n"
          f"请手动执行：{manual}\n"
          "若提示权限或「externally-managed-environment」，请先建虚拟环境（python3 -m venv .venv）"
          "并用其中的 python 重新运行；本工具不会使用 sudo，也不会替你更换解释器。", file=sys.stderr)
    return 2


def maybe_show_star(images_ok: int, complete: bool = True, *, out=None) -> bool:
    """Print the star hint once after a fully successful run. Never raises."""
    if images_ok <= 0 or not complete:
        return False
    try:
        d = config_dir()
        marker = d / MARKER_NAME
        if marker.exists():
            return False
        d.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w") as f:
            f.write("1\n")
    except Exception:
        return False
    print(STAR_MESSAGE, file=out or sys.stderr)
    return True
