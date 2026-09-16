import copy
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_logger = logging.getLogger(__name__)


_TRACE_LOCK = threading.RLock()
_TRACE_STORE: dict[str, dict[str, Any]] = {}
_CURRENT_TRACE_ID: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
# 公开 trace 的步骤窗口：头尾各留一段。
# 旧实现只取前 12 条（_PUBLIC_TRACE_STEP_LIMIT），而批判分析单次要产生 20+ 步，
# 于是 limitations 轴、报告生成和主张对齐全被截掉 —— 而主张对齐恰是最贵的一步
# （实测 70.6s / 总 161.6s）。头尾双窗口既保住载荷上界，又保证收尾步骤永远可见。
_PUBLIC_TRACE_STEP_HEAD_LIMIT = 12
_PUBLIC_TRACE_STEP_TAIL_LIMIT = 12
_PUBLIC_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "headers",
    "api_key",
    "apikey",
    "key",
    "prompt",
    "systemprompt",
    "system_prompt",
    "systemmessage",
    "system_message",
    "papertext",
    "paper_text",
    "papercontent",
    "paper_content",
    "fulltext",
    "full_text",
    "documenttext",
    "document_text",
    "script",
    "scripttext",
    "script_text",
    "stdout",
    "stderr",
    "rawdata",
    "raw_data",
}


class TraceNotFoundError(Exception):
    pass


