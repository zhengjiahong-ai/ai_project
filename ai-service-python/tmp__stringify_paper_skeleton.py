

def _stringify_paper_skeleton(paper_skeleton: Dict[str, Any] | None) -> str:
    if not paper_skeleton:
        return "暂无可用的论文结构摘要。"

    lines = []
    for section, summary in paper_skeleton.items():
        lines.append(f"- {section}: {summary}")
    return "\n".join(lines)


