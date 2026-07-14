from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

MAX_DATA_BYTES: int = 524288  # 512 KiB
MAX_QUERY_LENGTH: int = 4096
MAX_RESULT_ROWS: int = 1000
TABLE_NAME: str = "data"

_SELECT_PATTERN = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_NON_SELECT_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REINDEX|RELEASE|SAVEPOINT|VACUUM)\b",
    re.IGNORECASE,
)


# ── Validation ───────────────────────────────────────────────────────────────

def _validate_query(query: str) -> str | None:
    """Return an error message if *query* is unsafe, or ``None`` if ok."""
    stripped = query.strip()
    if not stripped:
        return "Query cannot be empty."
    if len(query) > MAX_QUERY_LENGTH:
        return f"Query length {len(query)} exceeds maximum {MAX_QUERY_LENGTH} characters."
    if not _SELECT_PATTERN.match(stripped):
        return "Only SELECT statements are allowed."
    # Reject multi-statement injection (semicolon followed by another statement).
    # Split on semicolons outside of single quotes (simplistic but effective
    # when combined with the SELECT-only check).
    parts = _split_on_top_level_semicolons(stripped)
    if len(parts) > 1:
        return "Multiple SQL statements are not allowed."
    # Reject non-SELECT keywords that could appear after the initial SELECT.
    if _NON_SELECT_PATTERN.search(stripped):
        return "Write operations (INSERT/UPDATE/DELETE/DROP/etc.) are not allowed."
    return None


def _split_on_top_level_semicolons(sql: str) -> list[str]:
    """Split *sql* on semicolons that are not inside single-quoted strings."""
    parts: list[str] = []
    current: list[str] = []
    in_quote = False
    for ch in sql:
        if ch == "'":
            in_quote = not in_quote
        elif ch == ";" and not in_quote:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


# ── Core Query Function ──────────────────────────────────────────────────────

def query_structured_data(query: str, data: str) -> dict[str, Any]:
    """Execute a SQL SELECT *query* against JSON *data* in an in-memory sandbox.

    Parameters
    ----------
    query
        A SQL SELECT statement (required).  Only SELECT is allowed;
        all write operations and multiple statements are rejected.
    data
        A JSON-encoded array of objects, e.g.
        ``'[{"name":"Alice","age":30},{"name":"Bob","age":25}]'``.

    Returns
    -------
    dict
        ``status``   – ``"success"`` or ``"error"``.
        ``rows``     – list of result dicts (empty on error).
        ``rowCount`` – number of rows returned (0 on error).
        ``error``    – human-readable error description (empty on success).
    """
    # ── Validate data ────────────────────────────────────────────────────
    if not data or not data.strip():
        return _error("Data cannot be empty.")
    if len(data) > MAX_DATA_BYTES:
        return _error(f"Data length {len(data)} exceeds maximum {MAX_DATA_BYTES} bytes.")

    try:
        rows_input: list[dict[str, Any]] = json.loads(data)
    except json.JSONDecodeError as exc:
        return _error(f"Invalid JSON data: {exc}")
    if not isinstance(rows_input, list):
        return _error("Data must be a JSON array of objects.")
    if not rows_input:
        return {"status": "success", "rows": [], "rowCount": 0, "error": ""}

    # ── Validate query ───────────────────────────────────────────────────
    query_err = _validate_query(query)
    if query_err is not None:
        return _error(query_err)

    # ── Infer column names ───────────────────────────────────────────────
    columns = _infer_columns(rows_input)
    if not columns:
        return _error("No columns found in data rows.")

    # ── Execute in in-memory SQLite ──────────────────────────────────────
    try:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Build column definitions (all TEXT — SQLite is flexible).
        col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
        cur.execute(f'CREATE TABLE "{TABLE_NAME}" ({col_defs})')

        # Insert rows.
        placeholders = ", ".join("?" for _ in columns)
        quoted_cols = ", ".join(f'"{c}"' for c in columns)
        insert_sql = f'INSERT INTO "{TABLE_NAME}" ({quoted_cols}) VALUES ({placeholders})'
        for row in rows_input:
            values = [_cell_value(row.get(c)) for c in columns]
            cur.execute(insert_sql, values)

        conn.commit()

        # Execute user query against the "data" table.
        cur.execute(query)
        result_rows = cur.fetchmany(MAX_RESULT_ROWS + 1)
        if len(result_rows) > MAX_RESULT_ROWS:
            return _error(f"Result exceeds maximum of {MAX_RESULT_ROWS} rows.")

        conn.close()

        return {
            "status": "success",
            "rows": [dict(r) for r in result_rows],
            "rowCount": len(result_rows),
            "error": "",
        }

    except sqlite3.Error as exc:
        return _error(f"SQL error: {exc}")
    except Exception as exc:
        return _error(f"Query execution failed: {exc}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _infer_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Return the union of all keys across *rows*, preserving first-seen order."""
    seen: set[str] = set()
    columns: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
    return columns


def _cell_value(value: Any) -> str:
    """Convert a cell value to a string for SQLite TEXT storage.

    Nested dicts / lists are serialized to JSON so they round-trip.
    ``None`` is stored as an empty string.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "rows": [], "rowCount": 0, "error": message}
