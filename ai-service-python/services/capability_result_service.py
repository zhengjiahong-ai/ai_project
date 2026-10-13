"""Common result envelope while retaining native learning/research state."""
from services.evidence_service import build_sentence_source_map
from rag.store import normalize_id


def adapt_capability_result(kind, payload, native):
    if native.get('status') not in (None, 'success'):
        raise ValueError('能力未返回成功结果')
    upstream = payload.get('upstream') or {}
    selected = payload['paperIds'] if 'paperIds' in payload else upstream.get('allowedPaperIds',
                 [upstream['pdfId']] if upstream.get('pdfId') else [])
    scope = list(selected)
    allowed = {normalize_id(value): value for value in scope}
    if len(allowed) != len(scope):
        raise ValueError('材料索引标识冲突')
    result = dict(native)
    if kind == 'conversation.execute':
        capability = result['capability']
        material_scope = result['materialScope']
        message = result['message']
        raw_sources = result.get('sources') or []
    elif kind.startswith('learning.'):
        state = result.get('state') or {}
        capability = 'background' if upstream.get('action') == 'remediate' else state.get('mode', upstream.get('mode', 'read'))
        material_scope = {'taskId': upstream['taskId'], 'allowedPaperIds': scope,
                          'primaryPaperId': state.get('pdfId') or upstream.get('pdfId'), 'strictScope': True}
        message = str(result.get('message') or '').strip()
        if state.get('status') == 'active' and result.get('question'):
            message += '\n\n' + result['question']
        raw_sources = result.get('sources') or []
    elif kind == 'research.start':
        capability = 'research'
        material_scope = {'taskId': payload.get('workspaceTaskId'),
                          'allowedPaperIds': scope, 'primaryPaperId': upstream.get('pdfId'), 'strictScope': True}
        # The owning workspace ID is supplied by the operation request, not the
        # research job ID returned by the native service.
        message = '研究计划已生成，可调整后开始。'
        raw_sources = []
    else:
        raise ValueError('请求能力无效')
    if not message.strip() or capability not in {'chat', 'read', 'quiz', 'background', 'critique', 'compare', 'research', 'compose'}:
        raise ValueError('能力结果无效')
    if material_scope.get('allowedPaperIds') != scope or material_scope.get('primaryPaperId') not in [None, *scope]:
        raise ValueError('能力结果不符合材料快照')
    sources = []
    for source in raw_sources:
        identity = source.get('pdfId') or source.get('sourcePdfId') or (source.get('metadata') or {}).get('id')
        if not identity or normalize_id(identity) not in allowed:
            raise ValueError('能力来源不属于指定材料')
        sources.append({**source, 'pdfId': allowed[normalize_id(identity)]})
    artifact = result.get('artifact')
    if kind.startswith('learning.') and len(message) > 1600:
        artifact = {'text': message, 'paperIds': scope, 'sources': sources,
                    'sentenceSourceMap': build_sentence_source_map(message, sources, target='message')}
        message = message.split('\n\n')[0][:1000] + '\n\n完整解释已保存在成果中。'
    if artifact:
        if artifact.get('paperIds') != scope or artifact.get('sources') != sources:
            raise ValueError('成果不符合材料快照')
        artifact = {**artifact, 'paperIds': scope, 'sources': sources}
    result.update({'resultVersion': 1, 'status': 'success', 'capability': capability, 'message': message,
                   'sources': sources, 'sentenceSourceMap': result.get('sentenceSourceMap') or
                   build_sentence_source_map(message, sources, target='message'),
                   'materialScope': material_scope, 'steps': result.get('steps') or [], 'artifact': artifact})
    return result
