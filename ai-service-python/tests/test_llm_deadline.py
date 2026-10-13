from contextvars import ContextVar
from threading import BoundedSemaphore, Event
from unittest.mock import Mock

import pytest

from llm import deadline


def test_absolute_deadline_discards_and_closes_late_response(monkeypatch):
    release, finished = Event(), Event()
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(deadline, '_slots', slots)
    response = Mock()
    response.close.side_effect = finished.set

    def transport():
        assert release.wait(2)
        return response

    try:
        with pytest.raises(TimeoutError, match='absolute deadline'):
            deadline.call_with_deadline(transport, 0.03)
        # A timed-out request still occupies capacity until transport exits.
        with pytest.raises(RuntimeError, match='capacity'):
            deadline.call_with_deadline(lambda: None, 1)
    finally:
        release.set()
    assert finished.wait(1)
    response.close.assert_called_once()


def test_provider_result_exception_and_context_are_preserved():
    scope = ContextVar('test_scope', default='missing')
    token = scope.set('authorized')
    try:
        assert deadline.call_with_deadline(scope.get, 1) == 'authorized'
        error = ValueError('provider failed')
        def fail():
            raise error
        with pytest.raises(ValueError) as caught:
            deadline.call_with_deadline(fail, 1)
        assert caught.value is error
    finally:
        scope.reset(token)
