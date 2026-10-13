"""One explicit, durable live call using the original stage-2 evidence snapshot."""
import json
import os
from pathlib import Path

from services.research_synthesis import synthesize_research_finding
from services.research_aggregator import build_research_report

root = Path('/app/data')
output = root / 'stage4-synthesis-20261008.json'
started = root / 'stage4-synthesis-20261008.started.json'
if output.exists():
    print(json.dumps({'status': 'saved', 'output': str(output)}))
    raise SystemExit()
if started.exists():
    raise RuntimeError('Existing live-call identity; inspect its process/output before any resubmission')
started.write_text(json.dumps({'pid': os.getpid(), 'status': 'running'}), encoding='utf-8')
try:
    payload = json.loads(Path('/app/scripts/stage4-evidence-input.json').read_text(encoding='utf-8'))
    result = synthesize_research_finding(payload['question'], payload['evidence'])
    finding = {**result, 'subQuestion': payload['question'], 'sources': payload['evidence']}
    report = build_research_report(payload['question'], '', [], [finding])
    output.write_text(json.dumps({'result': result, 'report': report}, ensure_ascii=False, indent=2), encoding='utf-8')
    started.write_text(json.dumps({'pid': os.getpid(), 'status': 'succeeded'}), encoding='utf-8')
    print(json.dumps({'status': 'succeeded', 'claims': len(result['claims']), 'output': str(output)}))
except Exception as error:
    started.write_text(json.dumps({'pid': os.getpid(), 'status': 'failed', 'error': str(error)}, ensure_ascii=False), encoding='utf-8')
    raise
