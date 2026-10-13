"""Check synthetic bindings against the existing index; never generate answers."""
import hashlib
import json
import os
from copy import deepcopy

import chromadb
from chromadb.config import Settings

from services.evidence_service import normalize_evidence_items
from services.evidence_quotes import prepare_quote_sources, resolve_references
from services.grounded_numeric_rendering import check_numeric_claim
from services.comparison_measurements import name_key, verified_packet
from services.research_synthesis import evidence_body

PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
client = chromadb.PersistentClient(path=os.environ.get('CHROMA_DB_PATH', '/app/chroma_data'),
                                   settings=Settings(anonymized_telemetry=False))
collection = client.get_collection('literature_collection_v4_e5_small')


def snapshot():
    saved = collection.get(include=['documents', 'metadatas'])
    rows = sorted(zip(saved['ids'], saved['documents'], saved['metadatas']))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), saved


before_hash, before = snapshot()
paper_rows = [{'text': text, 'metadata': meta} for text, meta in zip(before['documents'], before['metadatas'])
              if meta.get('id') == PAPER]
assert len(paper_rows) == 55, 'Unexpected verification paper index'
sources = normalize_evidence_items(paper_rows, pdf_id=PAPER, max_text_chars=40000)
def contains_target_rows(source):
    packet = verified_packet(source, evidence_body(source['text']))
    return (packet and 'Mip-NeRF 360' in str(packet['groups'])
            and any('Ours' in row[1] for row in packet['rows'])
            and any(name_key(row[1]).startswith('3dgs*') for row in packet['rows']))


table = next(source for source in sources if contains_target_rows(source))
hardware = next(source for source in sources if 'NVIDIA A6000 GPU' in source['text'])
_, validation, catalog = prepare_quote_sources([table, hardware])
table = next(source for source in validation if source['sourceId'] == table['sourceId'])
hardware = next(source for source in validation if source['sourceId'] == hardware['sourceId'])
packet = table['_verifiedTable']
assert packet and len(packet['groups']) == 2
baseline, ours = packet['rows']
assert '3dgs*' in name_key(baseline[1]) and 'Ours' in ours[1], 'Unexpected source rows: ' + repr([baseline[1], ours[1]])
hardware_qid = next(qid for qid, quote in catalog[hardware['sourceId']].items() if 'NVIDIA A6000 GPU' in quote)
refs = []
for row in (baseline, ours):
    literal = f'Table row {row[0]}: ' + ' | '.join([row[1], *row[2]])
    refs.append({'sourceId': table['sourceId'], 'quoteId': next(qid for qid, quote in catalog[table['sourceId']].items() if quote == literal)})

bindings = []
for group in range(2):
    dataset, metrics = packet['groups'][group]
    for metric, operation in [('Size', 'inverse_ratio'), ('PSNR', 'difference')]:
        assert metric in metrics
        bindings.append({'id': len(bindings) + 1, 'kind': 'experiment', 'sourceId': table['sourceId'],
                         'row': ours[0], 'group': group, 'metric': metric, 'baselineRow': baseline[0],
                         'operation': operation, 'dataset': dataset, 'baseline': baseline[1],
                         'hardware': 'NVIDIA A6000 GPU',
                         'conditionReferences': [{'sourceId': hardware['sourceId'], 'quoteId': hardware_qid}]})
raw = {'kind': 'inference', 'summary': '核对值为⟦数值1⟧、⟦数值2⟧、⟦数值3⟧和⟦数值4⟧。',
       'references': refs, 'numericBindings': bindings}
selected = resolve_references(raw, catalog, require_selection=True)
checked = check_numeric_claim(selected, validation)
assert '17.38倍' in checked['summary'] and '17.32倍' in checked['summary']
assert '下降0.27' in checked['summary'] and '下降0.22' in checked['summary']
assert checked['summary'].count('NVIDIA A6000 GPU，基线') == 1
checks = {'computedRatios': True, 'computedDirection': True, 'twoDatasetBindings': True, 'sharedConditionOnce': True}
for name in ('dataset', 'baseline', 'foreignHardware'):
    changed, changed_sources = deepcopy(selected), deepcopy(validation)
    if name == 'foreignHardware':
        next(source for source in changed_sources if source['sourceId'] == hardware['sourceId'])['pdfId'] = 'foreign.pdf'
    else:
        changed['numericBindings'][0][name] = 'Wrong condition'
    try:
        check_numeric_claim(changed, changed_sources)
    except ValueError:
        checks[name + 'Rejected'] = True
    else:
        raise AssertionError('Invalid condition accepted: ' + name)
after_hash, after = snapshot()
assert after_hash == before_hash and len(after['ids']) == len(before['ids'])
checks['indexDocumentsAndMetadataUnchanged'] = True
print(json.dumps({'scope': 'Synthetic numeric bindings on actual current index; not real model quality acceptance',
                  'providerCalls': 0, 'taskWrites': 0, 'indexWrites': 0, 'paperId': PAPER,
                  'paperChunkCount': len(paper_rows), 'indexCount': len(before['ids']),
                  'indexVersions': sorted({row['metadata']['index_version'] for row in paper_rows}),
                  'beforeHash': before_hash, 'afterHash': after_hash, 'checks': checks,
                  'renderedClaim': checked}, ensure_ascii=False))
