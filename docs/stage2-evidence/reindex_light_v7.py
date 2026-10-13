"""Refresh one public verification PDF, keeping a recoverable old-index snapshot."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
sys.path.insert(0, os.getcwd())
from core.document_parser import parse_tei_xml
from rag.store import get_rag

HERE = Path(os.environ['TABLE_PROBE_DIR'])
PDF = HERE / 'public-light.pdf'
PAPER = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
assert hashlib.sha256(PDF.read_bytes()).hexdigest() + '.pdf' == PAPER
research = Path(os.environ.get('RESEARCH_TASK_DB_PATH', '/app/data/research_tasks.sqlite3'))
operations = Path(os.environ.get('TASK_OPERATION_DB_PATH') or research.with_name('task_operations.sqlite3'))
for database, query in ((operations, "select request_id from task_operations where status in ('queued','running','cancelling')"),
                        (research, "select taskId from research_tasks where status not in ('failed','cancelled','succeeded','awaiting_plan_review','awaiting_final_review')")):
    assert database.is_file(), f'Authoritative task database missing: {database}'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        assert not connection.execute(query).fetchall(), 'Active generation; index refresh refused'

def serializable(data):
    return {key: value.tolist() if hasattr(value, 'tolist') else value for key, value in data.items()}

def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

rag = get_rag()
include = ['documents', 'metadatas', 'embeddings']
before = serializable(rag.collection.get(where={'id': PAPER}, include=include))
assert before['ids'] and all(meta['id'] == PAPER for meta in before['metadatas'])
other_before = serializable(rag.collection.get(where={'id': {'$ne': PAPER}}, include=include))
backup = HERE / 'stage4-light-index-v7-backup.json'
if not backup.exists():
    backup.write_text(json.dumps(before, ensure_ascii=False), encoding='utf-8')
else:
    assert digest(json.loads(backup.read_text(encoding='utf-8'))) == digest(before), 'Existing backup differs; do not overwrite'
sections = parse_tei_xml(str(HERE / 'stage4-tables-v6-light.tei.xml'), str(PDF))
assert len(next(section for section in sections if section.get('tableId') == 'tab_0')['tableVerifiedData']['rows']) == 8
def denied(*args, **kwargs):
    raise AssertionError('Provider calls are prohibited during index refresh')
with patch('llm.client.get_llm', side_effect=denied), patch('services.analysis_service.get_llm', side_effect=denied):
    count = rag.add_sections_to_db(sections, str(PDF), {'id': PAPER, 'title': before['metadatas'][0]['title']})
after = serializable(rag.collection.get(where={'id': PAPER}, include=include))
other_after = serializable(rag.collection.get(where={'id': {'$ne': PAPER}}, include=include))
table_meta = [meta for meta in after['metadatas'] if meta.get('evidence_kind') == 'table']
report = {'scope': 'One existing public verification PDF index refreshed; no task/receipt/cache migration',
          'providerCalls': 0, 'taskWrites': 0, 'paperId': PAPER,
          'oldChunkCount': len(before['ids']), 'newChunkCount': count,
          'allIndexCount': rag.collection.count(), 'backupFile': backup.name,
          'backupSha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
          'indexVersions': sorted({meta['index_version'] for meta in after['metadatas']}),
          'tableChunkCount': len(table_meta), 'otherPapersBeforeHash': digest(other_before),
          'otherPapersAfterHash': digest(other_after)}
assert digest(other_before) == digest(other_after), 'Unrelated index data changed'
assert count == len(after['ids']) == 55 and len(table_meta) == 18
assert len(report['indexVersions']) == 1
print('LIGHT_REINDEX_V7_JSON=' + json.dumps(report, ensure_ascii=False))
