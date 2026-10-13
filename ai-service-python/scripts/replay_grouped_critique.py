"""Validate saved real outputs under the current contract without a provider call."""
import json
import argparse
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ai-service-python'))
from services.grounded_critique import synthesize_critique
from services.conversation_capability_service import execute_conversation
from schemas.conversation import ConversationCapabilityRequest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('cases', nargs='*', default=['focused-quality', 'review-quality'])
args = parser.parse_args()
for name in args.cases:
    if name not in ('focused-quality', 'review-quality'):
        raise SystemExit('Older catalogs differ: only the fixed quality cases can be replayed with this catalog.')
    packet = json.loads((ROOT / 'docs/critique-evidence-20261011' / f'{name}.json').read_text(encoding='utf-8'))
    with patch('services.socratic_service._call_guarded_llm', return_value=packet['rawResponse']) as provider:
        native = synthesize_critique(packet['question'], packet['sources'], allow_partial=True)
    request = ConversationCapabilityRequest(taskId='critique-acceptance', message=packet['question'], capability='critique',
        allowedPaperIds=['LightGaussian-public'], primaryPaperId='LightGaussian-public')
    with patch('services.conversation_capability_service._critique', return_value=native):
        result = execute_conversation(request)
    out = ROOT / 'docs/critique-evidence-20261011' / f'{name}-replay.json'
    out.write_text(json.dumps({'providerCalls': 0, 'originalProviderCalls': packet['providerCalls'], 'result': result}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'case': name, 'partial': result['partial'], 'summary': result['message'], 'issues': len(result['critique']['issues'])}, ensure_ascii=False))
