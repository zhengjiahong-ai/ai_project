"""Structured table extraction from HTML and images.

Extracts tables from raw HTML (<table> tags) or from images via VLM,
returning JSON arrays compatible with ``query_structured_data``.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

MAX_TABLE_ROWS = 500
MAX_TABLE_COLS = 50


# ── Public API ───────────────────────────────────────────────────────────────

def extract_html_tables(html: str, max_tables: int = 5) -> dict[str, Any]:
    """Extract structured table data from raw HTML.

    Returns ``{status, tables, tableCount, error}``.
    """
    if not html or not isinstance(html, str):
        return _error("HTML content is empty.")

    soup = BeautifulSoup(html, "lxml")
    table_elements = soup.find_all("table")[:max_tables]
    if not table_elements:
        return {"status": "success", "tables": [], "tableCount": 0, "error": ""}

    tables = []
    for table_el in table_elements:
        headers, rows = _parse_table(table_el)
        if not rows:
            continue
        caption_el = table_el.find("caption")
        tables.append({
            "caption": caption_el.get_text(strip=True)[:300] if caption_el else "",
            "headers": headers,
            "rows": rows[:MAX_TABLE_ROWS],
            "rowCount": len(rows[:MAX_TABLE_ROWS]),
            "colCount": len(headers),
        })

    return {
        "status": "success",
        "tables": tables[:max_tables],
        "tableCount": len(tables[:max_tables]),
        "error": "",
    }


def table_to_query_format(table: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert an extracted table to the format expected by query_structured_data.

    Each row becomes a dict with header keys.
    """
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    if not headers:
        return [dict(enumerate(row)) for row in rows]
    return [dict(zip(headers, row)) for row in rows]


# ── HTML table parsing ───────────────────────────────────────────────────────

def _parse_table(table_el: Any) -> tuple[list[str], list[list[str]]]:
    """Parse a BeautifulSoup <table> element into (headers, rows)."""
    headers: list[str] = []
    rows: list[list[str]] = []

    # Extract headers from <th> in thead or first row
    thead = table_el.find("thead")
    if thead:
        for th in thead.find_all("th"):
            headers.append(_clean_cell(th))
    if not headers:
        first_row = table_el.find("tr")
        if first_row:
            for th in first_row.find_all("th"):
                headers.append(_clean_cell(th))
            if not headers:
                for td in first_row.find_all("td"):
                    headers.append(_clean_cell(td))

    # Extract body rows
    tbody = table_el.find("tbody") or table_el
    for tr in tbody.find_all("tr"):
        cells = [_clean_cell(td) for td in tr.find_all(["td", "th"])]
        if cells and any(c for c in cells):
            rows.append(cells[:MAX_TABLE_COLS])

    # If headers were from first row, skip that row in body
    if headers and rows and _first_row_is_headers(table_el, headers):
        rows = rows[1:]

    if not headers and rows:
        headers = [f"col_{i}" for i in range(len(rows[0]))]

    return headers[:MAX_TABLE_COLS], rows


def _clean_cell(td: Any) -> str:
    return td.get_text(separator=" ", strip=True)[:500] if td else ""


def _first_row_is_headers(table_el: Any, headers: list[str]) -> bool:
    """Check if the first row of tbody duplicates what we already have as headers."""
    first_tr = table_el.find("tr")
    if not first_tr:
        return False
    cells = [_clean_cell(td) for td in first_tr.find_all(["td", "th"])]
    return len(cells) == len(headers) and all(
        a.lower().strip() == b.lower().strip() for a, b in zip(cells, headers)
    )


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "tables": [], "tableCount": 0, "error": message}
