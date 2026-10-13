"""Group independently checked claims into complete, addressable reading judgments.

No model calls or free rewrites occur here. Short forms reuse checked conclusions.
"""
import hashlib
import re


def stable_id(prefix, *values):
    return prefix + '-' + hashlib.sha256('\x1f'.join(map(str, values)).encode()).hexdigest()[:16]


def requested_points(question):
    match = re.search(r'(?:给|列出|总结|最关键的?|主要的?|重点|只(?:要|看|说|讲|检查|回答)?|最影响[^。！？：:]{0,30}的)\s*([1-8一二两三四五六七八])\s*(?:个)?(?:点|项|条|判断|观点)', question)
    if not match:
        return None
    value = match[1]
    return int(value) if value.isdigit() else {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8}[value]


def requested_sentences(question):
    match = re.search(r'(?:用|只(?:要|用|给)?|不超过|最多)?\s*([1-3一二两三])\s*句话', question)
    return (int(match[1]) if match[1].isdigit() else {'一': 1, '二': 2, '两': 2, '三': 3}[match[1]]) if match else None


def render_claim(claim, numbers):
    refs = list(dict.fromkeys(ref['sourceId'] for ref in claim['references']))
    return claim['text'] + ' ' + ' '.join(f'[{numbers[sid]}]' for sid in refs)


def select_chat_blocks(critique, numbers, *, limit=400, point_limit=None, sentence_limit=None):
    """Never slice a sentence, numeric condition, citation or observation/inference pair."""
    claims = {claim['id']: claim for claim in critique['claims']}
    issues = {issue['id']: issue for issue in critique['issues']}
    chosen = critique['presentation']['artifactIssueIds'][:point_limit or 3]
    coverage = critique.get('coverage', {})
    mandatory_pending = bool(coverage.get('unresolvedQuestionPartIds') or (
        coverage.get('requestedPoints') and coverage.get('availablePoints', len(issues)) < coverage['requestedPoints']))
    visible_pending = critique.get('artifactPending', critique.get('visiblePending', ''))
    if mandatory_pending and len(visible_pending) > limit:
        visible_pending = '部分判断仍待核查。' if limit >= 10 else ''
    reserve = len(visible_pending) + 2 if mandatory_pending and visible_pending else 0
    lead = critique.get('lead', '')
    if sentence_limit or len(lead) + reserve > limit:
        lead = ''
    blocks = []
    remaining = max(0, limit - len(lead) - (2 if lead else 0) - reserve)
    if sentence_limit and mandatory_pending and visible_pending:
        sentence_limit -= len(re.findall(r'[。！？]+', visible_pending)) or 1
    for index, issue_id in enumerate(chosen):
        if sentence_limit is not None and sentence_limit <= 0:
            break
        issue = issues[issue_id]
        conclusion = render_claim(claims[issue['conclusionClaimId']], numbers).strip()
        support = [render_claim(claims[cid], numbers).strip() for cid in issue['supportClaimIds']]
        full = f"**{index + 1}. {issue['title']}**\n\n" + '\n\n'.join([conclusion, *support])
        slots = len(chosen) - index
        budget = remaining // slots
        short = conclusion
        # With explicit sentence budgets, a checked claim may itself contain
        # multiple sentences. It is indivisible; omit rather than quietly cut it.
        sentence_count = len(re.findall(r'[。！？]+', short)) or 1
        if sentence_limit is not None and sentence_count > sentence_limit:
            continue
        text = full if sentence_limit is None and len(full) <= budget else short
        if len(text) > remaining:
            continue
        blocks.append({'issueId': issue_id, 'text': text})
        remaining -= len(text) + 2
        if sentence_limit is not None:
            sentence_limit -= sentence_count
            if sentence_limit <= 0:
                break
    # Critical coverage gaps stay in the short answer when they fit. The full
    # artifact retains all gaps; tiny budgets can use the epistemic fallback.
    if not blocks and not lead and not (mandatory_pending and visible_pending):
        fallback = '完整判断见成果。' if issues else '当前证据不足以判断，详见成果。'
        if len(fallback) > limit:
            fallback = '见成果' if limit >= 3 else '阅'[:limit]
        lead = fallback
        remaining = limit - len(lead)
    if not mandatory_pending and (sentence_limit == 0 or len(visible_pending) + 2 > remaining):
        visible_pending = ''
    if point_limit and len(blocks) < min(point_limit, len(issues)) and not mandatory_pending and sentence_limit is None:
        note = f'完整{min(point_limit, len(issues))}项判断见成果。'
        while blocks and len('\n\n'.join([lead, *(block['text'] for block in blocks), note]).strip()) > limit:
            blocks.pop()
        if len('\n\n'.join([lead, *(block['text'] for block in blocks), note]).strip()) <= limit:
            visible_pending = note
    critique['lead'] = lead
    critique['chatBlocks'] = blocks
    critique['visiblePending'] = visible_pending
    critique['presentation']['chatIssueIds'] = [block['issueId'] for block in blocks]
    return '\n\n'.join(part for part in [lead, *(block['text'] for block in blocks), visible_pending] if part)


