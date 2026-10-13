"""Archive completed v9 cases from local cache/API. No model calls or writes to tasks."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
plan = json.loads((HERE / 'stage4-reading-v9-case-plan.json').read_text(encoding='utf-8-sig'))
start = datetime.fromisoformat(plan['authorizedAt']).timestamp()
end = datetime.now(timezone.utc).timestamp()
code = '''
import json, sqlite3, sys
from services.llm_cache import _cache_db_path
from services.agent_grounded_answer import _extract_json_object
db=sqlite3.connect('file:'+_cache_db_path()+'?mode=ro',uri=True)
rows=db.execute('SELECT model,temperature,response,created_at FROM llm_cache WHERE created_at>=? AND created_at<? ORDER BY created_at',(float(sys.argv[1]),float(sys.argv[2]))).fetchall()
result=[]
for model,temp,response,created in rows:
    try: parsed=_extract_json_object(response)
    except Exception: parsed=response
    result.append({'model':model,'temperature':temp,'createdAt':created,'response':parsed})
print(json.dumps(result,ensure_ascii=False))
'''
cached = subprocess.run(['docker', 'exec', 'ai_service_python', 'python', '-c', code, str(start), str(end)],
                        text=True, encoding='utf-8', capture_output=True, check=True)
responses = json.loads(cached.stdout)
(HERE / 'stage4-reading-v9-cached-responses.json').write_text(json.dumps({
    'scope': 'Local cache rows in authorization time window; rows are not total requests or charges',
    'startUtc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
    'endUtc': datetime.fromtimestamp(end, timezone.utc).isoformat(),
    'cacheRows': responses, 'newModelCalls': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'cacheRows': len(responses), 'newModelCalls': 0}))

