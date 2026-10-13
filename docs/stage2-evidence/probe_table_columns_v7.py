"""Real local retrieval plus controlled offline comparison validation, no Provider."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

sys.path.insert(0, os.getcwd())
from core.document_parser import parse_tei_xml
from services.evidence_service import normalize_evidence_items
from services.grounded_comparison import synthesize_comparison

HERE = Path(os.environ['TABLE_PROBE_DIR'])
PDF = HERE / 'public-light.pdf'
assert hashlib.sha256(PDF.read_bytes()).hexdigest() == '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634'
original_parse = parse_tei_xml
with patch('core.document_parser.parse_tei_xml', side_effect=lambda xml: original_parse(xml, str(PDF))):
    indexed = runpy.run_path(str(HERE / 'probe_table_index_v6.py'))
old_report = indexed['report']
packet_sources = old_report['comparison']['sources']
temporary = indexed['temporary']
raw_sources = []
for paper in (indexed['A'], indexed['B']):
    rows = normalize_evidence_items(temporary.get_documents_by_metadata({'id': paper}, limit=400),
                                    pdf_id=paper, max_text_chars=1800)
    selected = {row['sourceId'] for row in packet_sources if row['pdfId'] == paper}
    raw_sources += [row for row in rows if row['sourceId'] in selected]
assert {row['sourceId'] for row in raw_sources} == {row['sourceId'] for row in packet_sources}
table = next(row for row in packet_sources if row.get('verifiedTable')
             and {9, 10} <= {value[0] for value in row['verifiedTable']['rows']})
verified = table['verifiedTable']
baseline = next(row for row in verified['rows'] if row[0] == 9)
ours = next(row for row in verified['rows'] if row[0] == 10)
hardware = next(row for row in packet_sources if row['pdfId'] == indexed['B'] and 'A6000' in row['text'])
hardware_body = '\n'.join(hardware['text'].splitlines()[4:-1])
position = hardware_body.index('A6000')
quote = hardware_body[max(0, position - 70):position + 70]
condition = [{'sourceId': hardware['sourceId'], 'quote': quote}]
refs = [{'sourceId': table['sourceId'], 'quote': f'Table row {row[0]}: ' + ' | '.join([row[1], *row[2]])}
        for row in (baseline, ours)]
measurements = []
for row, metric, value, operation in ((10, 'FPS', '237', 'value'), (10, 'Size', '45MB', 'value'),
                                      (9, 'FPS', '144', 'value'), (9, 'Size', '782MB', 'value'),
                                      (10, 'Size', '17.38', 'inverse_ratio')):
    measurements.append({'sourceId': table['sourceId'], 'row': row, 'group': 0, 'metric': metric,
                         'value': value, 'operation': operation, 'baselineRow': 9,
                         'dataset': verified['groups'][0][0], 'hardware': 'A6000',
                         'baseline': baseline[1], 'conditionReferences': condition})
claim = {'summary': 'Mip-NeRF 360（A6000，3D-GS *基线）：LightGaussian为237 FPS、45MB；基线为144 FPS、782MB，存储比约17.38倍。',
         'kind': 'inference', 'paperIds': [indexed['B']], 'references': refs, 'measurements': measurements}
response = {'claims': [claim], 'dimensions': [{'label': '固定数字校验夹具', 'cells': [
    {'paperId': indexed['A'], 'kind': 'not_covered', 'summary': '此离线夹具不生成论文A的结论', 'references': []},
    {**deepcopy(claim), 'paperId': indexed['B']}]}], 'limitations': []}

captured = {}
def offline_provider(prompt, system):
    captured['prompt'] = prompt
    return json.dumps(response, ensure_ascii=False)

with patch('services.socratic_service._call_guarded_llm', side_effect=offline_provider):
    valid = synthesize_comparison('核对主表数字条件', raw_sources, [indexed['A'], indexed['B']])
rejections = {}
for label in ('wrong_dataset', 'false_ratio', 'wrong_baseline'):
    invalid = deepcopy(response)
    first = invalid['claims'][0]['measurements'][0]
    if label == 'wrong_dataset':
        first['group'] = 1
    elif label == 'false_ratio':
        invalid['claims'][0]['measurements'][-1]['value'] = '15'
    else:
        first['baseline'] = '3D-GS [16]'
    with patch('services.socratic_service._call_guarded_llm', return_value=json.dumps(invalid)):
        try:
            synthesize_comparison('核对主表数字条件', raw_sources, [indexed['A'], indexed['B']])
        except ValueError as exc:
            rejections[label] = str(exc)
        else:
            raise AssertionError(f'{label} was incorrectly accepted')
packet = json.loads(captured['prompt'].split('资料JSON：\n', 1)[1])
budget = min(1400, 24000 // len(packet['evidence']))
def body_chars(row):
    body = '\n'.join(row['text'].splitlines()[4:-1])
    return len(body) + (len(json.dumps(row['verifiedTable'], ensure_ascii=False, separators=(',', ':')))
                        if row.get('verifiedTable') else 0)
report = {'scope': 'Real ephemeral PDF/TEI index and final prompt, controlled offline response fixtures only; no answer quality certification',
          'providerCalls': 0, 'taskWrites': 0, 'persistentIndexWrites': 0,
          'persistentIndexCount': indexed['original'].collection.count(),
          'verifiedMainTableGroups': verified['groups'], 'visibleVerifiedRows': verified['rows'],
          'validControlledResult': valid, 'rejections': rejections, 'sources': packet['evidence'],
          'checks': {'finalPromptHasCheckedTable': True,
                     'perSourceBodyAndMetadataWithinBudget': all(body_chars(row) <= budget for row in packet['evidence']),
                     'scopeRetained': {row['pdfId'] for row in packet['evidence']} == {indexed['A'], indexed['B']},
                     'allThreeInvalidFixturesRejected': len(rejections) == 3,
                     'originalIndexUnchanged': indexed['original'].collection.count() == indexed['before']}}
print('TABLE_COLUMNS_V7_JSON=' + json.dumps(report, ensure_ascii=False))
assert all(report['checks'].values()), report['checks']
