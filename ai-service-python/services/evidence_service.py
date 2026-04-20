from typing import Any, Dict, Iterable, List, Optional


VALID_SOURCE_TYPES = {"current_paper", "library", "unknown"}


def normalize_evidence_items(
    items: Any,
    source_type: Optional[str] = None,
    pdf_id: Optional[str] = None,
    limit: Optional[int] = None,
    max_text_chars: int = 900,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    resolved_source_type = _normalize_source_type(source_type)

    for item in _iter_items(items):
        raw = item if isinstance(item, dict) else {"text": item}
        text = _extract_text(raw)
        if not text:
            continue

        evidence = {
            "sourceId": str(raw.get("sourceId") or raw.get("id") or f"source-{len(normalized) + 1}"),
            "text": _truncate(text, max_text_chars),
            "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
            "similarity": _coerce_number(raw.get("similarity")),
            "score": _coerce_number(raw.get("score")),
            "pdfId": _resolve_pdf_id(raw, pdf_id),
            "chunkIndex": _resolve_chunk_index(raw),
            "sourceType": _normalize_source_type(raw.get("sourceType") or raw.get("source_type") or resolved_source_type),
        }
        normalized.append(evidence)

        if limit is not None and len(normalized) >= limit:
            break

    return normalized


def format_evidence_context(
    items: Any,
    title: str = "证据片段",
    max_items: int = 5,
    max_text_chars: int = 700,
) -> str:
    evidence_items = normalize_evidence_items(items, limit=max_items, max_text_chars=max_text_chars)
    if not evidence_items:
        return ""

    lines = [f"\n\n{title}:"]
    for item in evidence_items:
        source_id = item.get("sourceId") or "source"
        source_type = item.get("sourceType") or "unknown"
        similarity = item.get("similarity")
        score = item.get("score")
        metrics = []
        if similarity is not None:
            metrics.append(f"similarity={similarity:.4f}")
        if score is not None:
            metrics.append(f"score={score:.4f}")

        meta_text = f" [{source_type}]"
        if metrics:
            meta_text += f" ({', '.join(metrics)})"
        lines.append(f"- {source_id}{meta_text}: {item.get('text', '')}")

    return "\n".join(lines)


def compact_evidence_for_response(
    items: Any,
    max_items: int = 5,
    max_text_chars: int = 700,
) -> List[Dict[str, Any]]:
    evidence_items = normalize_evidence_items(items, limit=max_items, max_text_chars=max_text_chars)
    compacted = []

    for item in evidence_items:
        source_id = item.get("sourceId")
        compacted.append({
            "id": source_id,
            "sourceId": source_id,
            "text": item.get("text", ""),
            "metadata": item.get("metadata") or {},
            "similarity": item.get("similarity"),
            "score": item.get("score"),
            "pdfId": item.get("pdfId"),
            "chunkIndex": item.get("chunkIndex"),
            "sourceType": item.get("sourceType") or "unknown",
        })

    return compacted


def _iter_items(items: Any) -> Iterable[Any]:
    if items is None:
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, tuple):
        return list(items)
    return [items]


def _extract_text(item: Dict[str, Any]) -> str:
    for key in ("text", "document", "content", "page_content"):
        value = item.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _resolve_pdf_id(item: Dict[str, Any], pdf_id: Optional[str]) -> Optional[str]:
    if pdf_id:
        return str(pdf_id)

    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for key in ("pdfId", "pdf_id", "id"):
        value = metadata.get(key)
        if value:
            return str(value)

    for key in ("pdfId", "pdf_id"):
        value = item.get(key)
        if value:
            return str(value)

    return None


def _resolve_chunk_index(item: Dict[str, Any]) -> Optional[int]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = (
        metadata.get("chunk_index")
        if metadata.get("chunk_index") is not None
        else metadata.get("chunkIndex")
    )
    if value is None:
        value = item.get("chunkIndex") if item.get("chunkIndex") is not None else item.get("chunk_index")
    return _coerce_int(value)


def _normalize_source_type(value: Any) -> str:
    text = str(value or "unknown").strip()
    return text if text in VALID_SOURCE_TYPES else "unknown"


def _truncate(text: str, max_chars: int) -> str:
    value = text.strip()
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip()


def _coerce_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
