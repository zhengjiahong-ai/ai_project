"""Native retrieval with controlled fact selections, no Provider or publication."""
import hashlib
import json
import sys
from copy import deepcopy
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import _compare, _critique

data = json.load(sys.stdin)
original_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
papers = [item['pdfId'] for item in data['plan']['materials']]
checks = {}


def options(prompt):
    packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
    facts = [fact for source in packet['evidence'] for fact in source.get('experimentFacts', [])]
    assert len(facts) == 20, 'Expected exactly the two whitelisted rows, two groups, five metrics'
    assert {fact['model'] for fact in facts} == {'3D-GS  *  [16]', 'Ours'}
    assert {fact['hardware'] for fact in facts} == {'NVIDIA A6000 GPU'}
    assert {fact['dataset'] for fact in facts} == {'Mip-NeRF 360 Datasets', 'Tank and Temple Datasets'}
    return facts


def select(facts, dataset, metric, ours=True):
    return next(fact['factId'] for fact in facts if fact['dataset'] == dataset and fact['metric'] == metric
                and (fact['model'] == 'Ours') == ours)


def binding(facts, dataset, metric, identity, operation='value', ours=True):
    result = {'id': identity, 'kind': 'experiment', 'factId': select(facts, dataset, metric, ours),
              'operation': operation}
    if operation != 'value':
        result['baselineFactId'] = select(facts, dataset, metric, False)
    return result


def controlled_critique(prompt, *args):
    facts = options(prompt)
    findings = []
    for dataset in ['Mip-NeRF 360 Datasets', 'Tank and Temple Datasets']:
        findings.append({'section': 'contribution', 'kind': 'inference',
                         'summary': '已核对实验的压缩、帧率与质量代价：⟦数值1⟧；⟦数值2⟧；⟦数值3⟧。',
                         'references': [], 'numericBindings': [binding(facts, dataset, 'Size', 1, 'inverse_ratio'),
                         binding(facts, dataset, 'FPS', 2), binding(facts, dataset, 'PSNR', 3, 'difference')]})
    return json.dumps({'findings': findings, 'pendingQuestions': []})


def controlled_compare(prompt, *args):
    facts = options(prompt)
    raw = deepcopy(next(row['response'] for row in data['cache']['cacheRows'] if 'dimensions' in row['response']))
    raw['limitations'] = []
    raw['dimensions'] = raw['dimensions'][:3]
    for row, metric in zip(raw['dimensions'], ['Size', 'PSNR', 'FPS']):
        row['cells'][1] = {'paperId': papers[1], 'summary': '同条件结果：⟦数值1⟧；⟦数值2⟧；⟦数值3⟧；⟦数值4⟧。',
                          'kind': 'reported', 'references': [], 'numericBindings': [
                              binding(facts, dataset, metric, index + 1, ours=ours)
                              for index, (dataset, ours) in enumerate([
                                  ('Mip-NeRF 360 Datasets', False), ('Mip-NeRF 360 Datasets', True),
                                  ('Tank and Temple Datasets', False), ('Tank and Temple Datasets', True)])]}
    return json.dumps(raw)


for case in data['plan']['cases']:
    kind = case['capability']
    request = ConversationCapabilityRequest(taskId='offline-v14-no-publish', capability=kind,
        message=case['prompt'], allowedPaperIds=[papers[1]] if kind == 'critique' else papers,
        primaryPaperId=papers[1] if kind == 'critique' else papers[0], strictScope=kind == 'critique')
    handler = controlled_critique if kind == 'critique' else controlled_compare
    with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
          patch('services.socratic_service._call_guarded_llm', side_effect=handler) as stub):
        result = _critique(request, papers[1]) if kind == 'critique' else _compare(request, [])
    assert stub.call_count == 1 and result['partial'] is False
    text = result['message']
    assert 'factId' not in text and '⟦数值' not in text
    if kind == 'critique':
        assert all(value in text for value in ['17.38倍', '17.32倍', 'FPS 237', 'FPS 357',
                                               'PSNR下降0.27 dB', 'PSNR下降0.22 dB'])
    else:
        assert len(result['comparisonTable']) == 3
        assert all(cell['kind'] != 'not_covered' for row in result['comparisonTable'] for cell in row['cells'])
        assert '具体数字见比较表' not in text + result['summary']
        assert all(value in text for value in ['782 MB', '45 MB', '433 MB', '25 MB',
                                               'FPS 144', 'FPS 237', 'FPS 106', 'FPS 357'])
    checks[kind] = {'facts': 20, 'controlledResultPartial': False, 'message': text, 'summary': result.get('summary')}
assert original_hash == hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
print(json.dumps({'providerCalls': 0, 'taskWrites': 0, 'rawResponsesUnchanged': True,
                  'controlledSelectionsAreNotModelAcceptance': True, 'checks': checks}, ensure_ascii=False))
