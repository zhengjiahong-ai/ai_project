"""Ephemeral local embeddings/BM25 through actual critique/comparison prompt paths."""
import json
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
sys.path.insert(0, os.getcwd())
import chromadb
from chromadb.config import Settings
from core.document_parser import parse_tei_xml
from core.rag_vector_db import LiteratureRAG
from core.hybrid_retriever import HybridRetriever
from rag import store

HERE = Path(os.environ['TABLE_PROBE_DIR'])
A = 'f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf'
B = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
original = store.get_rag()
before = original.collection.count()
temporary = object.__new__(LiteratureRAG)
temporary.embedding_model = original.embedding_model
temporary.embedding_model_name = original.embedding_model_name
temporary.query_prefix, temporary.passage_prefix = original.query_prefix, original.passage_prefix
client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
temporary.collection = client.create_collection('table_probe_v6', metadata={'hnsw:space': 'cosine'})
raw_a = original.collection.get(where={'id': A}, include=['documents', 'metadatas', 'embeddings'])
assert raw_a['ids']
temporary.collection.add(ids=raw_a['ids'], documents=raw_a['documents'],
                         metadatas=raw_a['metadatas'], embeddings=raw_a['embeddings'].tolist())
sections = parse_tei_xml(str(HERE / 'stage4-tables-v6-light.tei.xml'))
with patch('core.rag_vector_db.invalidate_hybrid_cache'):
    count = temporary.add_sections_to_db(sections, 'public-light.pdf', {'id': B, 'title': 'LightGaussian'})
tables = [row for row in temporary.get_documents_by_metadata({'id': B}, limit=400)
          if row['metadata'].get('evidence_kind') == 'table']
assert len({row['metadata']['table_id'] for row in tables}) == 9
main = [row for row in tables if row['metadata']['table_id'] == 'tab_0']
assert all(row['metadata']['page_index'] == 5 for row in main)
assert all(row['metadata']['table_column_mapping_unverified'] for row in main)
assert any('3D-GS * [16]' in ' '.join(row['text'].split()) and '782MB' in row['text'] for row in main)
assert any('Ours | 237 | 45MB' in row['text'] for row in main)
hybrid = HybridRetriever(temporary)
with patch('rag.store.get_rag', return_value=temporary), \
     patch('rag.store.get_hybrid', return_value=hybrid), \
     patch('services.analysis_service.get_rag', return_value=temporary):
    captured = runpy.run_path(str(HERE / 'probe_focus_v5.py'))
comparison = captured['report']['comparison']
light = [row for row in comparison['sources'] if row['pdfId'] == B]
body = '\n'.join(row['text'] for row in light)
report = {'scope': 'Ephemeral local index; original 3DGS chunks copied unchanged, LightGaussian reparsed; final prompt only',
          'providerCalls': 0, 'taskWrites': 0, 'persistentIndexWrites': 0,
          'persistentCountBefore': before, 'persistentCountAfter': original.collection.count(),
          'lightChunkCount': count, 'tableChunkCount': len(tables), 'distinctTables': 9,
          'comparison': comparison, 'axes': captured['report']['axes'],
          'checks': {'mainBaselineRowInComparison': '3D-GS * [16]' in ' '.join(body.split()) and '782MB' in body,
                     'mainOursRowInComparison': 'Ours | 237 | 45MB' in body,
                     'unverifiedColumnFlagInComparison': any(row['tableColumnMappingUnverified'] for row in light),
                     'hardwareAndDatasetsRetained': 'A6000' in body and 'Mip-NeRF360' in body,
                     'originalIndexUnchanged': before == original.collection.count()}}
print('TABLE_INDEX_PROBE_JSON=' + json.dumps(report, ensure_ascii=False))
assert all(report['checks'].values()), report['checks']
