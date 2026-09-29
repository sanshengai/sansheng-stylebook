"""角色库与系列锁定（最小可用）。

- 角色圣经 character.json：辨识特征以形状与标志物为主（发型、眼镜、配饰、体型），不能只靠颜色区分——
  颜色会被样式的色板改掉，形状不会；
- 设定网格：一次生成正面、侧面、背面与三种表情，之后每张图都拿它当角色身份参考（role: identity）；
- 项目锁定 stylebook.project.json：风格码@修订号 + 色彩 + 角色清单，系列中途合同升级不自动跟进；
- 一致性验收：设定网格放第一格，其余图并排，交独立看图逐条核对辨识特征。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

COLOR_WORDS = re.compile(r"\b(red|orange|yellow|green|blue|purple|pink|white|black|grey|gray|brown|beige|cream|teal|navy|"
                         r"golden|silver|violet|mustard|coral|mint|lavender|peach|colou?red|pastel|dark|light)\b", re.I)
PROJECT_FILE = "stylebook.project.json"


def validate(ch: dict) -> list[str]:
    p: list[str] = []
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", str(ch.get("id", ""))):
        p.append("id 用小写英文、数字与连字符（2–32 位）")
    for k in ("name", "desc"):
        if not str(ch.get(k, "")).strip():
            p.append(f"缺 {k}")
    markers = ch.get("markers") or []
    if len(markers) < 3:
        p.append("辨识特征 markers 至少 3 条（发型、眼镜、配饰、体型等）")
    minor = re.search(r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen)"
                      r"[- ]years?[- ]old\b", str(ch.get("desc", "")) + " " + " ".join(markers), re.I)
    if minor and (not minor.group(1).isdigit() or int(minor.group(1)) < 18):
        p.append("不写具体的未成年年龄（如 twelve-year-old）：带参考图改图时容易被审核拦截，写 young student、child 这类说法即可")
    shape_markers = [m for m in markers if COLOR_WORDS.sub("", m).strip(" ,;-") and len(COLOR_WORDS.sub("", m).split()) >= 2]
    if len(shape_markers) < 2:
        p.append("至少 2 条辨识特征要靠形状或标志物，不能只靠颜色（颜色会被样式色板改掉）")
    return p


def load(path: Path) -> dict:
    ch = json.loads(Path(path).read_text(encoding="utf-8"))
    probs = validate(ch)
    if probs:
        raise ValueError(f"角色 {ch.get('id', path)} 不合格：" + "；".join(probs))
    ch["_dir"] = str(Path(path).resolve().parent)
    return ch


def identity_text(ch: dict) -> str:
    return f"{ch['desc'].strip()} Always recognisable by: " + "; ".join(ch["markers"]) + "."


def sheet_manifest(ch: dict, style: str, model: str = "gpt-image-2") -> dict:
    """设定网格：一张图里画正面、侧面、背面全身，外加三种表情特写。"""
    return {"style": style, "model": model, "aspect": "16:9",
            "content": {"subject": ("A clean character reference sheet of one single character on a plain light background: "
                                    "full body front view, side view and back view standing in a row, plus three head close-ups "
                                    "showing happy, surprised and thoughtful expressions. Every view shows the same character."),
                        "characters": [{"id": ch["id"], "desc": identity_text(ch)}]},
            "text": {"mode": "none"}}


def scene_manifest(ch: dict, style: str, subject: str, sheet: Path | None, model: str = "gpt-image-2", **extra) -> dict:
    m = {"style": style, "model": model, "content": {"subject": subject, "characters": [{"id": ch["id"], "desc": identity_text(ch)}]}}
    if sheet:
        m["references"] = [{"path": str(sheet), "role": "identity"}]
    m.update(extra)
    return m


def consistency_items(ch: dict) -> list[str]:
    """对照网格的验收条目：第一格是设定网格，其余每一格里的角色都要保住这些特征。"""
    items = [f"wherever the camera angle lets it be seen, every panel after the first keeps this trait from the reference sheet: {m} "
             f"(a trait hidden by the angle, e.g. a face detail in a back view, does not count as missing)" for m in ch["markers"]]
    items.append("the main character's face shape, head-to-body proportions and overall silhouette match the reference sheet in every panel")
    return items


def consistency_contract(ch: dict, style_contract: dict) -> dict:
    """借用样式合同的结构，换成一致性条目，交给同一个看图验收员。"""
    return {"code": style_contract["code"], "qa": {
        "must_see": consistency_items(ch),
        "must_not_see": ["a panel where the main character is clearly a different person (different face, hairstyle or signature item)",
                         "the main character's signature item missing or changed into a different object in any panel"]}}


# ---------------- 项目锁定 ----------------

def project_lock(project_dir: Path, style: str, palette: dict | None = None, characters: list[str] | None = None) -> Path:
    if "@r" not in style:
        raise ValueError("项目锁定要写修订号，例如 C58@r1；合同升级时编译会拦下来先问")
    p = Path(project_dir) / PROJECT_FILE
    data = {"style": style, "palette": palette or {"family": "orig"}, "characters": characters or []}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def project_load(project_dir: Path) -> dict | None:
    p = Path(project_dir) / PROJECT_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
