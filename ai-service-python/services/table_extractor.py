"""Structured table extraction from HTML, GROBID TEI, and images (16-1 enhanced).

Extracts tables from:
* raw HTML ``<table>`` tags,
* GROBID TEI ``<figure type="table">`` elements,
* fallback: PDF.js text-line clustering with column-alignment detection.

Returns JSON arrays compatible with ``query_structured_data``.
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


def extract_tei_tables(tei_path: str, max_tables: int = 5) -> dict[str, Any]:
    """Extract structured table data from a GROBID TEI XML file (16-1).

    GROBID wraps tables in ``<figure type="table">...</figure>`` elements.
    This function reads the TEI document, finds those figures, and extracts
    rows from the contained ``<row>`` / ``<cell>`` elements.
    """
    try:
        with open(tei_path, "r", encoding="utf-8") as handle:
            soup = BeautifulSoup(handle, "xml")
    except Exception as exc:
        return _error(f"Cannot read TEI file: {exc}")

    table_figures = soup.find_all("figure", {"type": "table"})[:max_tables]
    if not table_figures:
        return {"status": "success", "tables": [], "tableCount": 0, "error": ""}

    tables: list[dict[str, Any]] = []
    for fig in table_figures:
        header_row = fig.find("row", {"role": "header"})
        headers: list[str] = []
        if header_row:
            headers = [_clean_cell(cell) for cell in header_row.find_all("cell")]

        body_rows: list[list[str]] = []
        for row in fig.find_all("row"):
            if header_row and row is header_row:
                continue
            cells = [_clean_cell(cell) for cell in row.find_all("cell")]
            if cells and any(c for c in cells):
                body_rows.append(cells)

        if not body_rows:
            continue

        if not headers:
            headers = [f"col_{i}" for i in range(len(body_rows[0]))]

        caption = ""
        fig_desc = fig.find("figDesc") or fig.find("head")
        if fig_desc:
            caption = fig_desc.get_text(strip=True)[:300]

        tables.append({
            "caption": caption,
            "headers": headers[:MAX_TABLE_COLS],
            "rows": body_rows[:MAX_TABLE_ROWS],
            "rowCount": len(body_rows[:MAX_TABLE_ROWS]),
            "colCount": len(headers[:MAX_TABLE_COLS]),
            "source": "grobid-tei",
        })

    return {
        "status": "success",
        "tables": tables[:max_tables],
        "tableCount": len(tables[:max_tables]),
        "error": "",
    }


def extract_tables_from_pdf_text_lines(
    lines: list[dict[str, Any]],
    page_width: float = 612.0,
) -> dict[str, Any]:
    """Fallback table detection from PDF text-line data (16-1).

    Uses text-line clustering and column-alignment heuristics to detect
    tabular content when GROBID doesn't identify a ``<figure type="table">``.
    Best-effort; results may be incomplete for complex layouts.
    """
    if not lines:
        return {"status": "success", "tables": [], "tableCount": 0, "error": ""}

    # Cluster lines by y-position proximity → candidate table rows.
    sorted_lines = sorted(lines, key=lambda ln: (ln.get("pageIndex", 0), ln.get("y", 0)))
    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = []
    prev_center_y: float | None = None
    ROW_GAP = 8.0

    for ln in sorted_lines:
        y = float(ln.get("y", 0))
        h = float(ln.get("height", 10))
        center_y = y + h / 2
        if prev_center_y is not None and abs(center_y - prev_center_y) > ROW_GAP:
            if current_row:
                rows.append(current_row)
            current_row = []
        current_row.append(ln)
        prev_center_y = center_y
    if current_row:
        rows.append(current_row)

    # Detect columns: group by x-position clusters.
    candidate_tables: list[dict[str, Any]] = []
    TABLE_MIN_ROWS = 3
    TABLE_MIN_COLS = 2

    for start_idx in range(len(rows)):
        for end_idx in range(start_idx + TABLE_MIN_ROWS, min(start_idx + 60, len(rows))):
            block = rows[start_idx:end_idx]
            # Collect all x positions.
            all_x: list[float] = []
            for row in block:
                for ln in row:
                    all_x.append(float(ln.get("x", 0)))
            if len(all_x) < TABLE_MIN_ROWS * TABLE_MIN_COLS:
                continue

            # Cluster x positions into columns.
            cols = _cluster_values(sorted(all_x), tolerance=18.0)
            if len(cols) < TABLE_MIN_COLS:
                continue

            # Build table rows from aligned text.
            table_rows: list[list[str]] = []
            for row in block:
                row_cells: list[str] = []
                for cx in cols:
                    # Find the line whose x is closest to this column center.
                    best = min(row, key=lambda ln: abs(float(ln.get("x", 0)) - cx))
                    if abs(float(best.get("x", 0)) - cx) < 40:
                        row_cells.append(str(best.get("text", ""))[:200])
                    else:
                        row_cells.append("")
                if row_cells:
                    table_rows.append(row_cells)

            if len(table_rows) >= TABLE_MIN_ROWS:
                headers = table_rows[0] if table_rows else []
                candidate_tables.append({
                    "caption": "",
                    "headers": headers[:MAX_TABLE_COLS],
                    "rows": table_rows[1:][:MAX_TABLE_ROWS],
                    "rowCount": len(table_rows[1:][:MAX_TABLE_ROWS]),
                    "colCount": len(headers[:MAX_TABLE_COLS]),
                    "source": "pdf-text-lines",
                })
                break
        if candidate_tables:
            break

    return {
        "status": "success",
        "tables": candidate_tables[:5],
        "tableCount": len(candidate_tables[:5]),
        "error": "",
    }


def _cluster_values(values: list[float], tolerance: float = 18.0) -> list[float]:
    """Cluster a sorted list of values; return cluster centers."""
    if not values:
        return []
    clusters: list[list[float]] = []
    current: list[float] = []
    for v in values:
        if current and v - current[-1] > tolerance:
            clusters.append(current)
            current = []
        current.append(v)
    if current:
        clusters.append(current)
    return [sum(cluster) / len(cluster) for cluster in clusters if len(cluster) >= 2]


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "tables": [], "tableCount": 0, "error": message}
