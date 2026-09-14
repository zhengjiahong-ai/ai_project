import logging
import os
import re
from typing import Any

from rag.store import get_rag
from schemas.requests import BackgroundKnowledgeRequest
from services.evidence_service import (
    compact_evidence_for_response,
    normalize_evidence_items,
)
from services.graph_normalizer import (
    DEFAULT_PREFERRED_DEPTH,
    DEFAULT_USER_LEVEL,
    RELATION_TYPE_MAP,
    ROOT_NODE_ID,
    _coerce_confidence,
    _coerce_list_of_strings,
    _coerce_text,
    _dedupe_strings,
    _fallback_payload,
    _normalize_label_key,
    _normalize_payload,
    _normalize_relation,
    _stable_id,
    _stringify_mapping,
)
from services.knowledge_graph_service import generate_current_paper_graph
from services.knowledge_graph_store import save_graph_snapshot
from services.query_service import build_retrieval_queries
from services.safety_service import (
    summarize_safety_results,
    wrap_untrusted_context,
)
from services.trace_service import (
    finalize_trace,
    record_counter,
    record_metric,
    sanitize_text,
    start_trace,
    trace_step,
)

_logger = logging.getLogger(__name__)

USER_LEVEL_ALIASES = {
    "": DEFAULT_USER_LEVEL,
    "一般": "一般",
    "普通": "一般",
    "普通/一般": "一般",
    "normal": "一般",
    "general": "一般",
    "intermediate": "一般",
    "入门": "入门",
    "基础": "入门",
    "beginner": "入门",
    "novice": "入门",
    "进阶": "进阶",
    "advanced": "进阶",
    "expert": "进阶",
    "深入": "进阶",
}

PREFERRED_DEPTH_ALIASES = {
    "": DEFAULT_PREFERRED_DEPTH,
    "速览": "速览",
    "快速": "速览",
    "简要": "速览",
    "标准": "标准",
    "普通": "标准",
    "深入": "深入",
    "深度": "深入",
}


def get_background_knowledge(request: BackgroundKnowledgeRequest) -> dict[str, Any]:
    reader_profile = _resolve_reader_profile(request)
    adaptation_reason = _build_adaptation_reason(reader_profile)
    trace_id = start_trace(
        "background",
        request_meta={
            "pdfId": sanitize_text(request.pdfId, max_chars=80),
            "userLevel": sanitize_text(reader_profile.get("user_knowledge_level"), max_chars=40),
            "paperTopic": sanitize_text(request.paper_topic, max_chars=120),
        },
    )
    try:
        user_level = str(reader_profile.get("user_knowledge_level") or DEFAULT_USER_LEVEL)
        normalized_pdf_id = _normalize_pdf_id(request.pdfId)
        paper_context, current_paper_sources = _load_current_paper_context(request, normalized_pdf_id)
        paper_topic = _resolve_topic(request, paper_context)
        with trace_step("build_background_query_plan", input_size=len(paper_context) + len(paper_topic)) as step:
            query_plan = build_retrieval_queries(paper_topic, context=paper_context, task_type="background")
            step["outputSize"] = len(query_plan.get("keywords") or [])
        retrieved_sources = _retrieve_related_sources(query_plan, normalized_pdf_id)

        response_sources = retrieved_sources or current_paper_sources
        response_source_type = "current_paper" if response_sources and normalized_pdf_id else "unknown"
        response_rag_sources = compact_evidence_for_response(
            normalize_evidence_items(
                response_sources,
                source_type=response_source_type,
                pdf_id=normalized_pdf_id if response_source_type == "current_paper" else None,
                limit=5,
            )
        )

        try:
            llm_payload = _generate_graph_payload(
                paper_topic=paper_topic,
                reader_profile=reader_profile,
                paper_context=paper_context,
                rag_sources=response_rag_sources,
                request=request,
            )
            with trace_step("normalize_background_payload", input_size=len(response_rag_sources)) as step:
                payload = _normalize_payload(
                    llm_payload,
                    paper_topic=paper_topic,
                    reader_profile=reader_profile,
                    pdf_id=normalized_pdf_id,
                    rag_sources=response_rag_sources,
                )
                step["outputSize"] = len((payload.get("graph") or {}).get("nodes") or [])
        except Exception as error:
            _logger.error(f"background knowledge graph generation fell back to linear plan: {error}")
            payload = _fallback_payload(
                paper_topic=paper_topic,
                reader_profile=reader_profile,
                pdf_id=normalized_pdf_id,
                rag_sources=response_rag_sources,
                error=error,
            )

        payload["rag_sources"] = response_rag_sources
        payload["queryPlan"] = query_plan
        payload["sqlite"] = _persist_optional_sqlite(payload)
        payload["neo4j"] = _persist_optional_neo4j(payload)
        payload["traceId"] = trace_id
        payload["reader_profile"] = payload.get("reader_profile") or reader_profile
        payload["adaptation_reason"] = adaptation_reason
        record_metric("ragSourceCount", len(response_rag_sources))
        record_metric("graphNodeCount", len((payload.get("graph") or {}).get("nodes") or []))
        finalize_trace(
            "success",
            response_meta={
                "paperTopic": sanitize_text(paper_topic, max_chars=120),
                "ragSourceCount": len(response_rag_sources),
                "graphNodeCount": len((payload.get("graph") or {}).get("nodes") or []),
                **summarize_safety_results(
                    wrap_untrusted_context("Background paper context", paper_context[:9000], max_tokens=2200),
                    wrap_untrusted_context("Background paper structure", _stringify_mapping(request.paperStructure), max_tokens=800),
                    wrap_untrusted_context(
                        "Background RAG sources",
                        "\n\n".join(item.get("text", "") for item in response_rag_sources if isinstance(item, dict))[:5000],
                        max_tokens=1200,
                    ),
                ),
            },
        )
        return payload
    except Exception as error:
        finalize_trace("error", error=error)
        raise


