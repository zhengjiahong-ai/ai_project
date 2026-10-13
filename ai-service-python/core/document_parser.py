from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from bs4 import BeautifulSoup


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, round(value, 6)))


def _coerce_page_index(value: Any, fallback: int | None = None) -> int | None:
    if value is None:
        return fallback

    text = str(value).strip()
    if not text:
        return fallback

    if text.isdigit():
        return max(int(text) - 1, 0)

    match = re.search(r"(\d+)$", text)
    if match:
        return max(int(match.group(1)) - 1, 0)

    return fallback


def _collect_page_sizes(soup: BeautifulSoup) -> dict[int, dict[str, float]]:
    page_sizes: dict[int, dict[str, float]] = {}

    for index, surface in enumerate(soup.find_all("surface")):
        page_index = _coerce_page_index(surface.get("n") or surface.get("xml:id"), index)
        if page_index is None:
            continue

        width = _to_float(surface.get("width")) or _to_float(surface.get("lrx"))
        height = _to_float(surface.get("height")) or _to_float(surface.get("lry"))
        if width is None or height is None:
            continue

        page_sizes[page_index] = {
            "width": round(width, 2),
            "height": round(height, 2),
        }

    return page_sizes


def _parse_coords_attribute(raw_value: Any) -> list[dict[str, float]]:
    coords: list[dict[str, float]] = []
    text = str(raw_value or "").strip()
    if not text:
        return coords

    for chunk in text.split(";"):
        parts = [part.strip() for part in chunk.split(",") if part.strip()]
        if len(parts) < 5:
            continue

        page_index = _coerce_page_index(parts[0])
        x = _to_float(parts[1])
        y = _to_float(parts[2])
        width = _to_float(parts[3])
        height = _to_float(parts[4])
        if page_index is None or None in (x, y, width, height):
            continue

        coords.append(
            {
                "pageIndex": page_index,
                "x": max(x, 0.0),
                "y": max(y, 0.0),
                "width": max(width, 0.0),
                "height": max(height, 0.0),
            }
        )

    return coords


def _collect_element_coords(element) -> list[dict[str, float]]:
    coords = _parse_coords_attribute(element.get("coords"))
    if coords:
        return coords

    nested_coords: list[dict[str, float]] = []
    for child in element.find_all(attrs={"coords": True}):
        nested_coords.extend(_parse_coords_attribute(child.get("coords")))
    return nested_coords


def _union_boxes(boxes: list[dict[str, float]]) -> dict[str, float] | None:
    if not boxes:
        return None

    left = min(box["x"] for box in boxes)
    top = min(box["y"] for box in boxes)
    right = max(box["x"] + box["width"] for box in boxes)
    bottom = max(box["y"] + box["height"] for box in boxes)

    return {
        "x": left,
        "y": top,
        "width": max(right - left, 0.0),
        "height": max(bottom - top, 0.0),
    }


def _normalize_box(box: dict[str, float], page_size: dict[str, float] | None) -> dict[str, float] | None:
    if not page_size:
        return None

    page_width = page_size.get("width") or 0
    page_height = page_size.get("height") or 0
    if page_width <= 0 or page_height <= 0:
        return None

    return {
        "left": _clamp_ratio(box["x"] / page_width),
        "top": _clamp_ratio(box["y"] / page_height),
        "width": _clamp_ratio(box["width"] / page_width),
        "height": _clamp_ratio(box["height"] / page_height),
    }


def _resolve_zone_type(element) -> str:
    if element.name == "formula":
        return "formula"

    figure_type = str(element.get("type") or "").lower()
    if "table" in figure_type or element.find("table") is not None:
        return "table"

    return "figure"


