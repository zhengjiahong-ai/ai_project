"""Replay the original v22 response, identifying the exact single prompt-line change."""
import hashlib
import json
import sys
from copy import deepcopy
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.grounded_critique import _atomic_findings, check_critique_payload
from services.safety_service import build_guarded_messages

archive = json.load(sys.stdin)
row = archive['cacheRows'][0]
original = deepcopy(row)
change = '归一化参考的统计含义必须保留：排序截点或分位参考、全局最大值和均值不可互换。省略具体百分数时仍需保留“排序参考”或“分位参考”的含义；没有完整参数绑定时可作这类定性说明，不能改称最大值。\n'
captured, diagnostics = {}, []


def model(prompt, extra_system_instruction=''):
    assert prompt.count(change) == 1
    old_prompt = prompt.replace(change, '')
    assert hashlib.sha256(old_prompt.encode()).hexdigest() == row['userPromptHash']
    system = build_guarded_messages(prompt, extra_system_instruction=extra_system_instruction)[0]['content']
    assert hashlib.sha256(system.encode()).hexdigest() == row['systemPromptHash']
    packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
    assert [source['sourceId'] for source in packet['evidence']] == row['inputVerification']['sourceIds']
    captured.update(originalPromptMatchesAfterRemovingSingleDocumentedLine=True,
                    originalSystemPromptMatches=True, sourceIdsUnchanged=True,
                    rawResponseSha256=hashlib.sha256(row['rawResponse'].encode()).hexdigest())
    return row['rawResponse']


def inspect(payload, sources, catalog, **kwargs):
    for finding in _atomic_findings(payload):
        try:
            checked, _ = check_critique_payload({'findings': [finding]}, sources, catalog)
            reason = None
        except ValueError as error:
            checked, reason = [], str(error)
        diagnostics.append({'kind': finding['kind'], 'summary': finding['summary'],
                            'rejection': reason, 'checked': checked})
    return check_critique_payload(payload, sources, catalog, **kwargs)


paper = row['inputVerification']['allowedPaperIds'][0]
request = ConversationCapabilityRequest(taskId=row['requestId'].removesuffix('-request'), capability='critique',
    message='重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？',
    allowedPaperIds=[paper], primaryPaperId=paper, strictScope=True)
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch('services.socratic_service._call_guarded_llm', side_effect=model) as stub,
      patch('services.grounded_critique.check_critique_payload', side_effect=inspect)):
    result = execute_conversation(request)
assert stub.call_count == 1 and row == original
assert len(result['message']) <= 600
for value in ('17.38', '17.32', '237', '357', 'PSNR下降0.27', 'PSNR下降0.22', 'LPIPS上升0.020', 'LPIPS上升0.024'):
    assert value in result['message'], (value, result['message'])
assert result['partial'] is True
rejected = [item for item in diagnostics if item['rejection']]
assert len(rejected) == 1 and '归一化参考' in rejected[0]['rejection']
assert all('数值正文包含未绑定数字' not in (item['rejection'] or '') for item in diagnostics)
print(json.dumps({'verification': captured, 'diagnostics': diagnostics, 'result': result,
                  'accepted': len(diagnostics) - len(rejected), 'rejected': len(rejected),
                  'modelSubmissions': 0, 'providerCalls': 0, 'taskWrites': 0,
                  'newModelQualityEvidence': False}, ensure_ascii=False))
