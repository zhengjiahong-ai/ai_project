"""Simulated missing authorization and an out-of-plan case fail before network."""
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

runner = Path(__file__).with_name('verify_stage4_v12.py')
read_text = Path.read_text
version = sys.argv[1] if len(sys.argv) > 1 else 'v18'
assert version in {'v18', 'v19', 'v22'}


def pending_plan(path, *args, **kwargs):
    original = read_text(path, *args, **kwargs)
    if path.name == f'stage4-analysis-{version}-case-plan.json':
        plan = json.loads(original)
        plan.update(status='pending_new_authorization', authorization=None)
        return json.dumps(plan)
    return original

for case, reason in [('critique', 'Explicit new authorization required'),
                     ('compare', 'Case outside fixed plan')]:
    with (patch.object(sys, 'argv', [str(runner), case, 'start', version]),
          patch.object(Path, 'read_text', pending_plan),
          patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')) as network):
        try:
            runpy.run_path(str(runner), run_name='__main__')
        except AssertionError as error:
            assert str(error) == reason
        else:
            raise AssertionError('Disallowed start accepted')
        assert network.call_count == 0
print('Pending critique and out-of-plan comparison refused before network; requests=0, submissions=0')
