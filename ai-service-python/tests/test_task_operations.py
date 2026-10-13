import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.operation_control import check_cancelled
from services.task_operation_service import OperationConflict, OperationStore


def test_failed_operation_logs_diagnostic_but_keeps_public_error_generic(tmp_path, caplog):
    def fail(*_):
        raise ValueError('test-only-invalid-quote')
    store = OperationStore(tmp_path / 'failed.sqlite3', fail)
    store.submit('task', 'failure', 'conversation.execute', {})
    store.close()
    receipt = store.get('task', 'failure')
    assert receipt['status'] == 'failed'
    assert 'test-only-invalid-quote' not in receipt['error']
    assert 'task=task request=failure' in caplog.text
    assert 'test-only-invalid-quote' in caplog.text


def test_conversation_adapter_uses_durable_receipt_and_replays_once(tmp_path, monkeypatch):
    from services import conversation_capability_service as conversation
    from services.task_operation_service import execute_capability
    calls = []
    def chat(request, prior=None):
        calls.append(request.allowedPaperIds)
        return {'status': 'success', 'message': '结果', 'rag_sources': []}
    monkeypatch.setattr(conversation, '_chat', chat)
    payload = {'upstream': {'taskId': 'task', 'message': '问题', 'allowedPaperIds': ['A.pdf']}}
    store = OperationStore(tmp_path / 'conversation.sqlite3', execute_capability)
    store.submit('task', 'conversation', 'conversation.execute', payload)
    store.close()
    result = store.get('task', 'conversation')
    assert result['status'] == 'succeeded'
    assert result['result']['materialScope']['allowedPaperIds'] == ['A.pdf']
    assert store.submit('task', 'conversation', 'conversation.execute', payload)['result'] == result['result']
    assert calls == [['A.pdf']]


def test_duplicate_concurrent_request_executes_once_and_persists_result(tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def handler(kind, payload):
        calls.append(payload)
        entered.set()
        assert release.wait(3)
        return {"state": {"activityId": "a"}}
    path = tmp_path / "ops.sqlite3"
    store = OperationStore(path, handler)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(lambda _: store.submit("task", "same-id", "learning.start", {"paper": "A"}), range(8)))
        assert entered.wait(3)
        assert len(calls) == 1
        assert {r["requestId"] for r in receipts} == {"same-id"}
        with pytest.raises(OperationConflict):
            store.submit("task", "same-id", "learning.start", {"paper": "B"})
        release.set()
        store.close()
        reopened = OperationStore(path, lambda *_: pytest.fail("receipt must not execute twice"))
        try:
            reopened.recover_after_restart()
            receipt = reopened.submit("task", "same-id", "learning.start", {"paper": "A"})
            assert receipt["status"] == "succeeded"
            assert receipt["result"]["state"]["activityId"] == "a"
            assert reopened.list("other") == []
        finally:
            reopened.close()
    finally:
        release.set()
        store.close()


def test_cancel_remains_cancelling_until_worker_exits_and_blocks_next_model_step(tmp_path):
    entered, release = threading.Event(), threading.Event()
    called_after_cancel = []
    def handler(*_):
        entered.set()
        assert release.wait(3)
        check_cancelled()
        called_after_cancel.append(True)
    store = OperationStore(tmp_path / "ops.sqlite3", handler)
    try:
        store.submit("task", "one", "learning.action", {})
        assert entered.wait(3)
        assert store.cancel("task", "one")["status"] == "cancelling"
        with pytest.raises(OperationConflict):
            store.submit("task", "two", "learning.action", {})
        release.set()
        store.close()
        assert store.get("task", "one")["status"] == "cancelled"
        assert called_after_cancel == []
        assert store.submit("task", "one", "learning.action", {})["status"] == "cancelled"
    finally:
        release.set()
        store.close()


def test_process_restart_retains_ambiguous_request_without_repeating(tmp_path):
    store = OperationStore(tmp_path / "ops.sqlite3", lambda *_: pytest.fail("never replay"))
    # Simulate a crash after durable reservation and before result storage.
    store.executor.submit = lambda *_: None
    store.submit("task", "one", "learning.start", {})
    store._set("task", "one", "running")
    store.recover_after_restart()
    assert store.submit("task", "one", "learning.start", {})["status"] == "interrupted"
    assert "不会自动重复" in store.get("task", "one")["error"]
    store.close()


def test_failure_and_queued_cancellation_do_not_reexecute(tmp_path):
    calls = []
    def fail(*_):
        calls.append(True)
        raise RuntimeError("private provider information")
    store = OperationStore(tmp_path / "ops.sqlite3", fail)
    store.submit("task", "one", "learning.start", {})
    store.close()
    assert store.get("task", "one")["status"] == "failed"
    assert "private" not in store.get("task", "one")["error"]
    assert store.submit("task", "one", "learning.start", {})["status"] == "failed"
    assert len(calls) == 1
    other = OperationStore(tmp_path / "queued.sqlite3", fail)
    other.executor.submit = lambda *_: None
    other.submit("task", "q", "learning.start", {})
    assert other.cancel("task", "q")["status"] == "cancelled"
    other._run("task", "q")
    assert len(calls) == 1
    other.close()


def test_stop_before_submission_is_durable_and_blocks_late_execution(tmp_path):
    path = tmp_path / 'stopped.sqlite3'
    payload = {'original': {'message': 'question'}, 'upstream': {}}
    store = OperationStore(path, lambda *_: pytest.fail('Stopped intent must never run'))
    assert store.submit('task', 'lost', 'conversation.execute', payload, cancelled=True)['status'] == 'cancelled'
    assert store.submit('task', 'lost', 'conversation.execute', payload)['status'] == 'cancelled'
    store.close()
    reopened = OperationStore(path, lambda *_: pytest.fail('Refresh must not restart stopped intent'))
    reopened.recover_after_restart()
    assert reopened.submit('task', 'lost', 'conversation.execute', payload)['status'] == 'cancelled'
    assert len(reopened.list('task')) == 1
    with pytest.raises(OperationConflict):
        reopened.submit('task', 'lost', 'conversation.execute', {'original': {'message': 'different'}}, cancelled=True)
    reopened.close()


def test_stop_reservation_cancels_a_racing_submission_with_same_original_intent(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def handler(*_):
        entered.set()
        assert release.wait(3)
        check_cancelled()
        pytest.fail('Must stop before another model step')
    store = OperationStore(tmp_path / 'race.sqlite3', handler)
    try:
        original = {'message': 'same question'}
        store.submit('task', 'race', 'conversation.execute', {'original': original, 'upstream': {'history': ['saved']}})
        assert entered.wait(3)
        assert store.submit('task', 'race', 'conversation.execute', {'original': original, 'upstream': {}}, cancelled=True)['status'] == 'cancelling'
        release.set(); store.close()
        assert store.get('task', 'race')['status'] == 'cancelled'
    finally:
        release.set(); store.close()
