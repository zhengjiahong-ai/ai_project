import re
from collections.abc import Iterable
from typing import Any

VALID_SOURCE_TYPES = {"current_paper", "library", "external_academic", "web_search", "web_page", "image_analysis", "unknown"}
EXTERNAL_EVIDENCE_FIELDS = (
    "provider",
    "providerId",
    "title",
    "authors",
    "year",
    "abstract",
    "doi",
    "url",
    "retrievedAt",
    "query",
    "license",
    "provenance",
)
MIN_CITATION_SCORE = 0.12
# 只在句子与证据不共享书写系统（中文报告句 × 英文证据）时生效的额外门槛。
# 跨语言配对下唯一可用的信号是共享的专名与数值，单个 token 极可能是巧合：
# 实测 “实验在 Tanks and Temples 上…” 只靠一个连词 and 就能对无关证据拿到
# 1/3 = 0.33（远超 0.12）。同语言配对不触发此门槛，分数因此保持不变。
MIN_CROSS_SCRIPT_OVERLAP = 2


def normalize_evidence_items(
    items: Any,
    source_type: str | None = None,
    pdf_id: str | None = None,
    limit: int | None = None,
    max_text_chars: int = 900,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
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
        if evidence["sourceType"] == "external_academic":
            evidence.update({field: raw.get(field) for field in EXTERNAL_EVIDENCE_FIELDS})
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
) -> list[dict[str, Any]]:
    evidence_items = normalize_evidence_items(items, limit=max_items, max_text_chars=max_text_chars)
    compacted = []

    for item in evidence_items:
        source_id = item.get("sourceId")
        compact_item = {
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
        }
        if compact_item["sourceType"] == "external_academic":
            compact_item.update({field: item.get(field) for field in EXTERNAL_EVIDENCE_FIELDS})
        compacted.append(compact_item)

    return compacted


def build_sentence_source_map(
    content: Any,
    sources: Any,
    target: str = "message",
    max_sentences: int = 8,
    max_sources_per_sentence: int = 2,
) -> list[dict[str, Any]]:
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
        source_terms.append((source_id, *_partition_citation_terms(terms)))

    if not source_terms:
        return []

    references = []
    for sentence in _split_reference_sentences(content):
        sentence_terms = _extract_citation_terms(sentence)
        if not sentence_terms:
            continue
        sentence_latin, sentence_cjk = _partition_citation_terms(sentence_terms)

        scored_sources = []
        sentence_scripts = (bool(sentence_latin), bool(sentence_cjk))
        for source_id, source_latin, source_cjk in source_terms:
            overlap = (sentence_latin & source_latin) | (sentence_cjk & source_cjk)
            if not overlap:
                continue
            eligible = (len(sentence_latin) if source_latin else 0) + (
                len(sentence_cjk) if source_cjk else 0
            )
            if not eligible:
                continue
            cross_script = sentence_scripts != (bool(source_latin), bool(source_cjk))
            if cross_script and len(overlap) < MIN_CROSS_SCRIPT_OVERLAP:
                continue
            score = len(overlap) / eligible
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
    fields: dict[str, Any],
    sources: Any,
    max_sentences_per_field: int = 3,
) -> list[dict[str, Any]]:
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


_HYBRID_CHANNELS = ("vector", "bm25")


def _iter_items(items: Any) -> Iterable[Any]:
    if items is None:
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, tuple):
        return list(items)
    if isinstance(items, dict):
        # rag.store 的混合检索返回 {"vector": [...], "bm25": [...], "fused": [...]}。
        # 旧实现把整个 dict 当成一条证据，而 _extract_text 只认 text/document/content
        # 等键，于是整批结果被静默丢弃 —— chat_service 的库级检索因此永远返回空列表。
        fused = items.get("fused")
        if isinstance(fused, list) and fused:
            return fused
        channels = [items[key] for key in _HYBRID_CHANNELS if isinstance(items.get(key), list)]
        if channels:
            return [entry for channel in channels for entry in channel]
    return [items]


def _split_reference_sentences(content: Any) -> list[str]:
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
            for index in range(len(segment) - size + 1):
                terms.add(segment[index:index + size])

    return terms


def _partition_citation_terms(terms: set[str]) -> tuple[set[str], set[str]]:
    """把词项按书写系统分成（拉丁/数字, 中文）两类。

    _extract_citation_terms 的两条正则产出天然不相交（ASCII token 不含汉字，
    中文 n-gram 只含汉字），所以按 isascii 分类是精确的，不是启发式。

    分类的唯一用途是给引用打分挑分母：跨语言配对时中文 n-gram 永远不可能与
    英文证据相交，把它们算进分母会让分数结构性趋零 —— 实测 3DGS 那篇 29 个
    报告句 0 条通过、最高仅 0.0597（阈值 0.12），“结论引用”卡片因此从不出现。
    同语言配对下两类都在，分母仍等于 len(terms)，分数与分类之前逐位一致。
    """
    latin = {term for term in terms if term.isascii()}
    return latin, terms - latin


def _extract_text(item: dict[str, Any]) -> str:
    for key in ("text", "document", "content", "page_content", "abstract"):
        value = item.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _resolve_pdf_id(item: dict[str, Any], pdf_id: str | None) -> str | None:
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


def _resolve_source_id(item: dict[str, Any], pdf_id: str | None, chunk_index: int | None, fallback_index: int) -> str:
    for key in ("sourceId", "source_id", "id"):
        value = item.get(key)
        if value:
            return str(value)

    if pdf_id and chunk_index is not None:
        return f"{pdf_id}-chunk-{chunk_index}"

    return f"source-{fallback_index}"


def _resolve_chunk_index(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = item.get("chunkIndex") if item.get("chunkIndex") is not None else item.get("chunk_index")
    if value is None:
        value = metadata.get("chunk_index") if metadata.get("chunk_index") is not None else metadata.get("chunkIndex")
    return _coerce_int(value)


def _resolve_page_index(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    value = item.get("pageIndex") if item.get("pageIndex") is not None else item.get("page_index")
    if value is None:
        value = metadata.get("pageIndex") if metadata.get("pageIndex") is not None else metadata.get("page_index")
    return _coerce_int(value)


def _resolve_section_id(item: dict[str, Any]) -> str | None:
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


def _coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