def extract_translation_layout_index(tei_path: str) -> dict[int, dict[str, Any]]:
    with open(tei_path, "r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "xml")

    page_sizes = _collect_page_sizes(soup)
    layout_index: dict[int, dict[str, Any]] = defaultdict(lambda: {"excludedZones": []})

    for element in soup.find_all(["figure", "formula"]):
        coords = _collect_element_coords(element)
        if not coords:
            continue

        per_page_coords: dict[int, list[dict[str, float]]] = defaultdict(list)
        for coord in coords:
            per_page_coords[coord["pageIndex"]].append(coord)

        zone_type = _resolve_zone_type(element)
        for page_index, boxes in per_page_coords.items():
            union_box = _union_boxes(boxes)
            normalized_bbox = _normalize_box(union_box, page_sizes.get(page_index)) if union_box else None
            if not normalized_bbox:
                continue

            layout_index[page_index]["excludedZones"].append(
                {
                    "type": zone_type,
                    "bbox": normalized_bbox,
                }
            )
            if page_index in page_sizes:
                layout_index[page_index]["pageSize"] = page_sizes[page_index]

    return dict(layout_index)


def _normalize_heading_number(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    match = re.match(r"^([A-Za-z]?\d+(?:[.\-]\d+)*|[IVXLC]+(?:[.\-][IVXLC]+)*)", text, re.IGNORECASE)
    return match.group(1).replace("-", ".") if match else ""


def _infer_heading_number(title: str, head) -> str:
    explicit_number = _normalize_heading_number(
        (head.get("n") if head else None)
        or (head.get("xml:id") if head else None)
        or (head.get("id") if head else None)
    )
    if explicit_number:
        return explicit_number

    return _normalize_heading_number(title)


def _infer_section_level(heading_number: str, nested_level: int) -> int:
    if heading_number:
        numeric_parts = [part for part in re.split(r"[.]+", heading_number) if part]
        if numeric_parts:
            return max(1, min(len(numeric_parts), 6))

    return max(1, min(nested_level, 6))


def _extract_table_sections(body):
    """Keep TEI table cells and spans without inferring damaged column labels."""
    result = []
    candidates = [node for node in body.find_all(['figure', 'table'])
                  if (node.name == 'figure' and _resolve_zone_type(node) == 'table')
                  or (node.name == 'table' and not node.find_parent(['figure', 'table']))]
    for index, owner in enumerate(candidates):
        if owner.find_parent('table'):
            continue
        table = owner.find('table') if owner.name == 'figure' else owner
        head = owner.find('head', recursive=False)
        caption = owner.find('figDesc', recursive=False)
        title = head.get_text(' ', strip=True) if head else f'Table {index + 1}'
        description = caption.get_text(' ', strip=True) if caption else ''
        rows = []
        spans = False
        for row in table.find_all('row') if table else []:
            if row.find_parent('table') is not table:
                continue
            cells = []
            for cell in row.find_all('cell', recursive=False):
                def span(name):
                    value = str(cell.get(name) or '1')
                    return int(value) if value.isdigit() and int(value) > 0 else 1
                cols, row_span = span('cols'), span('rows')
                spans = spans or cols > 1 or row_span > 1
                cells.append({'text': cell.get_text(' ', strip=True), 'cols': cols, 'rows': row_span})
            if cells:
                rows.append(cells)
        lines = [f'Table caption: {title} {description}'.strip()]
        for number, row in enumerate(rows, 1):
            values = [cell['text'] + (f" [cols={cell['cols']}, rows={cell['rows']}]"
                      if cell['cols'] > 1 or cell['rows'] > 1 else '') for cell in row]
            lines.append(f'Table row {number}: ' + ' | '.join(values))
        if not rows:
            lines.append((table or owner).get_text(' ', strip=True))
        coords = _collect_element_coords(owner)
        page = min((coord['pageIndex'] for coord in coords), default=None)
        table_id = owner.get('xml:id') or owner.get('id') or f'table-{index + 1}'
        section = {'id': f'table-{table_id}', 'section': f'{title} {description}'.strip(),
                   'content': '\n'.join(lines), 'evidenceKind': 'table', 'tableId': table_id,
                   'tableColumnMappingUnverified': spans or not rows, 'tableRows': rows,
                   'tablePrefix': '\n'.join(lines[:2] if rows else lines)}
        if page is not None:
            section.update(pageIndex=page, page=page + 1)
            table_coords = _collect_element_coords(table or owner)
            if len(table_coords) == 1 and table_coords[0]['pageIndex'] == page:
                coord = table_coords[0]
                section['tableBounds'] = [coord['x'], coord['y'], coord['width'], coord['height']]
        result.append(section)
    return result


def parse_tei_xml(tei_path, pdf_path=None):
    with open(tei_path, "r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "xml")

    sections = []
    metadata_lines = []

    title_tag = soup.find("title")
    if title_tag:
        metadata_lines.append(f"Title: {title_tag.get_text(strip=True)}")

    authors = []
    for author in soup.find_all("author"):
        pers_name = author.find("persName")
        if not pers_name:
            continue

        surname = pers_name.find("surname")
        forename = pers_name.find("forename")
        name_parts = []
        if forename:
            name_parts.append(forename.get_text(strip=True))
        if surname:
            name_parts.append(surname.get_text(strip=True))
        if name_parts:
            authors.append(" ".join(name_parts))

    if authors:
        metadata_lines.append(f"Authors: {', '.join(authors)}")

    abstract_tag = soup.find("abstract")
    if abstract_tag:
        metadata_lines.append(f"Abstract: {abstract_tag.get_text(strip=True)}")

    keywords = [keyword.get_text(strip=True) for keyword in soup.find_all("term")]
    if keywords:
        metadata_lines.append(f"Keywords: {', '.join(keywords)}")

    if metadata_lines:
        sections.append(
            {
                "section": "Front Matter (Metadata)",
                "content": "\n".join(metadata_lines),
            }
        )

    body = soup.find("body") or soup
    body_divs = body.find_all("div")
    div_ids = {id(div): f"section-{index + 1}" for index, div in enumerate(body_divs)}

    for div in body_divs:
        head = div.find("head", recursive=False) or div.find("head")
        title = head.get_text(strip=True) if head else "unknown"
        coords = _collect_element_coords(div)
        first_page_index = min((coord["pageIndex"] for coord in coords), default=None)
        ancestor_divs = [parent for parent in div.find_parents("div") if id(parent) in div_ids]
        nested_level = len(ancestor_divs) + 1
        heading_number = _infer_heading_number(title, head)
        parent_div = ancestor_divs[0] if ancestor_divs else None
        parent_id = div_ids.get(id(parent_div)) if parent_div else None

        paragraphs = [paragraph.get_text(strip=True) for paragraph in div.find_all("p")
                      if not paragraph.find_parent('table')
                      and not any(_resolve_zone_type(figure) == 'table'
                                  for figure in paragraph.find_parents('figure'))]
        for formula in div.find_all("formula"):
            paragraphs.append("Equation: " + formula.get_text(strip=True))

        for figure in div.find_all("figure"):
            if _resolve_zone_type(figure) == 'table':
                continue  # Indexed separately with cells, caption and page.
            zone_type = _resolve_zone_type(figure).capitalize()
            paragraphs.append(f"{zone_type}: " + figure.get_text(strip=True))

        content = "\n".join(item for item in paragraphs if item.strip())
        if content.strip():
            section_payload = {
                "id": div_ids[id(div)],
                "section": title,
                "content": content,
                "level": _infer_section_level(heading_number, nested_level),
                "nestedLevel": nested_level,
            }
            if parent_id:
                section_payload["parentId"] = parent_id
            if heading_number:
                section_payload["headingNumber"] = heading_number
            if first_page_index is not None:
                section_payload["pageIndex"] = first_page_index
                section_payload["page"] = first_page_index + 1
            sections.append(section_payload)

    sections.extend(_extract_table_sections(body))
    if pdf_path:
        from core.pdf_table_columns import attach_verified_table_columns
        sections = attach_verified_table_columns(sections, pdf_path)
    return sections
