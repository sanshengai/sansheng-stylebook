"""风格码：网站选择器与 Skill 之间传递选择的一行文字。

语法（sb1）：
    sb1:<样式>[-<结构>-<密度>]-<色彩>
    样式  C31 或 C31@r2（锁定修订）
    结构  auto 或表达结构 id（flow、compare…），只在讲道理的场景出现
    密度  auto / sparse / balanced / dense，与结构成对出现
    色彩  orig，或 <色系 id>.L<深浅>S<鲜灰>，深浅与鲜灰取 -1 / 0 / 1
例：sb1:C01-orig　sb1:C31-flow-balanced-macaron.L1S0　sb1:C31@r2-auto-auto-orig
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PREFIX = "sb1:"
_STYLE = re.compile(r"^(?:C|S)\d{2,3}(?:@r\d+)?$")
_PAL = re.compile(r"^(?P<fam>[a-z]+)(?:\.L(?P<l>-?1|0)S(?P<s>-?1|0))?$")
DENSITIES = ("auto", "sparse", "balanced", "dense")


class StyleCodeError(ValueError):
    pass


@dataclass(frozen=True)
class StyleCode:
    style: str
    structure: str | None = None
    density: str | None = None
    palette: str = "orig"
    light: int = 0
    sat: int = 0

    def format(self) -> str:
        parts = [self.style]
        if self.structure is not None:
            parts += [self.structure, self.density or "auto"]
        parts.append("orig" if self.palette == "orig" else f"{self.palette}.L{self.light}S{self.sat}")
        return PREFIX + "-".join(parts)

    def manifest_fields(self) -> dict:
        """转成编译清单的字段。结构 auto 原样传给编译器（写入「按内容选最清楚的结构」）；密度 auto 不写，按格式默认。"""
        out: dict = {"style": self.style, "palette": {"family": self.palette, "light": self.light, "sat": self.sat}}
        if self.structure:
            out["structure"] = self.structure
        if self.density and self.density != "auto":
            out["density"] = self.density
        return out


def find(text: str) -> list[str]:
    """从一段话里找出所有风格码（用户可能连同整句「用叁笙画风手册 sb1:… 做成…」一起贴过来）。"""
    return re.findall(r"sb1:[A-Za-z0-9@.\-]+", text or "")


def parse(code: str) -> StyleCode:
    raw = code.strip()
    if not raw.startswith(PREFIX):
        raise StyleCodeError(f"风格码要以 {PREFIX} 开头：{raw!r}")
    parts = raw[len(PREFIX):].split("-")
    # 色彩段里的负号（L-1、S-1）会被 split 拆开：把 "L" / "S" 结尾的碎片与下一段拼回去
    merged: list[str] = []
    for p in parts:
        if merged and re.search(r"\.L$|\.L-?[01]S$|\.L0S$", merged[-1]):
            merged[-1] += "-" + p
        else:
            merged.append(p)
    parts = merged
    if len(parts) not in (2, 4):
        raise StyleCodeError(f"风格码段数不对（应为 2 或 4 段）：{raw!r}")
    style, pal = parts[0], parts[-1]
    if not _STYLE.match(style):
        raise StyleCodeError(f"样式码不对：{style!r}")
    m = _PAL.match(pal)
    if not m:
        raise StyleCodeError(f"色彩段不对：{pal!r}")
    fam = m.group("fam")
    if fam == "orig" and m.group("l") is not None:
        raise StyleCodeError("原色不带深浅鲜灰")
    light, sat = int(m.group("l") or 0), int(m.group("s") or 0)
    structure = density = None
    if len(parts) == 4:
        structure, density = parts[1], parts[2]
        if not re.fullmatch(r"[a-z]+", structure):
            raise StyleCodeError(f"结构段不对：{structure!r}")
        if density not in DENSITIES:
            raise StyleCodeError(f"密度段不对：{density!r}")
    return StyleCode(style, structure, density, fam, light, sat)


def validate(sc: StyleCode) -> list[str]:
    """与数据对照：样式、结构、色系是否存在。"""
    from . import data as D
    problems = []
    if sc.style.split("@")[0] not in D.catalog():
        problems.append(f"没有这个样式：{sc.style}")
    if sc.structure and sc.structure != "auto" and sc.structure not in D.structures():
        problems.append(f"没有这个表达结构：{sc.structure}")
    if sc.palette not in {p["id"] for p in D.palettes()["palettes"]}:
        problems.append(f"没有这个色系：{sc.palette}")
    return problems