def _normalize_pdf_id(pdf_id: str | None) -> str | None:
    if not pdf_id:
        return None

    try:
        return get_rag().normalize_id(pdf_id)
    except Exception:
        return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(pdf_id)).lower()


def _load_current_paper_context(request: BackgroundKnowledgeRequest, normalized_pdf_id: str | None) -> tuple[str, list[dict]]:
    with trace_step("load_background_context", meta={"pdfId": sanitize_text(normalized_pdf_id, max_chars=80)}) as step:
        parts: list[str] = []
        sources: list[dict] = []

        if isinstance(request.paperStructure, dict) and request.paperStructure:
            parts.append(f"Paper structure:\n{_stringify_mapping(request.paperStructure)}")

        if isinstance(request.paperSkeleton, dict) and request.paperSkeleton:
            parts.append(f"Paper section summaries:\n{_stringify_mapping(request.paperSkeleton)}")

        if normalized_pdf_id:
            try:
                record_counter("retrievalCalls")
                documents = get_rag().get_documents_by_metadata({"id": normalized_pdf_id}, limit=40)
                sources = documents[:5]
                document_text = "\n\n".join(item.get("text", "") for item in documents if item.get("text"))
                if document_text.strip():
                    parts.append(f"Current indexed paper excerpts:\n{document_text[:9000]}")
            except Exception as error:
                _logger.error(f"background knowledge current-paper retrieval skipped: {error}")

        context = "\n\n".join(part for part in parts if part.strip())[:12000]
        step["outputSize"] = len(context)
        return context, sources


# 索引片段的正文格式固定是 "Paper: <title>\n\nSection: ...\n\nContent: ..."。
_PAPER_TITLE_RE = re.compile(r"^Paper:\s*(.+)$", re.MULTILINE)


def _extract_indexed_paper_title(paper_context: str) -> str:
    """从已索引片段里取论文标题，取不到返回空串。"""
    match = _PAPER_TITLE_RE.search(str(paper_context or ""))
    if not match:
        return ""
    return " ".join(match.group(1).split())[:120]


def _topic_from_pdf_id(pdf_id: str | None) -> str:
    """退到文件名当主题。不好看，但仍比把整段检索原文当主题好。"""
    name = str(pdf_id or "").strip()
    if not name:
        return ""
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return " ".join(part for part in re.split(r"[_\-]+", name) if part)[:80]