def sanitize_text(value: Any, max_chars: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""

    for env_name in ("DEEPSEEK_API_KEY",):
        api_key = os.environ.get(env_name)
        if api_key:
            text = text.replace(api_key, "[REDACTED]")

    text = re.sub(r"((?:DEEPSEEK|DASHSCOPE)_API_KEY\s*[:=]\s*)(\S+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def summarize_external_search_query(query: Any) -> dict[str, Any]:
    text = " ".join(str(query or "").strip().split())
    return {
        "queryHash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "queryLength": len(text),
        "tokenCount": len(text.split()) if text else 0,
    }


def start_trace(
    task_type: str,
    request_meta: dict[str, Any] | None = None,
    trace_id: str | None = None,
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
            "retryCount": 0,
            "truncationCount": 0,
            "estimatedInputTokens": 0,
            "estimatedOutputTokens": 0,
            "externalSearchCalls": 0,
            "externalSearchCacheHits": 0,
            "externalSearchFailures": 0,
            "externalEvidenceCount": 0,
            "externalSearchLatencyMs": 0,
            "externalSearchBudgetBlocks": 0,
            "codeExecutionCalls": 0,
            "codeExecutionFailures": 0,
            "codeExecutionOutputCount": 0,
            # Web search counters
            "webSearchCalls": 0,
            "webSearchResults": 0,
            "webSearchFailures": 0,
            "webSearchLatencyMs": 0,
            "webSearchBudgetBlocks": 0,
            "webSearchCacheHits": 0,
            # Web fetch counters
            "webFetchCalls": 0,
            "webFetchChars": 0,
            "webFetchFailures": 0,
            "webFetchBudgetBlocks": 0,
            "webFetchCacheHits": 0,
            "webFetchBytes": 0,
            # Agentic loop counters
            "agenticLoopIterations": 0,
            "queryRefinementCalls": 0,
        },
        "steps": [],
    }

    with _TRACE_LOCK:
        _TRACE_STORE[resolved_trace_id] = trace

    if activate:
        _CURRENT_TRACE_ID.set(resolved_trace_id)

    return resolved_trace_id


@contextmanager
def use_trace(trace_id: str | None) -> Iterator[str | None]:
    token = _CURRENT_TRACE_ID.set(trace_id)
    try:
        yield trace_id
    finally:
        _CURRENT_TRACE_ID.reset(token)


@contextmanager
def trace_step(
    name: str,
    *,
    input_size: int | None = None,
    output_size: int | None = None,
    meta: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
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
    response_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
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

    _logger.info(f"[trace] {json.dumps(snapshot, ensure_ascii=False)}")
    _CURRENT_TRACE_ID.set(None)
    return snapshot


def get_trace_snapshot(trace_id: str) -> dict[str, Any]:
    with _TRACE_LOCK:
        trace = _TRACE_STORE.get(str(trace_id or ""))
        if trace is None:
            raise KeyError(f"Trace not found: {trace_id}")
        return copy.deepcopy(trace)


def get_trace_summary(trace_id: str) -> dict[str, Any]:
    try:
        snapshot = get_trace_snapshot(trace_id)
    except KeyError as error:
        persisted = _load_persisted_trace_summary(trace_id)
        if persisted:
            return {"status": "success", "trace": persisted}
        raise TraceNotFoundError("Trace not found.") from error

    return {"status": "success", "trace": build_public_trace_summary(snapshot)}


def build_public_trace_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    trace = {
        "traceId": sanitize_text(snapshot.get("traceId"), max_chars=120),
        "taskType": sanitize_text(snapshot.get("taskType"), max_chars=80),
        "status": sanitize_text(snapshot.get("status"), max_chars=40),
        "startedAt": sanitize_text(snapshot.get("startedAt"), max_chars=40),
        "finishedAt": sanitize_text(snapshot.get("finishedAt"), max_chars=40),
        "durationMs": _normalize_size(snapshot.get("durationMs")),
        "requestMeta": _public_sanitize_meta(snapshot.get("requestMeta") or {}),
        "responseMeta": _public_sanitize_meta(snapshot.get("responseMeta") or {}),
        "counters": _public_sanitize_counters(snapshot.get("counters") or {}),
    }
    public_steps, steps_omitted = _public_trace_step_window(snapshot.get("steps") or [])
    trace["steps"] = public_steps
    # 显式回报被省略的条数，不让消费方把截断后的窗口误读成"就这几步"。
    trace["stepsOmitted"] = steps_omitted
    if snapshot.get("error"):
        trace["error"] = sanitize_text(snapshot.get("error"), max_chars=240)
    return trace


def _load_persisted_trace_summary(trace_id: str) -> dict[str, Any] | None:
    try:
        from services import research_task_service
    except Exception:
        research_task_service = None

    if research_task_service is not None:
        try:
            summary = research_task_service.get_persisted_trace_summary(trace_id)
            if summary:
                return summary
        except Exception:
            pass

    try:
        from services import agent_project_service
    except Exception:
        return None

    try:
        return agent_project_service.get_persisted_trace_summary(trace_id)
    except Exception:
        return None


def clear_traces() -> None:
    with _TRACE_LOCK:
        _TRACE_STORE.clear()
    _CURRENT_TRACE_ID.set(None)


def get_current_trace_id() -> str | None:
    return _CURRENT_TRACE_ID.get()


def _append_step(step: dict[str, Any]) -> None:
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


def _public_sanitize_meta(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_public_key(key_text):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = _public_sanitize_meta(item)
        return sanitized
    if isinstance(value, list):
        return [_public_sanitize_meta(item) for item in value[:12]]
    if isinstance(value, tuple):
        return [_public_sanitize_meta(item) for item in list(value)[:12]]
    if isinstance(value, str):
        return sanitize_text(value, max_chars=240)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_text(value, max_chars=120)


def _public_sanitize_counters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    counters = {}
    for key, item in value.items():
        key_text = sanitize_text(key, max_chars=80)
        if not key_text:
            continue
        if isinstance(item, (int, float)):
            counters[key_text] = item
        else:
            counters[key_text] = _public_sanitize_meta(item)
    return counters


def _public_sanitize_step(raw_step: dict[str, Any]) -> dict[str, Any]:
    step = {
        "name": sanitize_text(raw_step.get("name"), max_chars=120),
        "durationMs": _normalize_size(raw_step.get("durationMs")) or 0,
        "status": sanitize_text(raw_step.get("status"), max_chars=40) or "success",
        "inputSize": _normalize_size(raw_step.get("inputSize")),
        "outputSize": _normalize_size(raw_step.get("outputSize")),
        "error": sanitize_text(raw_step.get("error"), max_chars=240),
    }
    if raw_step.get("meta"):
        step["meta"] = _public_sanitize_meta(raw_step.get("meta"))
    return step


def _public_trace_step_window(value: Any) -> tuple[list[dict[str, Any]], int]:
    """按头尾窗口选取步骤，并回报被省略的条数。

    写入侧（_append_step）故意不设上限，否则长任务会在运行中静默丢步骤；
    截断只发生在公开输出这一侧，而且必须可观测。
    """
    if not isinstance(value, list):
        return [], 0

    raw_steps = [step for step in value if isinstance(step, dict)]
    total = len(raw_steps)
    window = _PUBLIC_TRACE_STEP_HEAD_LIMIT + _PUBLIC_TRACE_STEP_TAIL_LIMIT
    if total <= window:
        selected = raw_steps
    else:
        selected = [
            *raw_steps[:_PUBLIC_TRACE_STEP_HEAD_LIMIT],
            *raw_steps[-_PUBLIC_TRACE_STEP_TAIL_LIMIT:],
        ]
    return [_public_sanitize_step(step) for step in selected], total - len(selected)


def _is_sensitive_public_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9_]+", "", str(key or "").lower())
    return (
        normalized in _PUBLIC_SENSITIVE_KEYS
        or normalized.endswith("apikey")
        or normalized.endswith("api_key")
        or ("paper" in normalized and ("text" in normalized or "content" in normalized or "body" in normalized))
        or ("full" in normalized and "text" in normalized)
    )


def _normalize_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _duration_ms(started_at: Any, finished_at: Any) -> int | None:
    try:
        started = datetime.fromisoformat(str(started_at))
        finished = datetime.fromisoformat(str(finished_at))
    except ValueError:
        return None
    return max(0, int((finished - started).total_seconds() * 1000))
