"""Archive this fixed live round; read-only DB/API access, no provider calls."""
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
READ = r'''
import json, sqlite3, logging
from datetime import datetime, timezone
from services.llm_cache import _cache_db_path
from services.agent_grounded_answer import _extract_json_object
from rag.store import get_rag, normalize_id
from services.evidence_service import _resolve_source_id
from services.research_synthesis import evidence_body, _flat
logging.disable(logging.CRITICAL)
start=datetime(2026,10,9,2,0,28,tzinfo=timezone.utc).timestamp()
end=datetime(2026,10,9,2,4,tzinfo=timezone.utc).timestamp()
db=sqlite3.connect('file:'+_cache_db_path()+'?mode=ro',uri=True)
rows=db.execute('SELECT response,created_at FROM llm_cache WHERE created_at>=? AND created_at<? ORDER BY created_at',(start,end)).fetchall()
cache=[]; comparisons=[]
for response,created in rows:
    try: value=_extract_json_object(response)
    except Exception: value=response
    cache.append({'createdAt':created,'response':value})
    if isinstance(value,dict) and isinstance(value.get('claims'),list) and isinstance(value.get('dimensions'),list): comparisons.append(value)
assert len(comparisons)==1
refs=[r for c in comparisons[0]['claims'] for r in c.get('references',[])]
refs += [r for d in comparisons[0]['dimensions'] for c in d['cells'] for r in c.get('references',[])]
papers=['f4c0c9f27e2d02b0265017f66049d471eb66cb50203bc918f51ba07d20cbbe11.pdf','803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf']
sources={}
for paper in papers:
    for doc in get_rag().get_documents_by_metadata({'id':normalize_id(paper)},limit=200):
        md=doc.get('metadata') or {}
        sid=_resolve_source_id(doc,paper,md.get('chunk_index'),0)
        sources[sid]=doc['text']
checks=[{'sourceId':r['sourceId'],'quote':r['quote'],'sourceFound':r['sourceId'] in sources,'matchesFullBody':_flat(r['quote']) in _flat(evidence_body(sources.get(r['sourceId'],'')))} for r in refs]
print(json.dumps({'cacheRows':cache,'comparison':comparisons[0],'quoteChecks':checks,'newModelCalls':0},ensure_ascii=False))
'''
result = subprocess.run(['docker','exec','ai_service_python','python','-c',READ],text=True,encoding='utf-8',capture_output=True,check=True)
data=json.loads(result.stdout)
(HERE/'stage4-reading-v5-cached-responses.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
base='http://127.0.0.1:8081/api/task-workspaces/'
with urlopen(base+'task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe',timeout=30) as response: task=json.load(response)
(HERE/'stage6-selection-v5-runtime.json').write_text(json.dumps({'task':task,'scope':'Current saved selection and prior artifacts, read-only','newModelCalls':0},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'cacheRows':len(data['cacheRows']),'failedQuotes':[x for x in data['quoteChecks'] if not x['matchesFullBody']],'taskRevision':task['revision'],'noteCount':len(task['notes'])},ensure_ascii=False))