def _resolve_topic(request: BackgroundKnowledgeRequest, paper_context: str) -> str:
    """定主题。它同时是知识图谱根节点的标签，会原样展示给用户，所以必须是标题级的短文本。

    旧实现在 request.paper_topic 与 structure/skeleton 都缺失时，直接把 paper_context
    （最多九千字检索原文）压成一行截 240 字返回。实测走到的就是这条兜底：根节点标签成了
    "Current indexed paper excerpts: Paper: 3D Gaussian Splatting ... Section: Ours
    (93 fps) Content: Train: 51min, PSNR: 25.2 ..."，图谱正中央一坨英文原文，而这段文本
    还会作为 paper_topic 灌进概念抽取的 prompt。前端只在做过篇章解构时才传得上
    paper_topic（App.jsx 取 research_problem/core_hypothesis），所以"没先解构就点背景
    补课"这条最常见的路径必然踩中它。

    兜底顺序改成"越像标题越优先"：结构里的 title、索引片段自带的 Paper: 行、文件名，
    再往后才是研究问题/摘要这类长文本，且一律限长。
    """
    topic = _coerce_text(request.paper_topic)
    if topic:
        return topic[:120]

    structure = request.paperStructure if isinstance(request.paperStructure, dict) else {}
    title = _coerce_text(structure.get("title"))
    if title:
        return title[:120]

    indexed_title = _extract_indexed_paper_title(paper_context)
    if indexed_title:
        return indexed_title

    file_topic = _topic_from_pdf_id(request.pdfId)
    if file_topic:
        return file_topic

    for key in ("research_problem", "core_hypothesis", "method_framework"):
        value = structure.get(key)
        if isinstance(value, list) and value:
            return ", ".join(str(item) for item in value[:3])[:120]
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]

    skeleton = request.paperSkeleton if isinstance(request.paperSkeleton, dict) else {}
    for key in ("abstract", "introduction", "methods"):
        value = skeleton.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]

    if paper_context.strip():
        return " ".join(paper_context.split())[:80]

    return "当前论文"


def _retrieve_related_sources(query_plan: dict[str, Any], normalized_pdf_id: str | None) -> list[dict]:
    query = query_plan.get("rewritten") or query_plan.get("original") or "prerequisite concepts background knowledge"
    if normalized_pdf_id:
        try:
            with trace_step(
                "retrieve_background_current_paper",
                input_size=len(str(query or "")),
                meta={"pdfId": sanitize_text(normalized_pdf_id, max_chars=80)},
            ) as step:
                record_counter("retrievalCalls")
                results = get_rag().retrieve(query, top_k=5, filter_metadata={"id": normalized_pdf_id})
                step["outputSize"] = len(results or [])
                return results
        except Exception as error:
            _logger.error(f"background knowledge filtered retrieval skipped: {error}")

    return []


def _normalize_hybrid_sources(hybrid_results: dict[str, list[dict]]) -> list[dict]:
    if not isinstance(hybrid_results, dict):
        return []

    # fused 已按文本去重且向量优先；直接拼 vector + bm25 会让两路重叠的片段
    # 先吃掉 limit 名额，再去重就凑不满下面的 5 条。
    items = hybrid_results.get("fused") or []
    if not items:
        items = [
            *(hybrid_results.get("vector") or []),
            *(hybrid_results.get("bm25") or []),
        ]
    evidence = normalize_evidence_items(items, source_type="library", limit=10)

    deduped = []
    seen = set()
    for item in evidence:
        text_key = _normalize_label_key(item.get("text"))
        if not text_key or text_key in seen:
            continue
        seen.add(text_key)
        deduped.append(item)
        if len(deduped) >= 5:
            break

    return deduped


def _generate_graph_payload(
    paper_topic: str,
    reader_profile: dict[str, Any],
    paper_context: str,
    rag_sources: list[dict],
    request: BackgroundKnowledgeRequest,
) -> dict[str, Any]:
    cross_paper_sources = None
    if getattr(request, 'include_library_papers', False):
        # Retrieve cross-paper context from other papers in the library
        cross_paper_sources = _load_cross_paper_sources(request)
    return generate_current_paper_graph(
        paper_topic=paper_topic,
        paper_context=paper_context,
        paper_structure=request.paperStructure if isinstance(request.paperStructure, dict) else {},
        rag_sources=rag_sources,
        reader_profile=reader_profile,
        pdf_id=_normalize_pdf_id(request.pdfId),
        cross_paper_sources=cross_paper_sources,
    )


def _load_cross_paper_sources(request: BackgroundKnowledgeRequest) -> list[dict[str, Any]] | None:
    """Load paper context from other papers in the library (opt-in only).

    Retrieves related papers from the knowledge graph store and returns their
    indexed fragments as additional context for concept extraction. The current
    paper is excluded from results.
    """
    normalized_pdf_id = _normalize_pdf_id(request.pdfId)
    if not normalized_pdf_id:
        return None
    try:
        from services.knowledge_graph_store import read_graph_neighborhood
        seed_terms = [str(request.paper_topic or '').strip()] if request.paper_topic else []
        neighborhood = read_graph_neighborhood(
            paperIds=None,
            sourceIds=None,
            seedTerms=seed_terms,
            maxNodes=6,
            maxEdges=8,
        )
        if neighborhood.get('status') == 'unavailable':
            return None
        # Extract paper-level context from neighbor graph nodes
        sources: list[dict[str, Any]] = []
        for node in (neighborhood.get('nodes') or [])[:3]:
            node_pdf_id = str(node.get('pdfId') or '')
            if node_pdf_id and node_pdf_id != normalized_pdf_id:
                sources.append({
                    'sourceId': f"cross-paper-{node_pdf_id}",
                    'text': str(node.get('summary') or node.get('label') or ''),
                    'paperTitle': str(node.get('paperTitle') or node_pdf_id),
                    'pdfId': node_pdf_id,
                    'provenance': 'library',
                })
        return sources if sources else None
    except Exception:
        return None




