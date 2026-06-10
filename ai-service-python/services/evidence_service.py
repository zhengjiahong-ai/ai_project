import re
from typing import Any, Dict, Iterable, List, Optional


VALID_SOURCE_TYPES = {"current_paper", "library", "unknown"}
MIN_CITATION_SCORE = 0.12


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
        pdf_id_value = _resolve_pdf_id(raw, pdf_id)
        chunk_index = _resolve_chunk_index(raw)
        source_id = _resolve_source_id(raw, pdf_id_value, chunk_index, len(normalized) + 1)

        evidence = {
            "sourceId": source_id,
            "text": _truncate(text, max_text_chars),
            "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
            "similarity": _coerce_number(raw.get("similarity")),
            "score": _coerce_number(raw.get("score")),
            "pdfId": pdf_id_value,
            "chunkIndex": chunk_index,
            "pageIndex": _resolve_page_index(raw),
            "sectionId": _resolve_section_id(raw),
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
            "pageIndex": item.get("pageIndex"),
            "sectionId": item.get("sectionId"),
            "sourceType": item.get("sourceType") or "unknown",
        })

    return compacted


def build_sentence_source_map(
    content: Any,
    sources: Any,
    target: str = "message",
    max_sentences: int = 8,
    max_sources_per_sentence: int = 2,
) -> List[Dict[str, Any]]:
    evidence_items = normalize_evidence_items(sources, max_text_chars=1200)
    source_terms = []
    valid_source_ids = set()
    for item in evidence_items:
        source_id = str(item.get("sourceId") or "").strip()
        if not source_id:
            continue
        terms = _extract_citation_terms(item.get("text") or "")
        if not terms:
            continue
        valid_source_ids.add(source_id)
        source_terms.append((source_id, terms))

    if not source_terms:
        return []

    references = []
    for sentence in _split_reference_sentences(content):
        sentence_terms = _extract_citation_terms(sentence)
        if not sentence_terms:
            continue

        scored_sources = []
        for source_id, terms in source_terms:
            overlap = sentence_terms.intersection(terms)
            if not overlap:
                continue
            score = len(overlap) / max(len(sentence_terms), 1)
            if score >= MIN_CITATION_SCORE:
                scored_sources.append((source_id, score))

        if not scored_sources:
            continue

        scored_sources.sort(key=lambda item: item[1], reverse=True)
        source_ids = [
            source_id
            for source_id, _score in scored_sources[:max_sources_per_sentence]
            if source_id in valid_source_ids
        ]
        if not source_ids:
            continue

        references.append({
            "id": f"ref-{len(references) + 1}",
            "target": str(target or "message"),
            "sentence": sentence,
            "sourceIds": source_ids,
            "confidence": round(scored_sources[0][1], 2),
        })
        if len(references) >= max_sentences:
            break

    return references


def build_field_sentence_source_map(
    fields: Dict[str, Any],
    sources: Any,
    max_sentences_per_field: int = 3,
) -> List[Dict[str, Any]]:
    references = []
    for target, value in fields.items():
        field_references = build_sentence_source_map(
            value,
            sources,
            target=target,
            max_sentences=max_sentences_per_field,
        )
        for item in field_references:
            references.append({
                **item,
                "id": f"ref-{len(references) + 1}",
            })
    return references


def _iter_items(items: Any) -> Iterable[Any]:
    if items is None:
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, tuple):
        return list(items)
    return [items]


def _split_reference_sentences(content: Any) -> List[str]:
    if isinstance(content, list):
        raw_text = "\n".join(str(item) for item in content)
    else:
        raw_text = str(content or "")

    candidates = []
    for line in raw_text.splitlines():
        text = line.strip()
        if not text:
            continue
        text = re.sub(r"^[-*•\d\s.、)）]+", "", text).strip()
        if not text:
            continue
        marked_text = re.sub(r"([。！？!?；;])", r"\1\n", text)
        candidates.extend(marked_text.splitlines())

    if not candidates:
        marked_text = re.sub(r"([。！？!?；;])", r"\1\n", raw_text)
        candidates = marked_text.splitlines()

    normalized = []
    seen = set()
    for candidate in candidates:
        text = " ".join(str(candidate or "").strip().split())
        if len(text) < 8:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text[:220])
    return normalized


def _extract_citation_terms(text: Any) -> set[str]:
    value = str(text or "").lower()
    terms = set()

    for token in re.findall(r"[a-z0-9][a-z0-9._-]{1,31}", value):
        if len(token) >= 3:
            terms.add(token)

    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", value):
        if len(segment) <= 6:
            terms.add(segment)
        for size in (2, 3, 4):
            if len(segment) < size:
                continue
            for index in range(0, len(segment) - size + 1):
                terms.add(segment[index:index + size])

    return terms


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


def _resolve_source_id(item: Dict[str, Any], pdf_id: Optional[str], chunk_index: Optional[int], fallback_index: int) -> str:
    for key in ("sourceId", "source_id", "id"):
        value = item.get(key)
        if value:
            return str(value)

    if pdf_id and chunk_index is not None:
        return f"{pdf_id}-chunk-{chunk_index}"

    return f"source-{fallback_index}"


def _resolve_chunk_index(item: Dict[str, Any]) -> Optional[int]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = item.get("chunkIndex") if item.get("chunkIndex") is not None else item.get("chunk_index")
    if value is None:
        value = metadata.get("chunk_index") if metadata.get("chunk_index") is not None else metadata.get("chunkIndex")
    return _coerce_int(value)


def _resolve_page_index(item: Dict[str, Any]) -> Optional[int]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = item.get("pageIndex") if item.get("pageIndex") is not None else item.get("page_index")
    if value is None:
        value = metadata.get("pageIndex") if metadata.get("pageIndex") is not None else metadata.get("page_index")
    return _coerce_int(value)


def _resolve_section_id(item: Dict[str, Any]) -> Optional[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = item.get("sectionId") or item.get("section_id")
    if not value:
        value = metadata.get("sectionId") or metadata.get("section_id")
    if value is None or value == "":
        return None
    return str(value)


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
