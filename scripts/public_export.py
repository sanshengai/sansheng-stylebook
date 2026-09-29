"""Export the tracked public Skill files without private notes or Git history.

The source repository may contain maintainer-only files and commits. Always
publish a fresh repository made from this export, never push its source history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {
    ".claude-plugin/marketplace.json", ".claude-plugin/plugin.json",
    ".env.example", ".githooks/pre-commit", ".gitignore",
    "ASSET_PROVENANCE.md", "CHANGELOG.md", "LICENSE", "README.md",
    "README_EN.md", "SKILL.md", "THIRD_PARTY_NOTICES.md",
    "assets/C01-story-sample.png", "assets/C32-infographic-sample.png",
    "examples/book/plan.json", "examples/comic/plan.json",
    "examples/content-plan-v2/article.md", "examples/content-plan-v2/plan.json",
    "examples/quickstart/manifest.json", "gallery/template.html",
    "registry.json", "requirements-ppt.txt", "requirements.txt",
    "scripts/sb.py", "scripts/public_export.py",
}
PUBLIC_DIRS = ("formats/", "palettes/", "references/", "scenes/",
               "scripts/stylebook/", "structures/", "styles/", "tests/")
REQUIRED = {"SKILL.md", "README.md", "LICENSE", "requirements.txt",
            "styles/anchor-provenance.json", "registry.json"}
FORBIDDEN = re.compile(
    r"(?:AIza[0-9A-Za-z_-]{20,}|AQ\.[A-Za-z0-9_-]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|"
    r"fc-[0-9a-f]{32}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"[Cc]:\\Users\\|/Us" + r"ers/[^/\s]+/|/ho" + r"me/[^/\s]+/)", re.I)


class ExportError(ValueError):
    pass


def select(entries: list[tuple[str, str]]) -> list[str]:
    """Only regular files from the explicit public surface may leave the repo."""
    selected = []
    for mode, name in entries:
        if name in PUBLIC_FILES or name.startswith(PUBLIC_DIRS):
            if mode not in {"100644", "100755"}:
                raise ExportError(f"公开文件不是普通文件：{name}")
            selected.append(name)
    if not selected:
        raise ExportError("公开文件列表为空")
    missing = REQUIRED - set(selected)
    if missing:
        raise ExportError(f"公开包缺少必需文件：{sorted(missing)}")
    contracts = [p for p in selected if re.fullmatch(r"styles/C\d{2,3}/contract\.json", p)]
    if len(contracts) != 53:
        raise ExportError(f"公开画风合同数量应为 53，实际 {len(contracts)}")
    if any(re.search(r"(?:^|/)S0[12](?:/|$)", p) for p in selected):
        raise ExportError("私有画风进入公开文件列表")
    return selected


def scan_text(name: str, raw: bytes) -> None:
    if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExportError(f"公开文本不是 UTF-8：{name}") from exc
    if name == ".githooks/pre-commit":
        # The hook declares the same detection expressions as data. Keep all
        # other lines in the scan, including executable commands and comments.
        value = "\n".join(line for line in value.splitlines() if not line.startswith("patterns="))
    if FORBIDDEN.search(value) or ("_work" + "space") in value:
        raise ExportError(f"公开文本含密钥形态或个人路径：{name}")


def tracked_entries() -> list[tuple[str, str]]:
    raw = subprocess.check_output(["git", "ls-tree", "-rz", "HEAD"], cwd=ROOT)
    result = []
    for record in raw.split(b"\0"):
        if record:
            header, path = record.split(b"\t", 1)
            mode, kind, _sha = header.decode("ascii").split(" ")
            if kind != "blob":
                raise ExportError(f"Git 条目类型不可公开：{path!r}")
            result.append((mode, path.decode("utf-8")))
    return result


def export(destination: Path) -> dict:
    if destination.exists():
        raise ExportError(f"输出位置已存在，不覆盖：{destination}")
    files = select(tracked_entries())
    payload: dict[str, bytes] = {}
    for name in files:
        raw = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=ROOT)
        scan_text(name, raw)
        payload[name] = raw
    destination.mkdir(parents=True)
    for name, raw in payload.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        if name == ".githooks/pre-commit":
            target.chmod(0o755)
    receipt = {"schema_version": 1, "file_count": len(files),
               "files": {name: hashlib.sha256(payload[name]).hexdigest() for name in files}}
    (destination / "PUBLIC_EXPORT_MANIFEST.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = export(args.output.resolve())
    except (ExportError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"公开导出失败：{exc}\n")
    print(f"公开候选：{args.output.resolve()}（{receipt['file_count']} 个文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
