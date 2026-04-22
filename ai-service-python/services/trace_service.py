import copy
import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional


_TRACE_LOCK = threading.RLock()
_TRACE_STORE: Dict[str, Dict[str, Any]] = {}
_CURRENT_TRACE_ID: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)


def sanitize_text(value: Any, max_chars: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if api_key:
        text = text.replace(api_key, "[REDACTED]")

    text = re.sub(r"(DASHSCOPE_API_KEY\s*[:=]\s*)(\S+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def start_trace(
    task_type: str,
    request_meta: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    activate: bool = True,
    initial_status: str = "running",
) -> str:
    resolved_trace_id = str(trace_id or uuid.uuid4())
    trace = {
        "traceId": resolved_trace_id,
        "taskType": str(task_type or "unknown"),
        "status": str(initial_status or "running"),
        "startedAt": _utc_now(),
        "finishedAt": None,
        "durationMs": None,
        "requestMeta": _sanitize_meta(request_meta or {}),
        "responseMeta": {},
        "counters": {
            "llmCalls": 0,
            "retrievalCalls": 0,
        },
        "steps": [],
    }

    with _TRACE_LOCK:
        _TRACE_STORE[resolved_trace_id] = trace

    if activate:
        _CURRENT_TRACE_ID.set(resolved_trace_id)

    return resolved_trace_id


@contextmanager
def use_trace(trace_id: Optional[str]) -> Iterator[Optional[str]]:
    token = _CURRENT_TRACE_ID.set(trace_id)
    try:
        yield trace_id
    finally:
        _CURRENT_TRACE_ID.reset(token)


@contextmanager
def trace_step(
    name: str,
    *,
    input_size: Optional[int] = None,
    output_size: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Iterator[Dict[str, Any]]:
    start_time = time.perf_counter()
    step = {
        "name": str(name or "step"),
        "durationMs": 0,
        "status": "success",
        "inputSize": _normalize_size(input_size),
        "outputSize": _normalize_size(output_size),
        "error": "",
    }
    details = {
        "outputSize": step["outputSize"],
        "meta": _sanitize_meta(meta or {}),
    }

    try:
        yield details
    except Exception as error:
        step["status"] = "error"
        step["error"] = sanitize_text(error, max_chars=240)
        raise
    finally:
        step["durationMs"] = int((time.perf_counter() - start_time) * 1000)
        step["outputSize"] = _normalize_size(details.get("outputSize"))
        if details.get("meta"):
            step["meta"] = _sanitize_meta(details.get("meta"))
        _append_step(step)


def record_counter(name: str, delta: int = 1) -> None:
    trace_id = get_current_trace_id()
    if not trace_id:
        return

    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(trace_id)
        if trace is None:
            return
        counters = trace.setdefault("counters", {})
        counters[name] = int(counters.get(name, 0) or 0) + int(delta or 0)


def record_metric(name: str, value: Any) -> None:
    trace_id = get_current_trace_id()
    if not trace_id:
        return

    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(trace_id)
        if trace is None:
            return
        if isinstance(value, (int, float)):
            trace.setdefault("counters", {})[name] = value
        else:
            response_meta = trace.setdefault("responseMeta", {})
            response_meta[name] = _sanitize_meta(value)


def finalize_trace(
    status: str,
    error: Any = None,
    response_meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    trace_id = get_current_trace_id()
    if not trace_id:
        return None

    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(trace_id)
        if trace is None:
            return None

        finished_at = _utc_now()
        trace["status"] = str(status or trace.get("status") or "finished")
        trace["finishedAt"] = finished_at
        trace["durationMs"] = _duration_ms(trace.get("startedAt"), finished_at)
        if error:
            trace["error"] = sanitize_text(error, max_chars=240)

        if response_meta:
            merged = dict(trace.get("responseMeta") or {})
            merged.update(_sanitize_meta(response_meta))
            trace["responseMeta"] = merged

        snapshot = copy.deepcopy(trace)

    print(f"[trace] {json.dumps(snapshot, ensure_ascii=False)}")
    _CURRENT_TRACE_ID.set(None)
    return snapshot


def get_trace_snapshot(trace_id: str) -> Dict[str, Any]:
    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(str(trace_id or ""))
        if trace is None:
            raise KeyError(f"Trace not found: {trace_id}")
        return copy.deepcopy(trace)


def clear_traces() -> None:
    with _TRACE_LOCK:
        _TRACE_STORE.clear()
    _CURRENT_TRACE_ID.set(None)


def get_current_trace_id() -> Optional[str]:
    return _CURRENT_TRACE_ID.get()


def _append_step(step: Dict[str, Any]) -> None:
    trace_id = get_current_trace_id()
    if not trace_id:
        return

    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(trace_id)
        if trace is None:
            return
        trace.setdefault("steps", []).append(copy.deepcopy(step))


def _sanitize_meta(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            sanitized[str(key)] = _sanitize_meta(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_meta(item) for item in value[:12]]
    if isinstance(value, tuple):
        return [_sanitize_meta(item) for item in list(value)[:12]]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def _normalize_size(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_ms(started_at: Any, finished_at: Any) -> Optional[int]:
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((finished - started).total_seconds() * 1000))
