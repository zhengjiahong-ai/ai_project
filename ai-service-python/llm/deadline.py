"""Bound caller wait even when an HTTP server keeps sending heartbeats."""
from concurrent.futures import Future, InvalidStateError, TimeoutError as FutureTimeout
from contextvars import copy_context
from threading import BoundedSemaphore, Thread
from time import monotonic
from typing import Callable, TypeVar

T = TypeVar('T')
# Timed-out transport threads may finish later. Bound their number as well as
# the caller's wait, without letting interpreter shutdown wait for a provider.
_slots = BoundedSemaphore(8)


def call_with_deadline(call: Callable[[], T], seconds: float) -> T:
    if seconds <= 0:
        raise ValueError('Deadline must be positive')
    expires = monotonic() + seconds
    slots = _slots
    if not slots.acquire(blocking=False):
        raise RuntimeError('LLM transport capacity is occupied by outstanding requests')
    future: Future[T] = Future()
    context = copy_context()

    def worker():
        try:
            value = context.run(call)
            try:
                future.set_result(value)
            except InvalidStateError:
                # The caller already timed out. No result can reach its ledger.
                close = getattr(value, 'close', None)
                if callable(close):
                    close()
        except BaseException as error:
            try:
                future.set_exception(error)
            except InvalidStateError:
                pass
        finally:
            slots.release()

    try:
        Thread(target=worker, name='llm-transport', daemon=True).start()
    except BaseException:
        slots.release()
        raise
    try:
        return future.result(timeout=max(0, expires - monotonic()))
    except FutureTimeout as error:
        if not future.cancel() and future.done():
            # Completion raced with the deadline: discard rather than returning
            # a response after the caller's time budget has expired.
            try:
                value = future.result()
                close = getattr(value, 'close', None)
                if callable(close):
                    close()
            except BaseException:
                pass
        raise TimeoutError('LLM request timed out at its absolute deadline') from error
