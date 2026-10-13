"""Current persistent retrieval and bounded prompts, synthetic responses only."""
import json
import re
from copy import deepcopy
from unittest.mock import patch

from llm.client import DeepSeekLLM
from rag.store import get_rag
from schemas.conversation import ConversationCapabilityRequest
from services.conversation_capability_service import execute_conversation
from services.evidence_quotes import prepare_quote_sources
from services.grounded_critique import check_critique_payload

A = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
FOCUS = '重点批判LightGaussian的压缩与速度主张：比较条件和质量代价？剪枝、球谐降阶和向量量化分别有什么局限？'
rag = get_rag()
before = rag.collection.count()
captured = {}


def excerpts(source):
    return dict(re.findall(r'^\[([0-9a-f]{16})\] (.+)$', source['text'], re.M))


def numeric_claim(packet):
    evidence = packet['evidence']
    table = next(source for source in evidence if source['pdfId'] == B and source.get('verifiedTable')
                 and {9,10} <= {row[0] for row in source['verifiedTable']['rows']})
    refs = []
    for row in table['verifiedTable']['rows']:
        if row[0] in (9,10):
            literal = f'Table row {row[0]}: ' + ' | '.join([row[1],*row[2]])
            qid = next(qid for qid, quote in excerpts(table).items() if literal == quote)
            refs.append({'sourceId':table['sourceId'],'quoteId':qid})
    hardware = next(source for source in evidence if source['pdfId'] == B and any('A6000' in quote for quote in excerpts(source).values()))
    hqid = next(qid for qid, quote in excerpts(hardware).items() if 'A6000' in quote)
    condition = [{'sourceId':hardware['sourceId'],'quoteId':hqid}]
    return {'summary':'Mip-NeRF 360（A6000，3D-GS *基线）：Ours为237 FPS、45MB。',
            'kind':'reported','references':refs,'paperIds':[B],
            'measurements':[{'sourceId':table['sourceId'],'row':10,'group':0,'metric':metric,'value':value,
                             'baselineRow':9,'dataset':table['verifiedTable']['groups'][0][0],
                             'hardware':'A6000','baseline':'3D-GS *','conditionReferences':condition}
                            for metric,value in (('FPS','237'),('Size','45MB'))]}


def controlled_provider(prompt, system):
    packet = json.loads(prompt.split('资料JSON：\n',1)[1])
    try:
        claim = numeric_claim(packet)
    except (StopIteration, KeyError):
        print('GROUNDED_READING_V6_FAILED_INPUT_JSON=' + json.dumps(packet,ensure_ascii=False))
        raise
    if 'pendingQuestions' in prompt:
        key = 'critique'
        claim.pop('paperIds')
        response = {'findings':[{**claim,'section':'contribution'}],
                    'pendingQuestions':[{'topic':'完整SH消融步骤的比较条件'}]}
    else:
        key = 'compare'
        cells = []
        for paper in packet['paperIds']:
            source = next(source for source in packet['evidence'] if source['pdfId'] == paper and excerpts(source))
            cells.append({'paperId':paper,'summary':'受控引用选择夹具，不作语义验收。','kind':'reported',
                          'references':[{'sourceId':source['sourceId'],'quoteId':next(iter(excerpts(source)))}]})
        response = {'claims':[claim], 'dimensions':[{'label':'受控引用链','cells':cells}], 'limitations':[]}
    captured[key] = {'input':packet,'response':response}
    return json.dumps(response, ensure_ascii=False)


with (patch.object(DeepSeekLLM,'_call',side_effect=AssertionError('Provider boundary blocked')),
      patch('services.socratic_service._call_guarded_llm',side_effect=controlled_provider)):
    critical = execute_conversation(ConversationCapabilityRequest(taskId='offline-only-v6',message=FOCUS,
        capability='critique',allowedPaperIds=[B],primaryPaperId=B,strictScope=True))
    comparison = execute_conversation(ConversationCapabilityRequest(taskId='offline-only-v6',
        message='比较原始3DGS和LightGaussian的压缩、质量与速度，并核对硬件和基线条件。',
        capability='compare',allowedPaperIds=[A,B]))

critical_input = captured['critique']['input']['evidence']
methods = '\n'.join(source['text'] for source in critical_input)
checks = {
    'critiqueSinglePaper': {source['pdfId'] for source in critical_input} == {B},
    'comparisonBothPapers': {source['pdfId'] for source in captured['compare']['input']['evidence']} == {A,B},
    'transmittanceDefinitionVisible': 'transmittance' in methods.lower(),
    'volumeAdjustmentVisible': 'normalized' in methods.lower() and '90' in methods and 'Equation: γ' in methods and 'Equation: V norm' in methods,
    'realMainTableAndHardwareValidated': '237 FPS' in critical['artifact']['text'] and 'A6000' in critical['message'],
    'shortSummary': len(critical['message']) <= 280,
    'noHeuristicClaimMap': all(row['method'] == 'literal_quote' for row in critical['artifact']['sentenceSourceMap']),
    'persistentIndexCountUnchanged': rag.collection.count() == before,
}
print('GROUNDED_READING_V6_JSON=' + json.dumps({'scope':'Current index, synthetic response fixtures; not model content acceptance',
    'providerCalls':0,'taskWrites':0,'persistentIndexWrites':0,'indexCount':before,'checks':checks,
    'captured':captured,'controlledResults':{'critique':critical,'compare':comparison}},ensure_ascii=False))
assert all(checks.values()), checks
