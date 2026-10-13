"""Exercise stale verification rejection with simulated authorization; never send data."""
import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
runner = HERE / 'verify_stage4_v12.py'
read_text = Path.read_text
version = sys.argv[1] if len(sys.argv) > 1 else 'v22'
assert version in {'v22', 'v24'}
plan_name = f'stage4-analysis-{version}-case-plan.json'
original = json.loads((HERE / plan_name).read_text(encoding='utf-8-sig'))
assert original['status'] == 'pending_new_authorization' and original['authorization'] is None
simulated = copy.deepcopy(original)
simulated.update(status='authorized', authorization='SIMULATION ONLY; not user approval', providerOriginVerified=True)
simulated['providerVerification'] = {
    'origin': original['provider'], 'model': 'deepseek-v4-pro', 'runningSince': 'recorded-start',
    'sourceHashes': {name: hashlib.sha256((HERE.parent.parent / 'ai-service-python/services' / name).read_bytes()).hexdigest()
        for name in ('conversation_capability_service.py', 'grounded_numeric_rendering.py', 'grounded_critique.py')},
}
cases = [
    ('unverified', 'Fresh runtime verification required'),
    ('wrong_verified_origin', 'Verified Provider does not match plan'),
    ('source_changed', 'Verified source changed'),
    ('restart', 'Verified runtime changed'),
    ('stopped', 'Verified runtime changed'),
    ('http', 'Actual Provider changed'),
    ('other_host', 'Actual Provider changed'),
    ('other_port', 'Actual Provider changed'),
    ('model_changed', 'Actual model changed'),
    ('valid_guard', 'NETWORK SENTINEL'),
]
checks = []
for scenario, reason in cases:
    plan = copy.deepcopy(simulated)
    runtime = {'Running': True, 'StartedAt': 'recorded-start'}
    configuration = {'scheme': 'https', 'hostname': 'api.deepseek.com', 'port': None, 'model': 'deepseek-v4-pro'}
    if scenario == 'unverified': plan['providerOriginVerified'] = False
    if scenario == 'wrong_verified_origin': plan['providerVerification']['origin'] = 'https://example.invalid'
    if scenario == 'source_changed': plan['providerVerification']['sourceHashes']['grounded_critique.py'] = 'stale'
    if scenario == 'restart': runtime['StartedAt'] = 'new-start'
    if scenario == 'stopped': runtime['Running'] = False
    if scenario == 'http': configuration['scheme'] = 'http'
    if scenario == 'other_host': configuration['hostname'] = 'example.invalid'
    if scenario == 'other_port': configuration['port'] = 8443
    if scenario == 'model_changed': configuration['model'] = 'other-model'

    def substitute(path, *args, **kwargs):
        return json.dumps(plan) if path.name == plan_name else read_text(path, *args, **kwargs)

    with (patch.object(sys, 'argv', [str(runner), 'critique', 'start', version]),
          patch.object(Path, 'read_text', substitute),
          patch('subprocess.check_output', side_effect=[json.dumps(runtime), json.dumps(configuration)]) as metadata,
          patch('urllib.request.urlopen', side_effect=AssertionError('NETWORK SENTINEL')) as network):
        try:
            runpy.run_path(str(runner), run_name='__main__')
        except AssertionError as error:
            assert str(error) == reason, (scenario, str(error))
        else:
            raise AssertionError('Expected guard rejection or controlled sentinel')
        assert network.call_count == (1 if scenario == 'valid_guard' else 0)
        checks.append({'scenario': scenario, 'outcome': reason, 'actualNetworkCalls': 0})
for capability, reason in [('critique', 'Explicit new authorization required'), ('compare', 'Case outside fixed plan')]:
    with (patch.object(sys, 'argv', [str(runner), capability, 'start', version]),
          patch('subprocess.check_output', side_effect=AssertionError('Docker forbidden')) as metadata,
          patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')) as network):
        try:
            runpy.run_path(str(runner), run_name='__main__')
        except AssertionError as error:
            assert str(error) == reason
        else:
            raise AssertionError('Expected authorization or case guard rejection')
        assert metadata.call_count == 0 and network.call_count == 0
        checks.append({'scenario': capability + '_pending_start', 'outcome': reason, 'actualNetworkCalls': 0})
assert json.loads((HERE / plan_name).read_text(encoding='utf-8-sig')) == original
assert not (HERE / f'stage4-critique-{version}-attempt.json').exists()
print(json.dumps({'checks': checks, 'casePlanUnchanged': True, 'authorizationWasSimulatedOnly': True,
    'actualNetworkCalls': 0, 'actualDockerCalls': 0, 'providerCalls': 0, 'taskWrites': 0}, ensure_ascii=False))
