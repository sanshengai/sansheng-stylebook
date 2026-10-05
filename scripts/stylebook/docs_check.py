"""文档卫生检查：入口与参考文件之间的链接、孤儿文件、画风码和场景 id 必须真实存在。

宝玉的仓库里出现过 23 处指向已删除风格的引用和多份孤儿文件，所以这里把「文档说的」和「数据里有的」机器比对，
而不是靠人记。只读，不改任何文件；返回问题列表，空列表表示通过。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
STYLE = re.compile(r"(?<![A-Za-z0-9])([CS]\d{2,3})(?![0-9A-Za-z])")
SCENE_ID = re.compile(r"场景 id `([a-z0-9-]+)`")


def _docs(root: Path) -> list[Path]:
    return [root / "SKILL.md", *sorted((root / "references").rglob("*.md"))]


def _known_styles(root: Path) -> set[str]:
    return {p.name for p in (root / "styles").glob("[CS][0-9]*") if p.is_dir()}


def check(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    docs = [d for d in _docs(root) if d.is_file()]
    if not docs or not (root / "SKILL.md").is_file():
        return ["缺 SKILL.md 或 references 目录"]
    graph: dict[Path, set[Path]] = {}
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        graph[doc.resolve()] = set()
        for target in LINK.findall(text):
            if re.match(r"[a-z]+://", target) or target.startswith("mailto:"):
                continue
            dest = (doc.parent / target).resolve()
            if not dest.exists():
                problems.append(f"{doc.relative_to(root)}: 链接指向不存在的文件 {target}")
            elif dest.suffix == ".md":
                graph[doc.resolve()].add(dest)
    # 孤儿：references 下每份 md 必须能从 SKILL.md 沿链接走到
    seen, stack = set(), [(root / "SKILL.md").resolve()]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, ()))
    for doc in docs:
        if doc.resolve() not in seen:
            problems.append(f"{doc.relative_to(root)}: 孤儿文件，从 SKILL.md 走不到")
    # 画风码
    styles = _known_styles(root)
    private_ok = {c for c in re.findall(r"S\d{2}", "") }  # 私有画风 S* 不在公开包里，不校验
    for doc in docs:
        for code in sorted(set(STYLE.findall(doc.read_text(encoding="utf-8")))):
            if code.startswith("S") or code in private_ok:
                continue
            if code not in styles:
                problems.append(f"{doc.relative_to(root)}: 提到画风 {code}，但 styles/ 里没有")
    # 场景 id
    scenes_file = root / "scenes" / "scenes.json"
    if scenes_file.is_file():
        data = json.loads(scenes_file.read_text(encoding="utf-8"))
        items = data.get("scenes", data) if isinstance(data, dict) else data
        ids = {s.get("id") for s in items if isinstance(s, dict)}
        for doc in docs:
            for sid in SCENE_ID.findall(doc.read_text(encoding="utf-8")):
                if sid not in ids:
                    problems.append(f"{doc.relative_to(root)}: 场景 id {sid} 不在 scenes.json")
    return problems


if __name__ == "__main__":
    found = check()
    for item in found:
        print(item)
    raise SystemExit(1 if found else 0)
