"""Cross-session research memory — remembers past findings and reuses knowledge.

Stores completed findings with embeddings for semantic retrieval.
New research sessions automatically recall relevant past discoveries.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = os.environ.get(
    "RESEARCH_MEMORY_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "research_memory.sqlite3"),
)


# ── SQLite ───────────────────────────────────────────────────────────────────

def _db(path: str = DEFAULT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS research_memory (
                memory_id   TEXT PRIMARY KEY,
                question    TEXT NOT NULL,
                finding     TEXT NOT NULL,
                verdict     TEXT NOT NULL DEFAULT '',
                evidence_summary TEXT NOT NULL DEFAULT '',
                source_ids  TEXT NOT NULL DEFAULT '[]',
                domain      TEXT NOT NULL DEFAULT '',
                embedding_json TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                outdated    INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rm_domain ON research_memory(domain)"
        )
    return conn


# ── Public API ───────────────────────────────────────────────────────────────

def store_finding(
    question: str,
    finding: dict[str, Any],
    evidence_items: list[dict[str, Any]] | None = None,
    domain: str = "",
) -> str:
    """Persist a research finding for future recall.

    Returns the ``memory_id``.
    """
    import uuid

    memory_id = f"mem-{uuid.uuid4().hex[:16]}"
    now = _utc_now()
    summary = finding.get("summary", "")[:500]
    verdict = finding.get("verdict", "")
    source_ids = json.dumps([e.get("sourceId", "") for e in (evidence_items or [])][:10], ensure_ascii=False)
    evidence_text = " ".join((e.get("text") or "")[:200] for e in (evidence_items or [])[:5])

    # Simple keyword embedding (bag-of-words vector, top 100 dims)
    embedding = _keyword_embedding(question + " " + summary)

    db = _db()
    with db:
        db.execute(
            """INSERT INTO research_memory
               (memory_id, question, finding, verdict, evidence_summary,
                source_ids, domain, embedding_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (memory_id, question[:300], summary, verdict, evidence_text[:500],
             source_ids, domain[:100], json.dumps(embedding), now),
        )
    return memory_id


def recall_relevant_past_research(
    question: str,
    domain: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """Retrieve top-k semantically similar past findings for *question*.

    Returns ``{status, memories, error}``.
    """
    if not question or not question.strip():
        return _error("Question cannot be empty.")

    query_embedding = _keyword_embedding(question)

    db = _db()
    rows = db.execute(
        "SELECT * FROM research_memory WHERE outdated=0 ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    # Cosine similarity against query
    scored = []
    for row in rows:
        try:
            emb = json.loads(row[7]) if isinstance(row[7], str) else row[7]
        except (json.JSONDecodeError, TypeError):
            emb = []
        sim = _cosine_similarity(query_embedding, emb)
        if sim > 0.1:
            scored.append((sim, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    memories = []
    for sim, row in scored[:limit]:
        memories.append({
            "memoryId": row[0],
            "question": row[1][:200],
            "finding": row[2][:300],
            "verdict": row[3],
            "evidenceSummary": row[4][:300],
            "domain": row[6],
            "similarity": round(sim, 3),
            "createdAt": row[8],
        })

    return {"status": "success", "question": question[:200], "memories": memories, "count": len(memories), "error": ""}


def mark_outdated(memory_id: str) -> bool:
    """Mark a previous finding as outdated (e.g., when new evidence contradicts it)."""
    db = _db()
    with db:
        db.execute("UPDATE research_memory SET outdated=1 WHERE memory_id=?", (memory_id,))
    return True


# ── Embedding helpers ────────────────────────────────────────────────────────

def _keyword_embedding(text: str) -> list[float]:
    """Simple bag-of-keywords embedding (no external model needed).

    Uses the top 100 most frequent alphanumeric tokens as dimensions.
    """
    import re
    words = re.findall(r'[a-zA-Z一-鿿]{2,}', text.lower())
    # Top-100 most discriminative words approach
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    # Normalize: TF-like vector over top 100 words
    sorted_words = sorted(freq, key=freq.get, reverse=True)[:100]
    total = max(sum(freq.values()), 1)
    return [freq.get(w, 0) / total for w in sorted_words]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    # Pad shorter vector
    if len(a) > len(b):
        b = b + [0.0] * (len(a) - len(b))
    elif len(b) > len(a):
        a = a + [0.0] * (len(b) - len(a))
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x**2 for x in a) ** 0.5
    norm_b = sum(y**2 for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "question": "", "memories": [], "count": 0, "error": message}
