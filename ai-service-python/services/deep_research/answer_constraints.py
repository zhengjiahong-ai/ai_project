"""User-visible length constraints, separate from model token budgets."""
import json
import re


def resolve_evidence_aliases(report, aliases):
    """Resolve only exact IDs supplied in this prompt, never guessed hash prefixes."""
    for claim in report.get('claims', []):
        if isinstance(claim, dict) and isinstance(claim.get('evidenceRefs'), list):
            claim['evidenceRefs'] = [aliases.get(ref, ref) if isinstance(ref, str) else ref
                                     for ref in claim['evidenceRefs']]
            bindings = claim.get('tableBindings')
            for binding in bindings if isinstance(bindings, list) else []:
                if isinstance(binding, dict) and isinstance(binding.get('evidenceId'), str):
                    binding['evidenceId'] = aliases.get(binding['evidenceId'], binding['evidenceId'])
    return report


def normalize_conditions(report):
    for claim in report.get('claims', []):
        if not isinstance(claim, dict):
            continue
        conditions = claim.get('conditions')
        if isinstance(conditions, str):
            claim['conditions'] = {'context': conditions} if conditions.strip() else {}
        elif isinstance(conditions, list) and all(isinstance(value, str) for value in conditions):
            claim['conditions'] = {str(index + 1): value for index, value in enumerate(conditions)}
    return report


def requested_character_limit(question):
    match = re.search(r'(\d{2,5})\s*(?:字|个字符|characters)\s*(?:以内|以下|内|maximum|max)?', question, re.I)
    return min(int(match[1]), 10000) if match else None


def answer_character_count(report):
    count = 0
    for claim in report.get('claims', []):
        if not isinstance(claim, dict) or not isinstance(claim.get('text'), str):
            return float('inf')
        conditions = claim.get('conditions') or {}
        if not isinstance(conditions, dict):
            return float('inf')
        count += len(claim['text']) + sum(len(str(key)) + len(str(value)) + 2 for key, value in conditions.items())
    return count


def _core_claims(claims, limit, output_kind, evidence):
    if output_kind != 'paper_comparison':
        return claims[:2 if limit <= 300 else 4]
    works = {e['evidenceId']: e.get('sourceWorkId') for e in evidence}
    selected, covered, joint = [], set(), None
    for claim in claims:
        identities = {works[ref] for ref in claim.get('evidenceRefs', []) if works.get(ref)}
        if len(identities) == 1 and not identities <= covered:
            selected.append(claim)
            covered.update(identities)
        elif len(identities) > 1 and claim.get('kind') == 'inference' and joint is None:
            joint = claim
    if joint is not None:
        selected.append(joint)
    return selected or claims[:3]


def compact_answer(report, question, invoke, parse, *, output_kind='', evidence=()):
    report = normalize_conditions(report)
    limit = requested_character_limit(question)
    if not limit or answer_character_count(report) <= limit:
        return report
    # Reduce the rewrite's scope, not its evidence: original references and kinds
    # are restored by code and the rewritten claims are verified afterwards.
    core = _core_claims(report['claims'], limit, output_kind, evidence)
    target = max(15, int(limit * .7 / max(1, len(core))))
    prompt = f'''用中文压缩以下核心回答。用户问题：{question}
总共最多{limit}字，每条text与conditions合计尽量不超过{target}字。
只返回JSON：{{"claims":[{{"claimId":"原ID","text":"短结论","conditions":{{}}}}]}}。
不要返回引用、kind、章节或额外声明，系统保留原始身份并重新核验。
保留论断必需的实验条件、方法标签和限定词；删去旁支数字和背景。
把条件写入text即可，不要在conditions重复。不能新增事实。
{'必须保留每个输入ID：它们分别代表各论文结论和跨论文可比性。' if output_kind == 'paper_comparison' else 'You MAY DROP 次要声明，但保留直接回答问题的判断。'}
输入：{json.dumps([{key: c.get(key, {} if key == 'conditions' else '') for key in ('claimId', 'text', 'conditions')} for c in core], ensure_ascii=False)}'''
    result = invoke(prompt)
    finish = (result.get('finishReason', result.get('finish_reason')) if isinstance(result, dict)
              else getattr(result, 'finish_reason', None))
    if finish == 'length':
        return None
    compact = parse(result.get('content', '') if isinstance(result, dict) else result.content)
    if not isinstance(compact, dict) or not isinstance(compact.get('claims'), list) or not compact['claims']:
        return None
    compact = normalize_conditions(compact)
    original = {c.get('claimId'): c for c in core if isinstance(c, dict)}
    seen = set()
    for claim in compact['claims']:
        if not isinstance(claim, dict) or claim.get('claimId') not in original or claim.get('claimId') in seen:
            return None
        seen.add(claim['claimId'])
        before = original[claim['claimId']]
        if ('kind' in claim and claim['kind'] != before.get('kind')) or ('evidenceRefs' in claim and claim['evidenceRefs'] != before.get('evidenceRefs')):
            return None
        merged = {**before, **claim}
        claim.clear()
        claim.update(merged)
    if output_kind == 'paper_comparison' and seen != set(original):
        return None
    if 'sections' not in compact and 'sections' in report:
        compact['sections'] = report['sections']
    return compact if answer_character_count(compact) <= limit else None
