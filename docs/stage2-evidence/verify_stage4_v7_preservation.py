"""Compare archived task state after the three authorized cases; no network."""
import json
from pathlib import Path

HERE = Path(__file__).parent
read = lambda name: json.loads((HERE / name).read_text(encoding='utf-8-sig'))
before = read('stage6-reading-v7-before.json')
after = read('stage6-reading-v7-after.json')
tasks = read('stage4-reading-v7-tasks.json')
checks = {'readingTaskAllFieldsUnchanged': before == after}
for case in ('critique', 'compose'):
    receipt = read(f'stage4-{case}-v7-receipt.json')
    checks[case + 'TerminalFailed'] = receipt['status'] == 'failed'
    checks[case + 'NoPublishedArtifact'] = tasks[case]['artifacts'] == []
    checks[case + 'OneSubmission'] = read(f'stage4-{case}-v7-attempt.json')['submitAttempts'] == 1
checks['translationOneSubmission'] = read('stage6-translation-v7-attempt.json')['generationSubmissions'] == 1
result = {'scope': 'Preservation and submission checks only; all three content cases not accepted',
          'checks': checks, 'readingRevisionBefore': before['revision'], 'readingRevisionAfter': after['revision'],
          'newModelCalls': 0, 'taskWrites': 0}
(HERE / 'stage4-reading-v7-preservation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result))
assert all(checks.values())
