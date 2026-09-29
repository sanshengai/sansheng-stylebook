"""四格漫画清单的可检查结构要求。"""


def validate_content(format_id: str | None, content: dict) -> list[str]:
    if format_id != "comic-4panel":
        return []
    panels = content.get("panels")
    problems = []
    if not isinstance(panels, list) or len(panels) != 4 or any(
        not isinstance(panel, str) or not panel.strip() for panel in panels
    ):
        problems.append("comic-4panel 须写满 4 格非空 content.panels")
    if not isinstance(content.get("relations"), str) or not content["relations"].strip():
        problems.append("comic-4panel 须在 content.relations 明写跨格连续关系")
    return problems
