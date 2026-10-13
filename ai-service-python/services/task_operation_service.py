"""Durable request receipts. A receipt is never automatically re-executed.

SQLite owns request identity and results, independently of HTTP connections.
One uvicorn process owns execution (the repository's production configuration).
After a process restart, unfinished receipts are interrupted, not repeated: a
provider may have accepted an in-flight call whose response was never recorded.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from services.operation_control import OperationCancelled, cancellation_scope

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
KINDS = {"learning.start", "learning.action", "research.start", "conversation.execute"}
logger = logging.getLogger(__name__)


class OperationConflict(ValueError):
    pass


class OperationNotFound(KeyError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class OperationStore:
    def __init__(self, path, handler, workers=2):
        self.path = Path(path)
        self.handler = handler
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="task-operation")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS task_operations (
                task_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                result TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(task_id, request_id))""")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _view(self, row):
        if row is None:
            raise OperationNotFound("请求不存在")
        return {"taskId": row["task_id"], "requestId": row["request_id"], "kind": row["kind"],
                "status": row["status"], "input": json.loads(row["payload"]),
                "result": json.loads(row["result"]) if row["result"] else None,
                "error": row["error"] or "", "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def get(self, task_id, request_id):
        with closing(self._connect()) as db:
            return self._view(db.execute("SELECT * FROM task_operations WHERE task_id=? AND request_id=?",
                                         (task_id, request_id)).fetchone())

    def list(self, task_id):
        with closing(self._connect()) as db:
            return [self._view(row) for row in db.execute(
                "SELECT * FROM task_operations WHERE task_id=? ORDER BY created_at", (task_id,))]

    def submit(self, task_id, request_id, kind, payload, *, cancelled=False):
        if not isinstance(task_id, str) or not task_id or len(task_id) > 255:
            raise ValueError("任务 ID 无效")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise ValueError("请求 ID 无效")
        if kind not in KINDS or not isinstance(payload, dict):
            raise ValueError("请求类型无效")
        serialized = _canonical(payload)
        fingerprint = hashlib.sha256((kind + serialized).encode()).hexdigest()
        created = False
        # Reserve before scheduling. Duplicate concurrent submissions read the same receipt.
        with self.lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM task_operations WHERE task_id=? AND request_id=?",
                             (task_id, request_id)).fetchone()
            if row:
                existing_payload = json.loads(row["payload"])
                same_intent = row['kind'] == kind and _canonical(existing_payload.get('original', existing_payload)) == _canonical(payload.get('original', payload))
                if row["fingerprint"] != fingerprint and not (cancelled and same_intent):
                    raise OperationConflict("同一请求 ID 不能用于不同内容")
            else:
                active = db.execute("SELECT 1 FROM task_operations WHERE task_id=? AND status IN ('queued','running','cancelling')",
                                    (task_id,)).fetchone()
                if active and not cancelled:
                    raise OperationConflict("当前任务仍有请求正在执行，请核对状态后继续")
                timestamp = _now()
                db.execute("INSERT INTO task_operations VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (task_id, request_id, fingerprint, kind, "cancelled" if cancelled else "queued", serialized, None, None, timestamp, timestamp))
                created = not cancelled
            db.commit()
        if created:
            self.executor.submit(self._run, task_id, request_id)
        return self.cancel(task_id, request_id) if cancelled else self.get(task_id, request_id)

    def _set(self, task_id, request_id, status, result=None, error="", expected=None):
        with self.lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM task_operations WHERE task_id=? AND request_id=?",
                             (task_id, request_id)).fetchone()
            if row is None:
                raise OperationNotFound(request_id)
            if expected is not None and row["status"] not in expected:
                return False
            db.execute("UPDATE task_operations SET status=?,result=?,error=?,updated_at=? WHERE task_id=? AND request_id=?",
                       (status, _canonical(result) if result is not None else row["result"], error, _now(), task_id, request_id))
            db.commit()
            return True

    def _run(self, task_id, request_id):
        if not self._set(task_id, request_id, "running", expected={"queued"}):
            return
        probe = lambda: self.get(task_id, request_id)["status"] == "cancelling"
        result = None
        try:
            with cancellation_scope(probe):
                receipt = self.get(task_id, request_id)
                payload = dict(receipt['input'])
                payload['workspaceTaskId'] = task_id
                result = self.handler(receipt["kind"], payload)
            if not self._set(task_id, request_id, "succeeded", result=result, expected={"running"}):
                self._stop_created_research(receipt["kind"], result)
                self._set(task_id, request_id, "cancelled", expected={"cancelling"})
        except OperationCancelled:
            self._stop_created_research(self.get(task_id, request_id)["kind"], result)
            self._set(task_id, request_id, "cancelled", expected={"running", "cancelling"})
        except Exception:
            logger.exception("Task operation failed: task=%s request=%s", task_id, request_id)
            # Do not leak provider credentials, prompts or stack traces in a public receipt.
            if probe():
                self._set(task_id, request_id, "cancelled", expected={"cancelling"})
            else:
                self._set(task_id, request_id, "failed", error="处理未完成，原问题和材料已保留，可重试。", expected={"running"})

    def _stop_created_research(self, kind, result):
        if kind != "research.start" or not result:
            return
        from services.research_task_service import cancel_research_task, get_research_task
        research_id = result["task"]["taskId"]
        cancel_research_task(research_id)
        while get_research_task(research_id)["task"]["status"] == "cancelling":
            time.sleep(0.05)

    def cancel(self, task_id, request_id):
        with self.lock:
            current = self.get(task_id, request_id)
            if current["status"] == "queued":
                self._set(task_id, request_id, "cancelled", expected={"queued"})
            elif current["status"] == "running":
                self._set(task_id, request_id, "cancelling", expected={"running"})
        return self.get(task_id, request_id)

    def recover_after_restart(self):
        # Called once by the single-process service lifespan, before accepting HTTP traffic.
        with self.lock, closing(self._connect()) as db:
            cancelling = {(row["task_id"], row["request_id"]) for row in db.execute(
                "SELECT task_id,request_id FROM task_operations WHERE status='cancelling'")}
            db.execute("UPDATE task_operations SET status='interrupted', error=?, updated_at=? "
                       "WHERE status IN ('queued','running','cancelling')",
                       ("服务已重启，请求执行结果未确认。不会自动重复模型调用；已保存活动可继续。", _now()))
            db.commit()
        # Recover the crash window between durable research creation and receipt completion.
        with closing(self._connect()) as db:
            candidates = list(db.execute("SELECT * FROM task_operations WHERE kind='research.start' AND status='interrupted'"))
        for row in candidates:
            payload = json.loads(row["payload"])
            key = payload.get("upstream", {}).get("operationKey")
            if not key:
                continue
            from services.research_task_service import ResearchTaskNotFoundError, get_research_task, cancel_research_task
            try:
                result = get_research_task(str(uuid.uuid5(uuid.NAMESPACE_URL, "pixiu:research:" + key)))
            except ResearchTaskNotFoundError:
                continue
            if (row["task_id"], row["request_id"]) in cancelling:
                result = cancel_research_task(result["task"]["taskId"])
                self._set(row["task_id"], row["request_id"], "cancelled", result=result, expected={"interrupted"})
            else:
                from services.capability_result_service import adapt_capability_result
                payload['workspaceTaskId'] = row['task_id']
                result = adapt_capability_result('research.start', payload, result)
                self._set(row["task_id"], row["request_id"], "succeeded", result=result, expected={"interrupted"})

    def close(self):
        self.executor.shutdown(wait=True)


