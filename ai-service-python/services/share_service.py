"""
Share-token service for agent project reports (16-4).

Generates UUID4 tokens that grant read-only access to a project's latest
report for 7 days.  Tokens are stored in SQLite; expired tokens are cleaned
on generation.

Shares NEVER expose: PDF content, full evidence text, API keys, traces,
chat history, workbench notes, or user credentials.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, Optional


def _share_db_path() -> str:
    return os.environ.get(
        "PIXIU_SHARE_DB_PATH",
        os.path.join(os.path.dirname(__file__), "..", "data", "shares.sqlite3"),
    )


_SHARE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


class ShareService:
    """Manages read-only share tokens for agent project reports."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or _share_db_path()
        self._lock = threading.Lock()
        self._init_db()

    def create_share(self, project_id: str, report: str, project_title: str = "") -> Dict[str, Any]:
        """Create a share token for a project's latest report.

        Returns ``{token, expiresAt, url}``.  Cleans expired tokens first.
        """
        self._cleanup_expired()
        token = uuid.uuid4().hex
        expires_at = time.time() + _SHARE_TTL_SECONDS

        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO shares (token, project_id, report, project_title, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (token, project_id, report, project_title, time.time(), expires_at),
            )
            self._db.commit()

        return {
            "token": token,
            "expiresAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_at)),
            "url": f"/share/{token}",
        }

    def get_share(self, token: str) -> Optional[Dict[str, Any]]:
        """Retrieve a share by token; returns None if missing or expired."""
        with self._lock:
            row = self._db.execute(
                "SELECT project_id, report, project_title, expires_at FROM shares WHERE token = ?",
                (token,),
            ).fetchone()

        if row is None:
            return None

        project_id, report, project_title, expires_at = row
        if time.time() > float(expires_at):
            self._delete(token)
            return None

        return {
            "projectId": project_id,
            "projectTitle": project_title,
            "report": report,
            "expiresAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(expires_at))),
        }

    def _delete(self, token: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM shares WHERE token = ?", (token,))
            self._db.commit()

    def _cleanup_expired(self) -> int:
        now = time.time()
        with self._lock:
            cur = self._db.execute("DELETE FROM shares WHERE expires_at < ?", (now,))
            self._db.commit()
            return cur.rowcount

    def _init_db(self) -> None:
        if self._db_path != ":memory:":
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS shares ("
            "  token TEXT PRIMARY KEY,"
            "  project_id TEXT NOT NULL,"
            "  report TEXT NOT NULL,"
            "  project_title TEXT NOT NULL DEFAULT '',"
            "  created_at REAL NOT NULL,"
            "  expires_at REAL NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_shares_expires ON shares(expires_at)"
        )
        self._db.commit()


# ── module-level singleton ───────────────────────────────────────────────

_share_service: Optional[ShareService] = None


def get_share_service() -> ShareService:
    global _share_service
    if _share_service is None:
        _share_service = ShareService()
    return _share_service