def _persist_optional_neo4j(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("persist_background_neo4j") as step:
        uri = os.environ.get("NEO4J_URI")
        user = os.environ.get("NEO4J_USER")
        password = os.environ.get("NEO4J_PASSWORD")
        if not uri or not user or not password:
            result = {
                "enabled": False,
                "status": "skipped",
                "message": "NEO4J_URI, NEO4J_USER, or NEO4J_PASSWORD is not configured.",
            }
            step["outputSize"] = 0
            return result

        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(uri, auth=(user, password))
            graph = payload.get("graph", {})
            with driver.session() as session:
                session.execute_write(_write_graph_tx, payload, graph)
            driver.close()
            step["outputSize"] = len((graph or {}).get("nodes") or [])
            return {"enabled": True, "status": "success", "message": "Knowledge graph persisted to Neo4j."}
        except Exception as error:
            step["outputSize"] = 0
            return {"enabled": True, "status": "error", "message": str(error)[:300]}


def _persist_optional_sqlite(payload: dict[str, Any]) -> dict[str, Any]:
    with trace_step("persist_background_sqlite") as step:
        result = save_graph_snapshot(payload)
        step["outputSize"] = len((payload.get("graph") or {}).get("nodes") or []) if result.get("status") == "success" else 0
        return result


def _write_graph_tx(tx, payload: dict[str, Any], graph: dict[str, list]) -> None:
    paper_id = payload.get("pdfId") or _stable_id(payload.get("paper_topic") or ROOT_NODE_ID) or ROOT_NODE_ID
    tx.run(
        """
        MERGE (p:Paper {id: $paper_id})
        SET p.topic = $topic, p.userKnowledgeLevel = $level
        """,
        paper_id=paper_id,
        topic=payload.get("paper_topic"),
        level=payload.get("user_knowledge_level"),
    )

    for node in graph.get("nodes", []):
        tx.run(
            """
            MERGE (c:Concept {id: $id})
            SET c.label = $label,
                c.type = $type,
                c.level = $level,
                c.summary = $summary,
                c.why = $why,
                c.stage = $stage,
                c.confidence = $confidence,
                c.sourceIds = $sourceIds,
                c.provenanceStatus = $provenanceStatus,
                c.confidenceReason = $confidenceReason
            WITH c
            MATCH (p:Paper {id: $paper_id})
            MERGE (p)-[:HAS_BACKGROUND_NODE]->(c)
            """,
            paper_id=paper_id,
            **node,
        )

    relationship_items = list(graph.get("links", []))
    relationship_items.extend(
        {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "relation": edge.get("type"),
            "label": "前置",
            "sourceIds": edge.get("sourceIds", []),
            "confidenceReason": edge.get("confidenceReason", ""),
            "provenanceStatus": edge.get("provenanceStatus", "model_inference"),
            "confidence": edge.get("confidence", 0.6),
        }
        for edge in graph.get("edges", [])
        if isinstance(edge, dict)
    )
    seen_relationships = set()

    for link in relationship_items:
        relation = _normalize_relation(link.get("relation"))
        relation_key = (link.get("source"), link.get("target"), relation)
        if relation_key in seen_relationships:
            continue
        seen_relationships.add(relation_key)
        relation_type = RELATION_TYPE_MAP.get(relation, "RELATED_TO")
        tx.run(
            f"""
            MATCH (source:Concept {{id: $source}})
            MATCH (target:Concept {{id: $target}})
            MERGE (source)-[r:{relation_type}]->(target)
            SET r.label = $label,
                r.relation = $relation,
                r.sourceIds = $sourceIds,
                r.confidenceReason = $confidenceReason,
                r.provenanceStatus = $provenanceStatus,
                r.confidence = $confidence
            """,
            source=link.get("source"),
            target=link.get("target"),
            label=link.get("label"),
            relation=relation,
            sourceIds=_coerce_list_of_strings(link.get("sourceIds")),
            confidenceReason=str(link.get("confidenceReason") or ""),
            provenanceStatus=str(link.get("provenanceStatus") or "model_inference"),
            confidence=_coerce_confidence(link.get("confidence"), 0.6),
        )


def _parse_line_items(raw: str) -> list[str]:
    return [
        item.strip("-* 0123456789.、").strip()
        for item in (raw or "").splitlines()
        if item.strip("-* 0123456789.、").strip()
    ]


def _normalize_user_level(value: Any) -> str:
    text = _coerce_text(value).lower()
    return USER_LEVEL_ALIASES.get(text, DEFAULT_USER_LEVEL)


def _normalize_preferred_depth(value: Any) -> str:
    text = _coerce_text(value)
    return PREFERRED_DEPTH_ALIASES.get(text, DEFAULT_PREFERRED_DEPTH)


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[\n,，;；、]+", value)
        return _dedupe_strings([item.strip() for item in items if item.strip()])
    return _coerce_list_of_strings(value)


def _coerce_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _resolve_reader_profile(request: BackgroundKnowledgeRequest) -> dict[str, Any]:
    raw_profile = request.reader_profile if isinstance(request.reader_profile, dict) else {}
    behavior_signals = request.behavior_signals if isinstance(request.behavior_signals, dict) else {}
    self_assessed = _normalize_user_level(
        raw_profile.get("selfAssessedFamiliarity") or raw_profile.get("user_knowledge_level") or request.user_knowledge_level
    )
    known_concepts = _normalize_string_list(raw_profile.get("knownConcepts"))
    confusing_concepts = _normalize_string_list(raw_profile.get("confusingConcepts"))
    question_count = _coerce_non_negative_int(behavior_signals.get("questionCount"))
    translation_usage_count = _coerce_non_negative_int(behavior_signals.get("translationUsageCount"))
    highlight_count = _coerce_non_negative_int(behavior_signals.get("highlightCount"))
    note_count = _coerce_non_negative_int(behavior_signals.get("noteCount"))

    inferred_level = self_assessed
    if question_count >= 4 or translation_usage_count >= 3:
        inferred_level = "入门"
    elif note_count >= 3 and highlight_count >= 3 and question_count <= 2:
        inferred_level = "进阶"

    if len(known_concepts) >= 4 and inferred_level == "入门":
        inferred_level = "一般"
    if len(confusing_concepts) >= 3 and inferred_level == "进阶":
        inferred_level = "一般"

    return {
        "user_knowledge_level": inferred_level,
        "selfAssessedFamiliarity": self_assessed,
        "preferredDepth": _normalize_preferred_depth(raw_profile.get("preferredDepth")),
        "learningGoal": _coerce_text(raw_profile.get("learningGoal")),
        "knownConcepts": known_concepts,
        "confusingConcepts": confusing_concepts,
        "behaviorSignals": {
            "questionCount": question_count,
            "highlightCount": highlight_count,
            "noteCount": note_count,
            "artifactCount": _coerce_non_negative_int(behavior_signals.get("artifactCount")),
            "translationUsageCount": translation_usage_count,
            "recentQuestions": _normalize_string_list(behavior_signals.get("recentQuestions"))
            if isinstance(behavior_signals.get("recentQuestions"), str)
            else _coerce_list_of_strings(behavior_signals.get("recentQuestions")),
            "currentSection": _coerce_text(behavior_signals.get("currentSection")),
            "currentPage": behavior_signals.get("currentPage"),
            "activeWorkspaceTab": _coerce_text(behavior_signals.get("activeWorkspaceTab")),
        },
    }


def _build_adaptation_reason(reader_profile: dict[str, Any]) -> str:
    reasons = []
    if reader_profile.get("selfAssessedFamiliarity") != reader_profile.get("user_knowledge_level"):
        reasons.append(
            f"结合最近提问、翻译使用和笔记行为，将熟悉度从“{reader_profile.get('selfAssessedFamiliarity')}”调整为“{reader_profile.get('user_knowledge_level')}”"
        )
    if reader_profile.get("confusingConcepts"):
        reasons.append(f"优先处理当前卡点：{'、'.join(reader_profile.get('confusingConcepts')[:3])}")
    if reader_profile.get("learningGoal"):
        reasons.append(f"补课目标聚焦于“{reader_profile.get('learningGoal')}”")
    if reader_profile.get("preferredDepth"):
        reasons.append(f"输出粒度按“{reader_profile.get('preferredDepth')}”组织")
    return "；".join(reasons) if reasons else "主要依据你的自评熟悉度生成。"


