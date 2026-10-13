"""Assign displayed citations once across papers and composed capabilities."""
import re
from copy import deepcopy
from services.critique_presentation import stable_id


def bind_citations(result, sources):
    result = deepcopy(result)
    local_sources = result.get('rag_sources') or []
    local_ids = list(dict.fromkeys(ref['sourceId'] for claim in result.get('groundedClaims', [])
                                for ref in claim.get('references', [])))
    if not local_ids:
        local_ids = [source['sourceId'] for source in local_sources if source.get('sourceId')]
    aliases = {}
    for source in local_sources:
        sid = source.get('sourceId')
        if not sid:
            continue
        existing = next((value for value in sources if value.get('sourceId') == sid), None)
        if existing and existing.get('pdfId') != source.get('pdfId'):
            aliases[sid] = stable_id('source', source.get('pdfId'), sid)
            source['sourceId'] = aliases[sid]
        elif existing and existing.get('text') != source.get('text'):
            # Same identity with different excerpt text is also a distinct packet.
            aliases[sid] = stable_id('source', source.get('pdfId'), sid, source.get('text'))
            source['sourceId'] = aliases[sid]
        if not any(value.get('sourceId') == source['sourceId'] for value in sources):
            sources.append(source)
    numbers = {source['sourceId']: index + 1 for index, source in enumerate(sources)}
    remap = {index + 1: numbers[aliases.get(sid, sid)] for index, sid in enumerate(local_ids)
             if aliases.get(sid, sid) in numbers}
    def rewrite(text):
        return re.sub(r'\[(\d+)\]', lambda match: f'[{remap[int(match[1])]}]' if int(match[1]) in remap else match[0], text)
    for field in ('message', 'summary'):
        if isinstance(result.get(field), str):
            result[field] = rewrite(result[field])
    critique = result.get('critique')
    if critique:
        for field in ('lead', 'artifactLead', 'visiblePending', 'artifactPending'):
            if isinstance(critique.get(field), str):
                critique[field] = rewrite(critique[field])
        for field in ('chatBlocks', 'artifactBlocks'):
            for block in critique.get(field, []):
                block['text'] = rewrite(block['text'])
    for claim in [*result.get('groundedClaims', []), *(critique or {}).get('claims', [])]:
        for ref in claim.get('references', []):
            ref['sourceId'] = aliases.get(ref['sourceId'], ref['sourceId'])
    return result


def combine_critiques(results, request, sources):
    from services.critique_presentation import select_chat_blocks, requested_points, requested_sentences
    from services.conversation_capability_service import _requested_chat_limit
    items = [item for item in results if item.get('critique', {}).get('schemaVersion') == 2]
    if not items:
        return None
    critique = deepcopy(items[0]['critique'])
    if len(items) > 1:
        for field in ('claims', 'issues', 'pending', 'artifactBlocks'):
            critique[field] = []
        coverage = {'answeredQuestionPartIds': [], 'unresolvedQuestionPartIds': []}
        parts = []
        lead_ids = []
        for index, item in enumerate(items):
            value = deepcopy(item['critique'])
            paper = item['paperId']
            prefix = stable_id('paper', paper) + ':'
            for part in value['question']['parts']:
                parts.append({**part, 'id': prefix + part['id']})
            for field in coverage:
                coverage[field].extend(prefix + pid for pid in value['coverage'][field])
            for field in ('issues', 'pending'):
                for record in value[field]:
                    record['questionPartIds'] = [prefix + pid for pid in record.get('questionPartIds', [])]
            for issue in value['issues']:
                issue['title'] = f"论文{index + 1} · {issue['title']}"
            for field in ('claims', 'issues', 'pending', 'artifactBlocks'):
                critique[field].extend(value[field])
            lead_ids.extend(value['presentation']['leadClaimIds'])
        critique['question']['parts'] = parts
        critique['coverage'] = coverage
        # Explicit multi-paper requests give each paper a first turn before
        # secondary points consume the short answer's budget.
        buckets = [[issue for issue in critique['issues'] if paper in issue['paperIds']]
                   for paper in [item['paperId'] for item in items]]
        critique['issues'] = [bucket[index] for index in range(max(map(len, buckets), default=0))
                              for bucket in buckets if index < len(bucket)]
        critique['presentation']['artifactIssueIds'] = [issue['id'] for issue in critique['issues']]
        critique['presentation']['leadClaimIds'] = lead_ids
        critique['lead'] = '\n\n'.join(item['critique'].get('artifactLead', '') for item in items)
        critique['artifactLead'] = critique['lead']
        critique['visiblePending'] = '\n'.join(dict.fromkeys(item['critique'].get('artifactPending', '') for item in items)).strip()
        critique['artifactPending'] = critique['visiblePending']
    targets = list(dict.fromkeys(paper for item in items for paper in item['critique']['scope']['targetPaperIds']))
    critique['scope'] = {'allowedPaperIds': request.allowedPaperIds, 'targetPaperIds': targets,
                         'primaryPaperId': request.primaryPaperId if request.primaryPaperId in targets else targets[0]}
    critique['presentation']['standalone'] = request.capability == 'critique'
    numbers = {source['sourceId']: index + 1 for index, source in enumerate(sources) if source.get('sourceId')}
    # Re-render from checked groups with the shared citation map and total budget.
    summary = select_chat_blocks(critique, numbers, limit=_requested_chat_limit(request.message, 400),
                                 point_limit=requested_points(request.message) or max(3, len(items)), sentence_limit=requested_sentences(request.message))
    by_claim = {claim['id']: claim for claim in critique['claims']}
    from services.critique_presentation import render_claim
    critique['artifactBlocks'] = [{'issueId': issue['id'], 'text': f"**{index + 1}. {issue['title']}**\n\n" + '\n\n'.join(
        render_claim(by_claim[cid], numbers).strip() for cid in [issue['conclusionClaimId'], *issue['supportClaimIds']])}
        for index, issue in enumerate(critique['issues'])]
    return critique, summary
