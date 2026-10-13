"""Check original cached numeric claims against current indexed text, without generation.

The full corpus confirms literal provenance, not the exact old prompt window.
This does not publish or turn old failed receipts into successful operations.
"""
import hashlib
import json
import os
import sys

import chromadb
from chromadb.config import Settings

from services.comparison_measurements import verified_packet
from services.evidence_quotes import excerpt_catalog, resolve_references
from services.evidence_service import normalize_evidence_items
from services.grounded_numeric_rendering import check_numeric_claim
from services.research_synthesis import evidence_body

recorded = json.load(sys.stdin)
client = chromadb.PersistentClient(path=os.environ.get('CHROMA_DB_PATH', '/app/chroma_data'),
                                   settings=Settings(anonymized_telemetry=False))
collection = client.get_collection('literature_collection_v4_e5_small')

def snapshot():
    saved = collection.get(include=['documents', 'metadatas'])
    rows = sorted(zip(saved['ids'], saved['documents'], saved['metadatas']))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), saved

before_hash, saved = snapshot()
sources = []
for material in recorded['plan']['materials']:
    paper = material['pdfId']
    rows = [{'text': text, 'metadata': meta} for text, meta in zip(saved['documents'], saved['metadatas'])
            if meta.get('id') == paper]
    sources.extend(normalize_evidence_items(rows, pdf_id=paper, max_text_chars=40000))
catalog = {}
for source in sources:
    body = evidence_body(source['text'])
    source['_verifiedTable'] = verified_packet(source, body)
    catalog[source['sourceId']] = excerpt_catalog(source['sourceId'], body)

checks = []
for row in recorded['cache']['cacheRows']:
    payload = row['response']
    if not isinstance(payload, dict):
        continue
    for claim in payload.get('findings', []) + payload.get('claims', []) + [cell for dim in payload.get('dimensions', []) for cell in dim['cells']]:
        entry = {'originalSummary': claim['summary'], 'bindingCount': len(claim.get('numericBindings', []))}
        try:
            resolved = resolve_references(claim, catalog, require_selection=True)
            result = check_numeric_claim(resolved, sources)
            entry.update(status='passed', renderedSummary=result['summary'])
        except ValueError as error:
            entry.update(status='rejected', error=str(error))
        checks.append(entry)
after_hash, _ = snapshot()
assert before_hash == after_hash
print(json.dumps({'scope': __doc__, 'providerCalls': 0, 'taskWrites': 0, 'indexWrites': 0,
                  'beforeHash': before_hash, 'afterHash': after_hash, 'indexCount': len(saved['ids']),
                  'claims': checks}, ensure_ascii=False))
