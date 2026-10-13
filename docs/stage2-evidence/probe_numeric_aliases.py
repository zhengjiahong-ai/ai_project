"""Current persisted evidence plus controlled results, never a Provider answer."""
import hashlib
import json
from copy import deepcopy
from unittest.mock import patch

from llm.client import DeepSeekLLM
from rag.store import get_rag
from services.evidence_service import normalize_evidence_items
from services.evidence_quotes import prepare_quote_sources
from services.grounded_critique import check_critique_payload, synthesize_critique

B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
rag = get_rag()
def snapshot():
    data = rag.collection.get(where={'id': B}, include=['documents', 'metadatas'])
    return sorted(zip(data['ids'], data['documents'], data['metadatas']))
before = snapshot()
count = rag.collection.count()
sources = normalize_evidence_items(rag.get_documents_by_metadata({'id': B}, limit=100), pdf_id=B, max_text_chars=1800)
table = next(source for source in sources if 'Table row 9: 3D-GS' in source['text'] and 'Table row 10: Ours' in source['text']
             and (source.get('metadata') or {}).get('table_verified_data'))
hardware = next(source for source in sources if 'A6000 GPU' in source['text'])
selected = [table, hardware]
clean, validation, catalog = prepare_quote_sources(selected)
packet = next(source['verifiedTable'] for source in clean if source['sourceId'] == table['sourceId'])
baseline, ours = (next(row for row in packet['rows'] if row[0] == number) for number in (9, 10))
dataset = packet['groups'][0][0]
fps = ours[2][packet['groups'][0][1].index('FPS')]
refs = []
for row in (baseline, ours):
    literal = 'Table row ' + str(row[0]) + ': ' + ' | '.join([row[1], *row[2]])
    refs.append({'sourceId': table['sourceId'], 'quoteId': next(qid for qid, quote in catalog[table['sourceId']].items() if quote == literal)})
condition = [{'sourceId': hardware['sourceId'], 'quoteId': next(qid for qid, quote in catalog[hardware['sourceId']].items() if 'A6000 GPU' in quote)}]
claim = {'section': 'contribution', 'summary': f'{dataset}（A6000，{baseline[1]}基线）：Ours为{fps}帧/秒。',
    'kind': 'reported', 'references': refs, 'measurements': [{'sourceId': table['sourceId'], 'row': ours[0], 'group': 0,
    'metric': 'FPS', 'value': fps, 'baselineRow': baseline[0], 'dataset': dataset, 'hardware': 'A6000',
    'baseline': baseline[1], 'conditionReferences': condition}]}
payload = {'findings': [claim], 'pendingQuestions': []}
with (patch.object(DeepSeekLLM, '_call', side_effect=AssertionError('Provider blocked')),
      patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(payload, ensure_ascii=False)) as controlled):
    result = synthesize_critique('离线核验同一主表帧率和条件', selected)
rejections = {}
for alias in ('999帧/秒', '999帧每秒', '999 frames per second', '999×压缩', '999x compression', '999 MiB'):
    invalid = deepcopy(payload)
    invalid['findings'][0]['summary'] = f'{dataset}（A6000，{baseline[1]}基线）：{alias}。'
    try:
        check_critique_payload(invalid, validation, catalog)
    except ValueError as error:
        rejections[alias] = str(error)
after = snapshot()
checks = {'realFrameRateAndConditionsAccepted': fps + '帧/秒' in result['summary'] and dataset in result['summary'] and 'A6000' in result['summary'],
    'allSixAliasesRejected': len(rejections) == 6,
    'samePaperEvidenceOnly': {source['pdfId'] for source in validation} == {B},
    'oneControlledSynthesis': controlled.call_count == 1,
    'persistentDocumentsAndMetadataUnchanged': before == after and rag.collection.count() == count}
print('NUMERIC_ALIAS_JSON=' + json.dumps({'scope': 'Current index and controlled synthesis; not actual model content acceptance',
    'checks': checks, 'sourceIds': [source['sourceId'] for source in selected], 'indexCount': count,
    'paperSnapshotSha256': hashlib.sha256(json.dumps(before, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    'providerCalls': 0, 'taskWrites': 0, 'persistentIndexWrites': 0, 'controlledSummary': result['summary'],
    'rejections': rejections}, ensure_ascii=False))
assert all(checks.values())