def organize_critique(payload, findings, questions, paper_id, question):
    """Rebuild groups after validation; a rejected key conclusion drops its issue."""
    by_group = {}
    claims = []
    by_id = {}
    for finding in findings:
        cid = stable_id('claim', paper_id, finding['kind'], finding['summary'], finding['references'])
        claim = {'id': cid, 'paperIds': [paper_id], 'kind': finding['kind'],
                 'text': finding['summary'], 'references': finding['references']}
        for field in ('measurements', 'numericBindings'):
            if finding.get(field):
                claim[field] = finding[field]
        if cid not in by_id:
            claims.append(claim)
            by_id[cid] = claim
        by_group.setdefault(finding.get('_group', 0), {})[finding.get('_role', 'conclusion')] = cid
    parts = payload.get('questionParts') or [{'id': 'main', 'text': question}]
    if (not isinstance(parts, list) or not 1 <= len(parts) <= 8
            or any(not isinstance(part, dict) or not isinstance(part.get('id'), str)
                   or not isinstance(part.get('text'), str) or not part['id'] or len(part['text']) > 1000 for part in parts)
            or len({part['id'] for part in parts}) != len(parts)):
        raise ValueError('批判问题覆盖格式无效。')
    part_ids = {part['id'] for part in parts}
    groups = payload.get('assessments', payload.get('findings', []))
    issues, by_topic = [], {}
    for index, raw in enumerate(groups):
        available = by_group.get(index, {})
        role = (raw.get('conclusion') or ('inference' if 'inference' in raw else 'observation')) if 'assessments' in payload else 'conclusion'
        if role not in available:
            continue
        conclusion = available[role]
        topic = raw.get('topicKey') or by_id[conclusion]['text']
        title = raw.get('title') or {'contribution': '证据支持', 'weakness': '条件与代价', 'risk': '适用范围'}[raw['section']]
        linked = raw.get('questionPartIds', [parts[0]['id']])
        if (not isinstance(topic, str) or not topic.strip() or len(topic) > 320
                or not isinstance(title, str) or not title.strip() or len(title) > 48
                or not isinstance(linked, list) or not linked or any(value not in part_ids for value in linked)):
            raise ValueError('批判观点分组格式无效。')
        # Titles identify topics; assertions belong to independently checked claims.
        assertion = re.search(r'决定|导致|证明|必须|需要|需|会|能够|仅|只', title)
        if assertion:
            title = title[:assertion.start()].strip() or {'contribution': '证据支持', 'weakness': '条件与代价', 'risk': '适用范围'}[raw['section']]
        supporting = [cid for cid in available.values() if cid != conclusion]
        if topic in by_topic:
            issue = by_topic[topic]
            issue['supportClaimIds'] = list(dict.fromkeys([*issue['supportClaimIds'], conclusion, *supporting]))
            issue['questionPartIds'] = list(dict.fromkeys([*issue['questionPartIds'], *linked]))
            continue
        issue = {'id': stable_id('issue', paper_id, topic), 'topicKey': topic, 'title': title,
                 'questionPartIds': linked, 'paperIds': [paper_id], 'conclusionClaimId': conclusion,
                 'supportClaimIds': supporting, 'relatedPendingIds': [], 'priority': len(issues)}
        issues.append(issue)
        by_topic[topic] = issue
    used = {cid for issue in issues for cid in [issue['conclusionClaimId'], *issue['supportClaimIds']]}
    overall = by_group.get('overall', {}).get('overall')
    # An overview cannot keep evidence belonging only to a discarded group.
    supported_refs = {str(ref) for claim in claims if claim['id'] in used for ref in claim['references']}
    if overall and not all(str(ref) in supported_refs for ref in by_id[overall]['references']):
        overall = None
    if overall and issues:
        used.add(overall)
    claims = [claim for claim in claims if claim['id'] in used]
    pending = []
    for index, topic in enumerate(questions):
        raw = next(item for item in (payload.get('pendingQuestions') or [])
                   if item.get('topic', '').strip() == topic.removeprefix('待核查：'))
        linked = raw.get('questionPartIds', [parts[0]['id']])
        if not isinstance(linked, list) or any(value not in part_ids for value in linked):
            raise ValueError('待核查问题覆盖格式无效。')
        pending.append({'id': stable_id('pending', paper_id, topic), 'topic': topic.removeprefix('待核查：'),
                        'whatToCheck': topic.removeprefix('待核查：'), 'questionPartIds': linked})
    answered = set(value for issue in issues for value in issue['questionPartIds'])
    unresolved_raw = payload.get('unresolvedQuestionPartIds', [])
    if not isinstance(unresolved_raw, list) or any(value not in part_ids for value in unresolved_raw):
        raise ValueError('批判问题覆盖格式无效。')
    unresolved = (part_ids - answered) | set(unresolved_raw)
    answered -= unresolved
    count = requested_points(question)
    count_shortfall = bool(count and len(issues) < count)
    partial = bool(unresolved or count_shortfall)
    if unresolved:
        note = '本次尚不能判断：' + '；'.join(part['text'] for part in parts if part['id'] in unresolved) + '。'
    elif count_shortfall:
        note = f'当前仅形成{len(issues)}项有依据的判断，其余仍待核查。'
    else:
        note = ''
    used_sources = list(dict.fromkeys(ref['sourceId'] for claim in claims for ref in claim['references']))
    numbers = {sid: index + 1 for index, sid in enumerate(used_sources)}
    critique = {'schemaVersion': 2, 'scope': {'allowedPaperIds': [paper_id], 'targetPaperIds': [paper_id], 'primaryPaperId': paper_id},
                'question': {'original': question, 'parts': parts, 'requestedPoints': count},
                'claims': claims, 'issues': issues, 'pending': pending,
                'coverage': {'answeredQuestionPartIds': sorted(answered), 'unresolvedQuestionPartIds': sorted(unresolved),
                             'requestedPoints': count, 'availablePoints': len(issues)},
                'presentation': {'leadClaimIds': [overall] if overall and issues else [], 'chatIssueIds': [],
                                 'artifactIssueIds': [issue['id'] for issue in issues]},
                'lead': render_claim(by_id[overall], numbers).strip() if overall and issues else '',
                'visiblePending': note}
    critique['artifactBlocks'] = [{'issueId': issue['id'], 'text': f"**{index + 1}. {issue['title']}**\n\n" + '\n\n'.join(
        render_claim(by_id[cid], numbers).strip() for cid in [issue['conclusionClaimId'], *issue['supportClaimIds']])}
        for index, issue in enumerate(issues)]
    from services.conversation_capability_service import _requested_chat_limit
    full_lead = critique['lead']
    summary = select_chat_blocks(critique, numbers, limit=_requested_chat_limit(question, 400),
                                 point_limit=count, sentence_limit=requested_sentences(question))
    critique['artifactLead'] = full_lead
    critique['artifactPending'] = note
    body = '\n\n'.join(part for part in [full_lead, *(block['text'] for block in critique['artifactBlocks']), note] if part)
    if not body:
        body = '当前取得的正文不足以判断这个问题。'
    if pending:
        body += '\n\n<details>\n<summary>待核查</summary>\n\n' + '\n'.join('- 待核查：' + item['whatToCheck'] for item in pending) + '\n\n</details>'
    return critique, body, summary, partial, used_sources
