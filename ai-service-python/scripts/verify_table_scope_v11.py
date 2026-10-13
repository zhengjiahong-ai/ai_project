"""Current PDF, persistent retrieval and numeric whitelist checks; no Provider."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

from core.document_parser import parse_tei_xml
from llm.client import DeepSeekLLM
from rag.store import get_rag
from schemas.conversation import ConversationCapabilityRequest
from services import grounded_comparison
from services.conversation_capability_service import _compare
from services.evidence_quotes import prepare_quote_sources, resolve_references, TABLE_VERIFICATION_PROMPT
from services.grounded_numeric_rendering import check_numeric_claim

plan = json.load(sys.stdin)
paper_ids = [paper['pdfId'] for paper in plan['materials']]
light = paper_ids[1]
pdf = Path('/tmp/pixiu-table-probe/public-light.pdf')
tei = pdf.with_name('stage4-tables-v6-light.tei.xml')
assert hashlib.sha256(pdf.read_bytes()).hexdigest() + '.pdf' == light
sections = parse_tei_xml(str(tei), str(pdf))
main = next(section for section in sections if section.get('tableId') == 'tab_0')
fresh = main['tableVerifiedData']
rag = get_rag()


def index_hash():
    saved = rag.collection.get(include=['documents', 'metadatas'])
    rows = sorted(zip(saved['ids'], saved['documents'], saved['metadatas']))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class CapturedPrompt(Exception):
    pass


captured = {}
original = grounded_comparison.synthesize_comparison


def capture_sources(*args, **kwargs):
    captured['sources'] = deepcopy(args[1])
    return original(*args, **kwargs)


def capture_prompt(prompt, system):
    captured['prompt'] = prompt
    raise CapturedPrompt()


before = index_hash()
request = ConversationCapabilityRequest(taskId='offline-v11-table-scope-no-publish', capability='compare',
    message=next(case['prompt'] for case in plan['cases'] if case['id'] == 'stage4-compose-v9'),
    allowedPaperIds=paper_ids, primaryPaperId=paper_ids[0])
with (patch.object(DeepSeekLLM, 'invoke', side_effect=AssertionError('Provider forbidden')),
      patch.object(grounded_comparison, 'synthesize_comparison', side_effect=capture_sources),
      patch('services.socratic_service._call_guarded_llm', side_effect=capture_prompt)):
    try:
        _compare(request, [])
    except CapturedPrompt:
        pass
    else:
        raise AssertionError('Prompt capture was not reached')
assert TABLE_VERIFICATION_PROMPT in captured['prompt']
clean, validation, catalog = prepare_quote_sources(captured['sources'])
table = next(source for source in clean if source['pdfId'] == light and source.get('verifiedTable')
             and {9, 10} <= {row[0] for row in source['verifiedTable']['rows']})
packet = table['verifiedTable']
assert table['tableColumnMappingUnverified'] is True
assert packet['groups'] == fresh['groups']
assert all(row in fresh['rows'] for row in packet['rows'])
hardware = next((source, qid) for source in validation if source['pdfId'] == light
                for qid, quote in catalog[source['sourceId']].items()
                if 'All performance evaluations are conducted on an A6000 GPU.' in quote)
condition = [{'sourceId': hardware[0]['sourceId'], 'quoteId': hardware[1]}]
baseline = next(row for row in packet['rows'] if row[0] == 9)
refs = [{'sourceId': table['sourceId'], 'quoteId': next(qid for qid, quote in catalog[table['sourceId']].items()
         if quote == 'Table row ' + str(row[0]) + ': ' + ' | '.join([row[1], *row[2]]))}
        for row in packet['rows']]
checked = []
last_raw = None
for group in range(2):
    for metric, operation in [('FPS', 'value'), ('Size', 'inverse_ratio'), ('SSIM', 'difference')]:
        raw = {'summary': '核对结果为⟦数值1⟧。', 'kind': 'reported' if operation == 'value' else 'inference',
               'references': refs,
               'numericBindings': [{'id': 1, 'kind': 'experiment', 'sourceId': table['sourceId'],
                   'row': 10, 'baselineRow': 9, 'group': group, 'metric': metric, 'operation': operation,
                   'dataset': packet['groups'][group][0], 'hardware': 'A6000', 'baseline': baseline[1],
                   'conditionReferences': condition}]}
        checked.append(check_numeric_claim(resolve_references(raw, catalog), validation)['summary'])
        last_raw = raw
assert any('SSIM下降0.007' in text for text in checked)
assert any('SSIM下降0.013' in text for text in checked)
assert any('17.38倍' in text for text in checked)
rejections = {}
for mutation in ['unverified_row', 'wrong_dataset', 'wrong_hardware', 'unstarred_baseline']:
    invalid = deepcopy(last_raw)
    binding = invalid['numericBindings'][0]
    if mutation == 'unverified_row':
        binding['row'] = 8
    elif mutation == 'wrong_dataset':
        binding['dataset'] = packet['groups'][0][0]
    elif mutation == 'wrong_hardware':
        binding['hardware'] = 'A5000'
    else:
        binding['baseline'] = '3D-GS [16]'
    try:
        check_numeric_claim(resolve_references(invalid, catalog), validation)
    except ValueError as error:
        rejections[mutation] = str(error)
    else:
        raise AssertionError('Invalid condition accepted: ' + mutation)
after = index_hash()
assert before == after
print(json.dumps({'scope': __doc__, 'providerCalls': 0, 'taskWrites': 0, 'indexWrites': 0,
                  'pdfHashMatched': True, 'freshPdfVerifiedGroups': fresh['groups'],
                  'freshPdfVerifiedRowNumbers': [row[0] for row in fresh['rows']],
                  'actualPromptVerifiedRows': packet['rows'], 'rawUnverifiedFlagPreserved': True,
                  'promptExplainsRowWhitelist': True, 'controlledChecks': checked,
                  'rejections': rejections, 'indexBeforeHash': before, 'indexAfterHash': after}, ensure_ascii=False))
