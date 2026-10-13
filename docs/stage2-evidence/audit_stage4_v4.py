"""Read archived provider outputs and local indexed evidence; never generate."""
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
READ_CACHE = r'''
import json, sqlite3, logging
from datetime import datetime, timezone
from services.llm_cache import _cache_db_path
from services.agent_grounded_answer import _extract_json_object
from services.research_synthesis import evidence_body, _flat
logging.disable(logging.CRITICAL)
since=datetime(2026,10,8,14,39,45,tzinfo=timezone.utc).timestamp()
until=datetime(2026,10,8,14,48,tzinfo=timezone.utc).timestamp()
db=sqlite3.connect('file:'+_cache_db_path()+'?mode=ro',uri=True)
rows=db.execute('SELECT response,created_at FROM llm_cache WHERE created_at>=? AND created_at<? ORDER BY created_at',(since,until)).fetchall()
translations=[]; compositions=[]
for response,created in rows:
    try: value=_extract_json_object(response)
    except Exception: continue
    if isinstance(value.get('translatedBlocks'),list):
        translations.append({'createdAt':created,'response':value})
    if isinstance(value.get('claims'),list) and isinstance(value.get('dimensions'),list):
        compositions.append({'createdAt':created,'response':value})
assert len(compositions)==1, 'Expected one fixed comparison output'
composition=compositions[0]['response']
refs=[r for claim in composition['claims'] for r in claim.get('references',[])]
refs += [r for row in composition['dimensions'] for cell in row['cells'] for r in cell.get('references',[])]
from rag.store import get_rag, normalize_id
rag=get_rag(); sources={}
papers={r['sourceId'].split('-chunk-')[0] for r in refs}
for paper in papers:
    for document in rag.get_documents_by_metadata({'id':normalize_id(paper)},limit=200):
        metadata=document.get('metadata') or {}
        sid=paper+'-chunk-'+str(metadata.get('chunk_index',metadata.get('chunkIndex')))
        if sid in {r['sourceId'] for r in refs}: sources[sid]=document['text']
checks=[]
for ref in refs:
    quote=ref['quote']; body=evidence_body(sources.get(ref['sourceId'],''))
    checks.append({'sourceId':ref['sourceId'],'quote':quote,'length':len(quote.strip()),
                   'sourceFound':ref['sourceId'] in sources,
                   'matchesFullBody':_flat(quote) in _flat(body),
                   'lengthAllowed':8<=len(quote.strip())<=300})
print(json.dumps({'translationCacheRows':translations,'composition':compositions[0],
                 'quoteChecks':checks,'validationFullSources':sources,'newModelCalls':0}))
'''
result = subprocess.run(['docker','exec','-i','ai_service_python','python','-c',READ_CACHE],
                        text=True,capture_output=True,check=True)
data=json.loads(result.stdout)
(HERE/'stage4-reading-v4-cached-responses.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
base='http://127.0.0.1:8081/api/task-workspaces'
with urlopen(base+'/task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe',timeout=15) as response:
    task=json.load(response)
notes=[note for note in task['notes'] if (note.get('source') or {}).get('text','').strip()=='significance']
assert len(notes)==1, 'Expected the new lowercase selection note'
receipt={'taskId':task['id'],'revision':task['revision'],'note':notes[0],
         'modelCasesSubmitted':1,'automaticRetryAllowed':False}
(HERE/'stage6-selection-v4-runtime.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'translationBatches':len(data['translationCacheRows']), 'comparisonQuotes':len(data['quoteChecks']),
                  'failedFullQuoteChecks':[r for r in data['quoteChecks'] if not r['matchesFullBody'] or not r['lengthAllowed']],
                  'noteId':notes[0]['id'],'newModelCalls':0},ensure_ascii=False))
