"""Organize accepted claims; never render unverified model section prose."""
from services.deep_research.synthesis import OUTPUT_KIND_SECTIONS, resolve_output_kind


def build_sections(claims, output_kind, proposed_sections=None):
    templates = OUTPUT_KIND_SECTIONS.get(resolve_output_kind(output_kind), OUTPUT_KIND_SECTIONS["direction_survey"])
    indexed = {claim["claimId"]: claim for claim in claims if claim.get("claimId")}
    used, sections = set(), []
    if output_kind == 'experiment_design':
        from services.deep_research.experimental_reasoning import DESIGN_ROLES
        for title in templates:
            ids = [key for key, claim in indexed.items()
                   if isinstance(claim.get('designRole'), str)
                   and DESIGN_ROLES.get(claim['designRole'], (None,))[0] == title]
            if ids:
                used.update(ids)
                sections.append({'title': title, 'claimIds': ids})
    for section in proposed_sections or []:
        if not isinstance(section, dict) or section.get("title") not in templates:
            continue
        refs = section.get("claimIds", [])
        if not isinstance(refs, list):
            continue
        ids = [key for key in refs if isinstance(key, str) and key in indexed and key not in used]
        if ids:
            used.update(ids)
            sections.append({"title": section["title"], "claimIds": ids})
    # Keep every accepted claim even if the model supplied a malformed section map.
    remaining = [key for key in indexed if key not in used]
    if remaining:
        sections.append({"title": templates[0], "claimIds": remaining})
    sections.sort(key=lambda section: templates.index(section["title"]))
    return sections


def _display_gaps(gaps):
    """Keep the full audit in storage, show each unfinished obligation once."""
    specific = [g for g in gaps if not isinstance(g, dict) or not g.get('wholeQuestion')]
    selected = {}
    for gap in specific or gaps:
        key = (gap.get('obligationId') or gap.get('question')) if isinstance(gap, dict) else gap
        if key and (key not in selected or isinstance(gap, dict) and gap.get('stage') == 'answer'):
            selected[key] = gap
    return list(selected.values())


def source_access_summary(claims, evidence):
    """Describe cited external evidence, never imply the entire paper was read."""
    refs = {ref for claim in claims for ref in claim.get('evidenceRefs', [])}
    cited = [item for item in evidence if item.get('evidenceId') in refs]
    if not any(item.get('sourceKind') == 'arxiv' for item in cited):
        return ''
    levels = {item.get('accessLevel') for item in cited}
    labels = [label for level, label in [('fulltext', '全文片段'), ('abstract', '摘要'),
                                         ('user_note', '笔记')] if level in levels]
    if levels - {'fulltext', 'abstract', 'user_note'} or refs - {item.get('evidenceId') for item in cited}:
        labels.append('访问范围未标明的材料')
    return '本回答引用：' + '、'.join(labels) + '。'


