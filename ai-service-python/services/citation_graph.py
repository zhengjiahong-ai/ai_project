"""Citation graph traversal via Semantic Scholar API.

Provides BFS-based forward/backward citation traversal with local
SQLite caching.  Each paper node carries title, year, abstract, and
citation-count metadata.

Endpoints used (already covered by the Semantic Scholar API key):
  - GET /graph/v1/paper/{paper_id}/citations  (forward)
  - GET /graph/v1/paper/{paper_id}/references (backward)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from core.config import settings

# ── Constants ────────────────────────────────────────────────────────────────

CITATIONS_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
REFERENCES_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references"
PAPER_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}"

FIELDS = "title,year,abstract,citationCount,authors,externalIds,url,publicationVenue"
CITATION_FIELDS = "contexts,intents,isInfluential,paperId,title,year,abstract,citationCount,authors,externalIds,url"

REQUEST_TIMEOUT = (3.05, 15.0)
MAX_RETRIES = 2
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MIN_INTERVAL = 1.0
MAX_RETRY_AFTER = 30.0
USER_AGENT = "PixiuCitationGraph/1.0"

DEFAULT_DB_PATH = os.environ.get(
    "CITATION_GRAPH_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "citation_graph.sqlite3"),
)
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_PAPERS = 50
BATCH_LIMIT = 50  # per-request batch size for citations/references

# ── SQLite storage ───────────────────────────────────────────────────────────

_db_initialized = threading.Event()


def _ensure_db(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS citation_cache (
                source_id  TEXT NOT NULL,
                target_id  TEXT NOT NULL,
                relation   TEXT NOT NULL CHECK(relation IN ('cites','cited_by')),
                direction  TEXT NOT NULL CHECK(direction IN ('forward','backward')),
                paper_json TEXT NOT NULL DEFAULT '{}',
                cached_at  TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id, relation)
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cc_source ON citation_cache(source_id, relation)"
        )
    _db_initialized.set()
    return conn


# ── Rate-limited HTTP client ─────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL):
        self._lock = threading.Lock()
        self._min = min_interval
        self._next = 0.0

    def wait(self, retry_delay: float = 0.0) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(retry_delay, self._next - now, 0.0)
            if delay > 0:
                time.sleep(delay)
            self._next = time.monotonic() + self._min


def _api_key() -> str | None:
    key = settings.semantic_scholar_api_key.strip()
    return key or None


def _headers() -> dict[str, str]:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    key = _api_key()
    if key:
        h["x-api-key"] = key
    return h


def _get_json(url: str, params: dict[str, Any], limiter: _RateLimiter) -> dict[str, Any]:
    retry_delay = 0.0
    session = requests.Session()
    for attempt in range(MAX_RETRIES + 1):
        limiter.wait(retry_delay)
        resp = None
        try:
            resp = session.get(
                url, params=params, headers=_headers(),
                timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True,
            )
            status = int(resp.status_code)
            if 200 <= status < 300:
                return _read_json(resp)
            if status in RETRYABLE_STATUSES and attempt < MAX_RETRIES:
                ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after") or ""
                retry_delay = _parse_retry_after(ra) if ra.strip() else 0.5 * (2 ** attempt)
                if retry_delay <= MAX_RETRY_AFTER:
                    continue
            raise RuntimeError(f"Semantic Scholar HTTP {status}")
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("citation_api_unavailable")
        finally:
            if resp is not None:
                resp.close()
    raise RuntimeError("citation_api_retries_exhausted")


def _read_json(resp: requests.Response) -> dict[str, Any]:
    chunks: list[bytes] = []
    size = 0
    for chunk in resp.iter_content(chunk_size=65536):
        if chunk:
            size += len(chunk)
            if size > 2 * 1024 * 1024:
                raise RuntimeError("response_too_large")
            chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


def _parse_retry_after(raw: str) -> float:
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0.0, (dt - datetime.now(UTC)).total_seconds())
    except Exception:
        return 0.0


# ── Core traversal ───────────────────────────────────────────────────────────

def traverse_citation_graph(
    seed_paper_id: str,
    direction: str = "both",
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_papers: int = DEFAULT_MAX_PAPERS,
) -> dict[str, Any]:
    """BFS traversal of the citation graph from *seed_paper_id*.

    Parameters
    ----------
    seed_paper_id
        Semantic Scholar paper ID (40-char hex) or DOI.
    direction
        ``"forward"`` (who cited this), ``"backward"`` (references),
        or ``"both"`` (default).
    max_depth
        Maximum BFS depth (1-4, default 3).
    max_papers
        Maximum total papers to collect (1-200, default 50).

    Returns
    -------
    dict with ``status``, ``seed``, ``nodes``, ``edges``, ``error``.
    """
    if not seed_paper_id or not seed_paper_id.strip():
        return _error("seed_paper_id is required")
    max_depth = min(max(int(max_depth), 1), 4)
    max_papers = min(max(int(max_papers), 1), 200)

    db = _ensure_db()
    limiter = _RateLimiter()

    # Resolve seed to canonical S2 paper ID
    seed_meta = _fetch_paper_meta(seed_paper_id.strip(), db, limiter)
    if seed_meta is None:
        return _error(f"Could not resolve paper: {seed_paper_id}")
    canonical_id = seed_meta["paperId"]

    nodes: dict[str, dict[str, Any]] = {canonical_id: seed_meta}
    edges: list[dict[str, Any]] = []
    queue: list[tuple[str, int]] = [(canonical_id, 0)]
    visited: set[str] = {canonical_id}

    do_forward = direction in ("forward", "both")
    do_backward = direction in ("backward", "both")

    while queue and len(nodes) < max_papers:
        current_id, depth = queue.pop(0)
        if depth >= max_depth:
            continue

        if do_forward:
            citing = _fetch_citations(current_id, db, limiter, "forward")
            for paper in citing:
                pid = paper.get("paperId", "")
                if not pid or pid in visited:
                    continue
                if len(nodes) >= max_papers:
                    break
                visited.add(pid)
                nodes[pid] = paper
                edges.append({"from": pid, "to": current_id, "relation": "cites"})
                queue.append((pid, depth + 1))

        if do_backward:
            refs = _fetch_citations(current_id, db, limiter, "backward")
            for paper in refs:
                pid = paper.get("paperId", "")
                if not pid or pid in visited:
                    continue
                if len(nodes) >= max_papers:
                    break
                visited.add(pid)
                nodes[pid] = paper
                edges.append({"from": current_id, "to": pid, "relation": "cites"})
                queue.append((pid, depth + 1))

    return {
        "status": "success",
        "seed": {
            "paperId": canonical_id,
            "title": seed_meta.get("title", ""),
            "year": seed_meta.get("year"),
            "citationCount": seed_meta.get("citationCount"),
        },
        "nodes": [
            {
                "paperId": pid,
                "title": node.get("title", ""),
                "year": node.get("year"),
                "abstract": (node.get("abstract") or "")[:300],
                "citationCount": node.get("citationCount"),
                "authors": (node.get("authors") or [])[:5],
                "url": node.get("url", ""),
            }
            for pid, node in nodes.items()
        ],
        "edges": edges,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "error": "",
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_paper_meta(
    paper_id: str, db: sqlite3.Connection, limiter: _RateLimiter,
) -> dict[str, Any] | None:
    # Check cache
    for rel in ("cites", "cited_by"):
        rows = db.execute(
            "SELECT paper_json FROM citation_cache WHERE source_id=? AND relation=? LIMIT 1",
            (paper_id, rel),
        ).fetchall()
        if rows:
            try:
                return json.loads(rows[0][0])
            except (json.JSONDecodeError, TypeError):
                pass

    try:
        payload = _get_json(
            PAPER_ENDPOINT.format(paper_id=paper_id),
            {"fields": FIELDS}, limiter,
        )
        meta = _normalize_paper(payload)
        _cache_paper(paper_id, meta, db)
        return meta
    except Exception:
        return None


def _fetch_citations(
    paper_id: str, db: sqlite3.Connection, limiter: _RateLimiter,
    direction: str,
) -> list[dict[str, Any]]:
    cached = db.execute(
        "SELECT paper_json FROM citation_cache WHERE source_id=? AND relation=?",
        (paper_id, "cites" if direction == "forward" else "cited_by"),
    ).fetchall()
    if cached:
        results: list[dict[str, Any]] = []
        for row in cached[:BATCH_LIMIT]:
            try:
                results.append(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                pass
        if results:
            return results

    endpoint = CITATIONS_ENDPOINT if direction == "forward" else REFERENCES_ENDPOINT
    papers: list[dict[str, Any]] = []
    offset = 0
    while len(papers) < BATCH_LIMIT:
        try:
            payload = _get_json(
                endpoint.format(paper_id=paper_id),
                {"fields": CITATION_FIELDS, "limit": min(BATCH_LIMIT, 100), "offset": offset},
                limiter,
            )
        except Exception:
            break
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            cited = item.get("citedPaper") or item.get("citingPaper") or item
            if not isinstance(cited, dict):
                continue
            meta = _normalize_paper(cited)
            pid = meta.get("paperId", "")
            if not pid:
                continue
            papers.append(meta)
            _cache_paper(pid, meta, db)
            if len(papers) >= BATCH_LIMIT:
                break
        if len(data) < min(BATCH_LIMIT, 100):
            break
        offset += len(data)
    return papers[:BATCH_LIMIT]


def _normalize_paper(paper: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for a in (paper.get("authors") or [])[:10]:
        if isinstance(a, dict):
            name = a.get("name", "")
            if name:
                authors.append(str(name).strip())
    ext = paper.get("externalIds") or {}
    return {
        "paperId": str(paper.get("paperId") or "").strip(),
        "title": str(paper.get("title") or "").strip()[:500],
        "year": _safe_int(paper.get("year")),
        "abstract": str(paper.get("abstract") or "").strip()[:2000],
        "citationCount": _safe_int(paper.get("citationCount")),
        "authors": authors,
        "doi": str(ext.get("DOI") or "").strip()[:200],
        "url": str(paper.get("url") or "").strip()[:500],
        "venue": _venue_name(paper.get("publicationVenue")),
    }


def _cache_paper(paper_id: str, paper: dict[str, Any], db: sqlite3.Connection) -> None:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with db:
        db.execute(
            "INSERT OR REPLACE INTO citation_cache(source_id, target_id, relation, direction, paper_json, cached_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (paper_id, paper.get("paperId", paper_id), "cites", "forward", json.dumps(paper, ensure_ascii=False), now),
        )


def _safe_int(value: Any) -> int | None:
    try:
        v = int(value)
        return v if 1000 <= v <= 2100 else None
    except (TypeError, ValueError):
        return None


def _venue_name(venue: Any) -> str:
    if isinstance(venue, dict):
        return str(venue.get("name", "") or "").strip()[:200]
    if isinstance(venue, str):
        return venue.strip()[:200]
    return ""


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "seed": None, "nodes": [], "edges": [], "nodeCount": 0, "edgeCount": 0, "error": message}
