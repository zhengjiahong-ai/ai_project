"""Real indexed input, original response and explicitly controlled split response.

No task writes or Provider calls. The controlled response is authored here and
cannot prove that a model follows the new protocol or produces good criticism.
"""
import hashlib
import json
import sys
from copy import deepcopy
from unittest.mock import patch

from llm.client import DeepSeekLLM
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation

archive = json.load(sys.stdin)
row = archive['cacheRows'][0]
paper = row['inputVerification']['allowedPaperIds'][0]
request = ConversationCapabilityRequest(taskId='stage4-3dgs-critique-20261010-v18', capability='critique',
    message='重点批判LightGaussian的15倍压缩与200+FPS主张：证据适用于哪些场景、比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？',
    allowedPaperIds=[paper], primaryPaperId=paper, strictScope=True)
findings = row['response']['findings']


def component(index, **changes):
    claim = deepcopy(findings[index])
    claim.pop('kind')
    claim.pop('section')
    return {**claim, **changes}


controlled = {'assessments': [
    {'section': 'weakness', 'inference': component(0)},
    {'section': 'weakness', 'observation': component(1)},
    {'section': 'weakness', 'inference': component(2)},
    {'section': 'risk', 'observation': component(6, summary=(
        '作者报告对高斯全部属性量化会造成精度损失；VQ用于球谐系数，并假设一组高斯外观相似。'
        '位置、形状、旋转、不透明度和高显著性球谐系数直接保存为float16。')),
     'inference': component(6, summary='直接保存的属性仍构成模型存储的一部分，应结合其占比评估整体压缩收益。')},
    {'section': 'risk', 'observation': component(4,
        summary='作者指出，仅用高斯体积会过度强调背景高斯，导致对精细几何高斯的过度剪枝。',
        references=[findings[4]['references'][1]])},
    {'section': 'risk', 'observation': component(5,
        summary='蒸馏以师生预测像素差异作为监督，并在每个训练视角周围按高斯分布采样相机位置。')},
], 'pendingQuestions': deepcopy(row['response']['pendingQuestions'])}
records = {}
for name, response in [('original_unchanged', row['rawResponse']),
                       ('controlled_split_not_model_output', json.dumps(controlled, ensure_ascii=False))]:
    captured = {}

    def reply(prompt, extra_system_instruction=''):
        packet = json.loads(prompt.split('资料JSON：\n', 1)[1])
        assert {source['pdfId'] for source in packet['evidence']} == {paper}
        captured.update(promptSha256=hashlib.sha256(prompt.encode()).hexdigest(),
                        allowedPaperIds=[paper],
                        transmittanceContext=[source['text'] for source in packet['evidence']
                                              if 'transmittance' in source['text'].lower()])
        return response

    with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
          patch('services.socratic_service._call_guarded_llm', side_effect=reply) as model):
        result = execute_conversation(request)
    assert model.call_count == 1 and captured['transmittanceContext']
    if name == 'original_unchanged':
        for field in ('message', 'partial', 'capability', 'materialScope'):
            assert result[field] == row['nativeReplay'][field], field
        assert result['artifact']['text'] == row['nativeReplay']['artifact']['text']
        assert result['partial']
    else:
        assert not result['partial']
        assert '17.378' in result['artifact']['text']
        assert '推断：直接保存的属性仍构成模型存储的一部分' in result['artifact']['text']
        assert '原文未提供目标域外验证' not in result['artifact']['text']
    records[name] = {'partial': result['partial'], 'message': result['message'],
                     'artifactText': result['artifact']['text'], 'input': captured}
print(json.dumps({'providerCalls': 0, 'taskWrites': 0, 'originalContentUnchanged': True,
                  'controlledResponseIsModelOutput': False, 'controlledResponse': controlled,
                  'records': records}, ensure_ascii=False))
