"""Archive only two expected structured responses; refuse unrelated cache rows."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).parent
version = sys.argv[1] if len(sys.argv) == 2 else 'v12'
assert version in {'v12', 'v13'} and len(sys.argv) <= 2
plan = json.loads((HERE / f'stage4-analysis-{version}-case-plan.json').read_text(encoding='utf-8-sig'))
for case in plan['cases']:
    with urlopen('http://127.0.0.1:8081/api/task-workspaces/' + case['taskId'] + '/operations/' + case['requestId']) as response:
        receipt = json.load(response)
    assert receipt['status'] in {'succeeded', 'failed', 'cancelled'}, 'Original requests are not terminal'
start = datetime.fromisoformat(plan['authorizedAt']).timestamp()
end = datetime.now(timezone.utc).timestamp()
code = '''
import json, sqlite3, sys
from services.llm_cache import _cache_db_path
from services.agent_grounded_answer import _extract_json_object
db=sqlite3.connect('file:'+_cache_db_path()+'?mode=ro',uri=True)
rows=db.execute('SELECT model,temperature,response,created_at FROM llm_cache WHERE created_at>=? AND created_at<? ORDER BY created_at',(float(sys.argv[1]),float(sys.argv[2]))).fetchall()
assert len(rows)==2, 'Cache window contains unexpected rows; inspect ownership before archiving'
result=[]
papers=set(json.loads(sys.argv[3]))
for model,temp,response,created in rows:
    parsed=_extract_json_object(response)
    assert isinstance(parsed,dict) and ('findings' in parsed or 'dimensions' in parsed)
    claims=parsed.get('findings',[])+parsed.get('claims',[])+[cell for row in parsed.get('dimensions',[]) for cell in row.get('cells',[])]
    refs=[ref for claim in claims for ref in claim.get('references',[])]
    assert refs and all(any(str(ref.get('sourceId','')).startswith(paper[:-4]) for paper in papers) for ref in refs)
    result.append({'model':model,'temperature':temp,'createdAt':created,'response':parsed})
assert sum('findings' in row['response'] for row in result)==1
assert sum('dimensions' in row['response'] for row in result)==1
print(json.dumps(result,ensure_ascii=False))
'''
cached = subprocess.run(['docker', 'exec', 'ai_service_python', 'python', '-c', code, str(start), str(end),
                         json.dumps([paper['pdfId'] for paper in plan['materials']])],
                         text=True, encoding='utf-8', capture_output=True, check=True)
responses = json.loads(cached.stdout)
output = HERE / f'stage4-analysis-{version}-cached-responses.json'
with output.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps({
    'scope': 'Two structured cache rows in authorization window with references restricted to approved papers; rows are not request or charge totals',
    'startUtc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
    'endUtc': datetime.fromtimestamp(end, timezone.utc).isoformat(),
    'cacheRows': responses, 'newModelCalls': 0}, ensure_ascii=False, indent=2))
print(json.dumps({'cacheRows': len(responses), 'newModelCalls': 0}))
