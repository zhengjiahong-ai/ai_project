"""Real process termination at durable call/publication boundaries, without an API."""
import subprocess
import sys
from pathlib import Path

import pytest

from services.deep_research.contracts import UnresolvedUnknownError, LateCompletionError
from services.deep_research.repository import DeepResearchRepository


def test_abrupt_process_exit_preserves_unknown_reservation_and_unpublished_report(tmp_path):
    database = tmp_path / 'interrupted.sqlite3'
    worker = '''
import os, sys
from services.deep_research.repository import DeepResearchRepository
repo = DeepResearchRepository(sys.argv[1])
repo.initialize()
repo.create_run({'runId': 'interrupted'})
repo.begin_execution('interrupted')
done, _ = repo.reserve_call(run_id='interrupted', node='read', tool='read', args_digest='known', budget_delta={'tokens': 50})
repo.complete_call(done['callId'], status='succeeded', result={'text': 'saved evidence'})
repo.reserve_call(run_id='interrupted', node='synthesize', tool='llm_invoke', args_digest='sent', budget_delta={'modelCalls': 1, 'tokens': 2000})
repo.create_run({'runId': 'published'})
repo.begin_execution('published')
repo.publish_report(run_id='published', dedup_key='version-1', payload={'summary': 'saved report'}, outcome='complete', report_text='saved report')
os._exit(23)
'''
    result = subprocess.run([sys.executable, '-c', worker, str(database)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=20)
    assert result.returncode == 23, result.stderr.decode(errors='replace')
    repo = DeepResearchRepository(str(database))
    repo.initialize()
    assert repo.require_run('interrupted')['status'] == 'running'
    repo.recover()
    saved = repo.require_run('interrupted')
    assert saved['status'] == 'paused'
    assert saved['budget']['tokens'] == 2050 and saved['budget']['modelCalls'] == 1
    calls = repo.list_calls('interrupted')
    assert [c['status'] for c in calls] == ['succeeded', 'unknown']
    assert calls[0]['result'] == {'text': 'saved evidence'}
    with pytest.raises(UnresolvedUnknownError):
        repo.begin_execution('interrupted')
    with pytest.raises(LateCompletionError):
        repo.complete_call(calls[1]['callId'], status='succeeded', result={'late': True})
    assert len(repo.list_calls('interrupted')) == 2
    assert repo.require_run('published')['report'] == 'saved report'
    assert repo.require_run('published')['status'] == 'completed'
    events = repo.list_outbox('published')
    assert len(events) == 1 and not events[0]['published']
    _, created = repo.publish_report(run_id='published', dedup_key='version-1',
                                     payload={'summary': 'saved report'}, outcome='complete', report_text='saved report')
    assert not created and len(repo.list_outbox('published')) == 1