def execute_capability(kind, payload):
    from services.capability_result_service import adapt_capability_result
    result = _execute_native_capability(kind, payload)
    return adapt_capability_result(kind, payload, result)


def _execute_native_capability(kind, payload):
    if kind == "conversation.execute":
        from schemas.conversation import ConversationCapabilityRequest
        from services.conversation_capability_service import execute_conversation
        return execute_conversation(ConversationCapabilityRequest.model_validate(payload["upstream"]))
    if kind == "learning.start":
        from schemas.adaptive_learning import AdaptiveLearningStartRequest
        from services.adaptive_learning_service import start_activity
        return start_activity(AdaptiveLearningStartRequest.model_validate(payload["upstream"]))
    if kind == "learning.action":
        from schemas.adaptive_learning import AdaptiveLearningActionRequest
        from services.adaptive_learning_service import transition_activity
        return transition_activity(AdaptiveLearningActionRequest.model_validate(payload["upstream"]))
    if kind != "research.start":
        raise ValueError("请求类型无效")
    from schemas.requests import ResearchTaskCreateRequest
    from services.research_task_service import create_research_task
    return create_research_task(ResearchTaskCreateRequest.model_validate(payload["upstream"]))


_store = None
_store_lock = threading.Lock()


def get_operation_store():
    global _store
    with _store_lock:
        if _store is None:
            path = os.environ.get("TASK_OPERATION_DB_PATH") or str(Path(os.environ.get("RESEARCH_TASK_DB_PATH", "data/research_tasks.sqlite3")).with_name("task_operations.sqlite3"))
            _store = OperationStore(path, execute_capability)
        return _store
