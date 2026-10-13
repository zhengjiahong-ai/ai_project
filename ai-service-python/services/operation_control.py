"""Cooperative cancellation at capability and provider boundaries."""
from contextlib import contextmanager
from contextvars import ContextVar


class OperationCancelled(RuntimeError):
    pass


_cancel_probe = ContextVar("task_cancel_probe", default=None)


def check_cancelled():
    probe = _cancel_probe.get()
    if probe is not None and probe():
        raise OperationCancelled("operation_cancelled")


@contextmanager
def cancellation_scope(probe):
    token = _cancel_probe.set(probe)
    try:
        check_cancelled()
        yield
        check_cancelled()
    finally:
        _cancel_probe.reset(token)