def render_report(payload):
    claims = {claim["claimId"]: claim for claim in payload.get("claims", []) if claim.get("claimId")}
    refs = list(dict.fromkeys(ref for claim in claims.values() for ref in claim.get("evidenceRefs", [])))
    ref_numbers = {ref: index + 1 for index, ref in enumerate(refs)}
    sources = {e["evidenceId"]: e for e in payload.get("evidence", []) if e.get("evidenceId")}
    access_summary = source_access_summary(list(claims.values()), list(sources.values()))
    lines, rendered = ([access_summary, ''] if access_summary else []), set()
    sections = payload.get("sections") or build_sections(list(claims.values()), payload.get("outputKind", "direction_survey"))
    labels = {"inference": "有依据的推断：", "hypothesis": "待验证假设：", "suggestion": "实验建议：", "proposal": "实验建议："}
    for section in sections:
        content = []
        for key in section.get("claimIds", []):
            claim = claims.get(key)
            if not claim or key in rendered:
                continue
            rendered.add(key)
            citations = " ".join(f"[{ref_numbers[ref]}](#research-evidence-{ref})" for ref in claim.get("evidenceRefs", []) if ref in ref_numbers)
            content.append(f"- {labels.get(claim.get('kind'), '')}{claim['text']} {citations}".rstrip())
            conditions = claim.get("conditions")
            if isinstance(conditions, dict) and conditions:
                content.append("  适用条件：" + "；".join(f"{name}：{value}" for name, value in conditions.items()))
        if content:
            lines.extend([f"## {section['title']}", "", *content, ""])
    if not claims:
        lines.extend(["当前取得的证据不足以回答这个问题。", ""])
    gaps = _display_gaps(payload.get("gaps", []))
    if gaps:
        lines.extend(["<details>", f"<summary>还有 {len(gaps)} 项未完成</summary>", ""])
        for gap in gaps[:8]:
            question = gap if isinstance(gap, str) else gap.get("question", "")
            if question:
                reason = gap.get("missingEvidence", "") if isinstance(gap, dict) else ""
                lines.append(f"- {question}" + (f"：{reason}" if reason else ""))
        lines.extend(["", "</details>", ""])
    notes = payload.get('researchNotes')
    if isinstance(notes, list) and notes:
        lines.extend(['<details>', '<summary>查证范围说明</summary>', ''])
        for note in notes:
            if isinstance(note, dict) and isinstance(note.get('question'), str) and note['question']:
                lines.append('- 辅助问题「' + note['question'] + '」未纳入本次回答范围。')
        lines.extend(['', '</details>', ''])
    if payload.get("limitations"):
        lines.extend([payload["limitations"], ""])
    if refs:
        lines.extend(["<details>", "<summary>原文依据</summary>", ""])
        for ref in refs:
            evidence = sources.get(ref, {})
            title = evidence.get("sourceTitle") or evidence.get("sourceWorkId") or "论文来源"
            page = evidence.get("location", {}).get("page")
            access = {'abstract': ' · 仅摘要', 'fulltext': ' · 全文片段',
                      'user_note': ' · 笔记'}.get(evidence.get('accessLevel'), '')
            lines.append(f"**[{ref_numbers[ref]}] {title}**" + (f" · 第 {page} 页" if page else "") + access)
            if evidence.get("quote"):
                lines.extend(["", "> " + evidence["quote"].replace("\n", "\n> "), ""])
        lines.extend(["</details>", ""])
    return "\n".join(lines).strip()


def verification_notice(claims):
    """Describe only the kinds actually retained in the published answer."""
    kinds = {claim.get('kind') for claim in claims}
    parts = []
    if 'reported' in kinds:
        parts.append('论文事实已按所列原文核对。')
    if 'inference' in kinds:
        parts.append('推断限于所列证据和适用条件。')
    if kinds & {'hypothesis', 'proposal', 'suggestion'}:
        parts.append('假设与实验建议尚未经过实验验证。')
    return ''.join(parts)


def conversation_summary(claims, outcome, *, max_chars=500, evidence=None):
    """Keep whole claims and their epistemic labels; never cut a number or condition."""
    labels = {"inference": "有依据的推断：", "hypothesis": "待验证假设：",
              "suggestion": "实验建议：", "proposal": "实验建议："}
    boundary = {"partial": "当前结果尚不完整，已核实的内容已保存。",
                "inconclusive": "当前取得的证据不足以形成可靠结论。"}.get(outcome, "")
    access = source_access_summary(claims, evidence or [])
    parts = [access] if access else []
    length = len(boundary) + len(access) + (2 if access else 0)
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        if not text:
            continue
        item = labels.get(claim.get("kind"), "") + text
        conditions = claim.get("conditions")
        if isinstance(conditions, dict) and conditions:
            item += "（" + "；".join(f"{key}：{value}" for key, value in conditions.items()) + "）"
        if length + len(item) + 2 > max_chars:
            continue
        parts.append(item)
        length += len(item) + 2
    if boundary:
        parts.append(boundary)
    return "\n\n".join(parts) or "研究结果已保存，可打开报告查看。"
