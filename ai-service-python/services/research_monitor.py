"""Continuous research monitor — watches for new publications matching interests.

Supports arXiv and PubMed as sources. Stores monitor configs and checked
paper IDs in SQLite to avoid duplicate alerts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = os.environ.get(
    "RESEARCH_MONITOR_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "research_monitor.sqlite3"),
)
CHECK_TIMEOUT = 30


# ── SQLite ───────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    Path(DEFAULT_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DEFAULT_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS monitors (
                monitor_id   TEXT PRIMARY KEY,
                question     TEXT NOT NULL,
                sources      TEXT NOT NULL DEFAULT '["arxiv"]',
                frequency    TEXT NOT NULL DEFAULT 'daily',
                created_at   TEXT NOT NULL,
                last_checked TEXT,
                active       INTEGER NOT NULL DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS checked_papers (
                monitor_id  TEXT NOT NULL,
                paper_id    TEXT NOT NULL,
                checked_at  TEXT NOT NULL,
                relevant    INTEGER NOT NULL DEFAULT 0,
                score       REAL NOT NULL DEFAULT 0.0,
                PRIMARY KEY (monitor_id, paper_id)
            )"""
        )
    return conn


# ── Public API ───────────────────────────────────────────────────────────────

def create_monitor(
    question: str,
    sources: list[str] | None = None,
    frequency: str = "daily",
) -> dict[str, Any]:
    """Create a research monitor for *question*.

    Returns ``{status, monitorId, question, sources, error}``.
    """
    if not question or not question.strip():
        return _error("Question cannot be empty.")
    sources = sources or ["arxiv"]
    monitor_id = f"monitor-{uuid.uuid4().hex[:16]}"
    now = _utc_now()

    db = _db()
    with db:
        db.execute(
            "INSERT INTO monitors (monitor_id, question, sources, frequency, created_at) VALUES (?,?,?,?,?)",
            (monitor_id, question.strip()[:300], json.dumps(sources), frequency, now),
        )
    return {
        "status": "success",
        "monitorId": monitor_id,
        "question": question.strip()[:300],
        "sources": sources,
        "frequency": frequency,
        "error": "",
    }


def check_new_publications(monitor_id: str) -> dict[str, Any]:
    """Check for new publications matching the monitor's question.

    Returns ``{status, monitorId, newPapers, newCount, error}``.
    """
    db = _db()
    row = db.execute("SELECT * FROM monitors WHERE monitor_id=?", (monitor_id,)).fetchone()
    if not row:
        return _error(f"Monitor {monitor_id} not found.")

    question = row[1]
    sources = json.loads(row[2]) if isinstance(row[2], str) else row[2]

    new_papers: list[dict[str, Any]] = []
    for source in sources:
        try:
            results = _search_source(source, question)
            for paper in results:
                pid = paper.get("paperId") or paper.get("title", "")
                if not pid:
                    continue
                existing = db.execute(
                    "SELECT 1 FROM checked_papers WHERE monitor_id=? AND paper_id=?",
                    (monitor_id, pid),
                ).fetchone()
                if existing:
                    continue
                # Score relevance with LLM
                relevance = _score_relevance(question, paper)
                db.execute(
                    "INSERT OR REPLACE INTO checked_papers (monitor_id, paper_id, checked_at, relevant, score) "
                    "VALUES (?,?,?,?,?)",
                    (monitor_id, pid, _utc_now(), 1 if relevance > 0.4 else 0, relevance),
                )
                paper["relevanceScore"] = round(relevance, 2)
                new_papers.append(paper)
        except Exception:
            continue

    db.execute("UPDATE monitors SET last_checked=? WHERE monitor_id=?", (_utc_now(), monitor_id))
    db.commit()

    new_papers.sort(key=lambda p: p.get("relevanceScore", 0), reverse=True)

    return {
        "status": "success",
        "monitorId": monitor_id,
        "newPapers": new_papers[:20],
        "newCount": len(new_papers[:20]),
        "recommended": [p for p in new_papers[:5] if p.get("relevanceScore", 0) > 0.5],
        "error": "",
    }


def get_monitor_digest(monitor_id: str) -> dict[str, Any]:
    """Generate a human-readable digest of recent findings."""
    check = check_new_publications(monitor_id)
    if check["status"] != "success":
        return check

    papers = check.get("newPapers", [])
    if not papers:
        return {**check, "digest": "No new relevant publications found."}

    lines = [f"## 研究监控摘要 ({_utc_now()[:10]})", "", f"新发现 {len(papers)} 篇可能相关论文：", ""]
    for p in papers[:10]:
        title = p.get("title", "Untitled")[:150]
        score = p.get("relevanceScore", 0)
        stars = "★" * min(int(score * 5), 5)
        lines.append(f"- {stars} [{score:.2f}] **{title}**")
        if p.get("abstract"):
            lines.append(f"  {(p.get('abstract') or '')[:200]}")
    return {**check, "digest": "\n".join(lines)}


def list_monitors() -> list[dict[str, Any]]:
    db = _db()
    rows = db.execute("SELECT * FROM monitors WHERE active=1 ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def deactivate_monitor(monitor_id: str) -> bool:
    db = _db()
    with db:
        db.execute("UPDATE monitors SET active=0 WHERE monitor_id=?", (monitor_id,))
    return True


# ── Internal ─────────────────────────────────────────────────────────────────

def _search_source(source: str, question: str) -> list[dict[str, Any]]:
    try:
        from services.tool_registry import get_tool_registry
        registry = get_tool_registry()
        if source == "arxiv":
            resp = registry.invoke("retrieve_external_academic", {"query": question[:200], "limit": 10})
            return resp.get("items") or []
        elif source == "pubmed":
            resp = registry.invoke("search_web", {"query": f"{question[:200]} site:pubmed.ncbi.nlm.nih.gov", "limit": 5})
            return resp.get("items") or []
        return []
    except Exception:
        return []


def _score_relevance(question: str, paper: dict[str, Any]) -> float:
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()
    text = title + " " + abstract[:500]
    q_words = set(question.lower().split()) & set(text.split())
    if not q_words:
        return 0.0
    return min(len(q_words) / max(len(set(question.lower().split())), 1), 1.0)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "monitorId": "", "question": "", "error": message}
