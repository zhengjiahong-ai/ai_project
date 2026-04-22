import os
import re
from typing import Any, Dict, List, Optional, Tuple

from llm.client import get_llm
from rag.store import get_rag, retrieve_hybrid_results
from schemas.requests import BackgroundKnowledgeRequest
from services.evidence_service import compact_evidence_for_response, normalize_evidence_items
from services.query_service import build_retrieval_queries
from services.trace_service import finalize_trace, record_counter, record_metric, sanitize_text, start_trace, trace_step
from services.utils import parse_json_from_llm


DEFAULT_USER_LEVEL = "一般"
ROOT_NODE_ID = "current-paper"
STAGE_ORDER = [
    "foundation",
    "method_prerequisite",
    "experiment_understanding",
    "critical_perspective",
]
STAGE_TITLES = {
    "foundation": "基础概念",
    "method_prerequisite": "方法前置",
    "experiment_understanding": "实验理解",
    "critical_perspective": "批判视角",
}
STAGE_KEYWORDS = {
    "foundation": [
        "基础",
        "概念",
        "术语",
        "定义",
        "原理",
        "背景",
        "embedding",
        "token",
        "representation",
    ],
    "method_prerequisite": [
        "方法",
        "模型",
        "算法",
        "结构",
        "框架",
        "检索",
        "图",
        "优化",
        "loss",
        "encoder",
        "decoder",
    ],
    "experiment_understanding": [
        "实验",
        "评估",
        "指标",
        "结果",
        "数据集",
        "ablation",
        "baseline",
        "benchmark",
        "metric",
    ],
    "critical_perspective": [
        "局限",
        "假设",
        "偏差",
        "风险",
        "误差",
        "泛化",
        "对比",
        "批判",
        "trade-off",
        "robustness",
    ],
}
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
LEVEL_RANK = {
    "basic": 0,
    "intermediate": 1,
    "advanced": 2,
    "target": 3,
}

RELATION_TYPE_MAP = {
    "prerequisite": "PREREQUISITE_OF",
    "prerequisite_of": "PREREQUISITE_OF",
    "supports": "SUPPORTS_READING",
    "supports_reading": "SUPPORTS_READING",
    "explains": "EXPLAINS",
    "extends": "EXTENDS",
    "related": "RELATED_TO",
}


def get_background_knowledge(request: BackgroundKnowledgeRequest) -> Dict[str, Any]:
    trace_id = start_trace(
        "background",
        request_meta={
            "pdfId": sanitize_text(request.pdfId, max_chars=80),
            "userLevel": sanitize_text(request.user_knowledge_level, max_chars=40),
            "paperTopic": sanitize_text(request.paper_topic, max_chars=120),
        },
    )
    try:
        user_level = _normalize_user_level(request.user_knowledge_level)
        normalized_pdf_id = _normalize_pdf_id(request.pdfId)
        paper_context, current_paper_sources = _load_current_paper_context(request, normalized_pdf_id)
        paper_topic = _resolve_topic(request, paper_context)
        with trace_step("build_background_query_plan", input_size=len(paper_context) + len(paper_topic)) as step:
            query_plan = build_retrieval_queries(paper_topic, context=paper_context, task_type="background")
            step["outputSize"] = len(query_plan.get("keywords") or [])
        retrieved_sources = _retrieve_related_sources(query_plan, normalized_pdf_id)

        response_sources = retrieved_sources or current_paper_sources
        response_source_type = "library" if retrieved_sources else "current_paper" if current_paper_sources else "unknown"
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
                user_level=user_level,
                paper_context=paper_context,
                rag_sources=response_rag_sources,
                request=request,
            )
            with trace_step("normalize_background_payload", input_size=len(response_rag_sources)) as step:
                payload = _normalize_payload(
                    llm_payload,
                    paper_topic=paper_topic,
                    user_level=user_level,
                    pdf_id=normalized_pdf_id,
                    rag_sources=response_rag_sources,
                )
                step["outputSize"] = len((payload.get("graph") or {}).get("nodes") or [])
        except Exception as error:
            print(f"background knowledge graph generation fell back to linear plan: {error}")
            payload = _fallback_payload(
                paper_topic=paper_topic,
                user_level=user_level,
                pdf_id=normalized_pdf_id,
                rag_sources=response_rag_sources,
                error=error,
            )

        payload["rag_sources"] = response_rag_sources
        payload["queryPlan"] = query_plan
        payload["neo4j"] = _persist_optional_neo4j(payload)
        payload["traceId"] = trace_id
        record_metric("ragSourceCount", len(response_rag_sources))
        record_metric("graphNodeCount", len((payload.get("graph") or {}).get("nodes") or []))
        finalize_trace(
            "success",
            response_meta={
                "paperTopic": sanitize_text(paper_topic, max_chars=120),
                "ragSourceCount": len(response_rag_sources),
                "graphNodeCount": len((payload.get("graph") or {}).get("nodes") or []),
            },
        )
        return payload
    except Exception as error:
        finalize_trace("error", error=error)
        raise


def _normalize_pdf_id(pdf_id: Optional[str]) -> Optional[str]:
    if not pdf_id:
        return None

    try:
        return get_rag().normalize_id(pdf_id)
    except Exception:
        return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(pdf_id)).lower()


def _load_current_paper_context(request: BackgroundKnowledgeRequest, normalized_pdf_id: Optional[str]) -> Tuple[str, List[dict]]:
    with trace_step("load_background_context", meta={"pdfId": sanitize_text(normalized_pdf_id, max_chars=80)}) as step:
        parts: List[str] = []
        sources: List[dict] = []

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
                print(f"background knowledge current-paper retrieval skipped: {error}")

        context = "\n\n".join(part for part in parts if part.strip())[:12000]
        step["outputSize"] = len(context)
        return context, sources


def _resolve_topic(request: BackgroundKnowledgeRequest, paper_context: str) -> str:
    topic = _coerce_text(request.paper_topic)
    if topic:
        return topic

    structure = request.paperStructure if isinstance(request.paperStructure, dict) else {}
    for key in ("research_problem", "core_hypothesis", "method_framework"):
        value = structure.get(key)
        if isinstance(value, list) and value:
            return ", ".join(str(item) for item in value[:3])
        if isinstance(value, str) and value.strip():
            return value.strip()[:240]

    skeleton = request.paperSkeleton if isinstance(request.paperSkeleton, dict) else {}
    for key in ("abstract", "introduction", "methods"):
        value = skeleton.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:240]

    if paper_context.strip():
        return paper_context.strip().replace("\n", " ")[:240]

    return "当前论文"


def _retrieve_related_sources(query_plan: Dict[str, Any], normalized_pdf_id: Optional[str]) -> List[dict]:
    query = query_plan.get("rewritten") or query_plan.get("original") or "prerequisite concepts background knowledge"
    try:
        with trace_step("retrieve_background_library", input_size=len(str(query or ""))) as step:
            record_counter("retrievalCalls")
            sources = _normalize_hybrid_sources(retrieve_hybrid_results(query, top_k=5))
            step["outputSize"] = len(sources)
        if sources:
            return sources
    except Exception as error:
        print(f"background knowledge related-source retrieval skipped: {error}")

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
            print(f"background knowledge filtered retrieval skipped: {error}")

    return []


def _normalize_hybrid_sources(hybrid_results: Dict[str, List[dict]]) -> List[dict]:
    vector_results = hybrid_results.get("vector", []) if isinstance(hybrid_results, dict) else []
    bm25_results = hybrid_results.get("bm25", []) if isinstance(hybrid_results, dict) else []
    evidence = normalize_evidence_items([*vector_results, *bm25_results], source_type="library", limit=10)

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
    user_level: str,
    paper_context: str,
    rag_sources: List[dict],
    request: BackgroundKnowledgeRequest,
) -> Dict[str, Any]:
    allowed_source_ids = [source.get("sourceId") for source in rag_sources if isinstance(source, dict) and source.get("sourceId")]
    source_context = "\n\n".join(
        f"{item.get('sourceId')}: {item.get('text', '')[:1200]}"
        for item in rag_sources[:5]
        if isinstance(item, dict)
    )

    prompt = f"""
You are building an AcademicRAG-style prerequisite knowledge graph before a user reads a paper.
Use the current paper context, paper structure, and RAG snippets to identify concepts the user should review first.

Return valid JSON only with this exact shape:
{{
  "paper_topic": "{paper_topic}",
  "background_knowledge": ["ordered prerequisite concept names"],
  "learning_path": [
    {{
      "step": 1,
      "stage": "foundation|method_prerequisite|experiment_understanding|critical_perspective",
      "title": "concept or task",
      "goal": "what the user should understand",
      "conceptIds": ["node-id"],
      "sourceIds": ["source-1"]
    }}
  ],
  "graph": {{
    "nodes": [
      {{
        "id": "stable-id",
        "label": "Concept label",
        "type": "paper|concept|method|theory|tool",
        "level": "basic|intermediate|advanced",
        "stage": "foundation|method_prerequisite|experiment_understanding|critical_perspective",
        "summary": "short explanation",
        "why": "why it matters for this paper",
        "sourceIds": ["source-1"]
      }}
    ],
    "links": [
      {{
        "source": "source-node-id",
        "target": "target-node-id",
        "relation": "prerequisite|supports|explains|extends|related",
        "label": "short relation label"
      }}
    ]
  }}
}}

Rules:
- Include one node with id "{ROOT_NODE_ID}" for the current paper or target topic.
- Use concise Chinese for labels, summaries, and learning goals.
- Tune the path for user level: {user_level}.
- Prefer 6 to 10 concept nodes.
- sourceIds can only use these ids: {allowed_source_ids if allowed_source_ids else []}.
- If no snippet supports a concept, use [] instead of inventing citations.

Paper topic:
{paper_topic}

Paper structure:
{_stringify_mapping(request.paperStructure) if isinstance(request.paperStructure, dict) else ""}

Paper summaries and indexed current-paper excerpts:
{paper_context[:9000]}

RAG snippets:
{source_context}
"""

    with trace_step(
        "generate_background_graph",
        input_size=len(prompt),
        meta={"userLevel": user_level, "ragSourceCount": len(rag_sources)},
    ) as step:
        raw = get_llm()._call(prompt)
        step["outputSize"] = len(str(raw or ""))
        try:
            return parse_json_from_llm(raw)
        except Exception:
            items = _parse_line_items(raw)
            if items:
                return {"background_knowledge": items}
            raise


def _normalize_payload(
    payload: Dict[str, Any],
    paper_topic: str,
    user_level: str,
    pdf_id: Optional[str],
    rag_sources: List[dict],
) -> Dict[str, Any]:
    graph, aliases = _normalize_graph(payload.get("graph"), paper_topic)
    background = _normalize_background(payload.get("background_knowledge"), graph, aliases)
    if len(graph.get("nodes", [])) <= 1 and background:
        graph = _linear_graph(paper_topic, background)
        aliases = _build_aliases_from_graph(graph)

    graph = _attach_graph_metadata(graph, rag_sources)
    sections = _normalize_learning_path_sections(payload.get("learning_path"), graph, aliases, background)
    learning_path = _flatten_learning_path_sections(sections)
    background = _background_from_sections(sections) or _normalize_background(background, graph, aliases)
    source_coverage = _build_source_coverage(graph)
    confidence = _compute_overall_confidence(graph, source_coverage)

    return {
        "status": "success",
        "pdfId": pdf_id,
        "paper_topic": str(payload.get("paper_topic") or paper_topic),
        "user_knowledge_level": user_level,
        "graph": graph,
        "learning_path": learning_path,
        "learning_path_sections": sections,
        "background_knowledge": background,
        "sourceCoverage": source_coverage,
        "confidence": confidence,
    }


def _normalize_graph(graph: Any, paper_topic: str) -> Tuple[Dict[str, list], Dict[str, str]]:
    raw_nodes = graph.get("nodes") if isinstance(graph, dict) else []
    raw_links = graph.get("links") if isinstance(graph, dict) else []
    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    node_order: List[str] = []
    aliases: Dict[str, str] = {}

    for index, node in enumerate(raw_nodes if isinstance(raw_nodes, list) else []):
        if not isinstance(node, dict):
            continue

        label = str(node.get("label") or node.get("name") or node.get("id") or f"概念 {index + 1}").strip()
        if not label:
            continue

        raw_id = str(node.get("id") or "").strip()
        is_root = raw_id == ROOT_NODE_ID or str(node.get("type") or "").strip().lower() == "paper"
        node_id = ROOT_NODE_ID if is_root else _stable_id(label or raw_id or f"concept-{index + 1}")
        if not node_id:
            node_id = f"concept-{index + 1}"

        normalized = {
            "id": node_id,
            "label": paper_topic if node_id == ROOT_NODE_ID else label,
            "type": "paper" if node_id == ROOT_NODE_ID else str(node.get("type") or "concept"),
            "level": str(node.get("level") or ("target" if node_id == ROOT_NODE_ID else "basic")),
            "stage": _normalize_stage(node.get("stage")) or _infer_stage_from_text(
                f"{label} {node.get('summary') or ''} {node.get('why') or ''}",
                index=index,
                total=max(len(raw_nodes), 1),
                is_root=node_id == ROOT_NODE_ID,
            ),
            "summary": str(node.get("summary") or ""),
            "why": str(node.get("why") or ""),
            "sourceIds": _coerce_list_of_strings(node.get("sourceIds")),
        }

        existing = nodes_by_id.get(node_id)
        nodes_by_id[node_id] = _merge_node(existing, normalized) if existing else normalized
        if node_id not in node_order:
            node_order.append(node_id)

        for alias in _alias_keys(raw_id):
            aliases[alias] = node_id
        for alias in _alias_keys(label):
            aliases[alias] = node_id
        aliases[node_id] = node_id

    if ROOT_NODE_ID not in nodes_by_id:
        nodes_by_id[ROOT_NODE_ID] = {
            "id": ROOT_NODE_ID,
            "label": paper_topic or "当前论文",
            "type": "paper",
            "level": "target",
            "stage": "critical_perspective",
            "summary": "当前论文的阅读目标。",
            "why": "所有前置概念最终都服务于理解这篇论文。",
            "sourceIds": [],
        }
        node_order.insert(0, ROOT_NODE_ID)

    aliases.update(_build_aliases_from_graph({"nodes": [nodes_by_id[node_id] for node_id in node_order], "links": []}))
    node_ids = set(node_order)
    links: List[dict] = []
    seen_links = set()

    for link in raw_links if isinstance(raw_links, list) else []:
        if not isinstance(link, dict):
            continue

        source = _resolve_alias(aliases, link.get("source"))
        target = _resolve_alias(aliases, link.get("target"))
        if source not in node_ids or target not in node_ids or source == target:
            continue

        relation = _normalize_relation(str(link.get("relation") or "related"))
        key = (source, target, relation)
        if key in seen_links:
            continue
        seen_links.add(key)
        links.append({
            "source": source,
            "target": target,
            "relation": relation,
            "label": str(link.get("label") or relation),
        })

    if not links:
        concept_ids = [node_id for node_id in node_order if node_id != ROOT_NODE_ID]
        for index, concept_id in enumerate(concept_ids):
            target = concept_ids[index + 1] if index + 1 < len(concept_ids) else ROOT_NODE_ID
            links.append({
                "source": concept_id,
                "target": target,
                "relation": "prerequisite",
                "label": "前置",
            })

    return {"nodes": [nodes_by_id[node_id] for node_id in node_order], "links": links}, aliases


def _normalize_background(value: Any, graph: Dict[str, list], aliases: Dict[str, str]) -> List[str]:
    nodes_by_id = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }

    labels: List[str] = []
    seen = set()
    raw_items = value if isinstance(value, list) else []
    for item in raw_items:
        text = _coerce_text(item)
        if not text:
            continue
        node_id = _resolve_alias(aliases, text)
        node = nodes_by_id.get(node_id) if node_id else None
        resolved_label = str(node.get("label") or text) if isinstance(node, dict) else text
        label_key = _normalize_label_key(resolved_label)
        if not label_key or label_key in seen or node_id == ROOT_NODE_ID:
            continue
        seen.add(label_key)
        labels.append(resolved_label)

    if labels:
        return labels

    ordered_nodes = [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id") != ROOT_NODE_ID and node.get("label")
    ]
    ordered_nodes.sort(key=lambda node: (STAGE_ORDER.index(_normalize_stage(node.get("stage")) or "foundation"), str(node.get("label"))))
    return [str(node.get("label")) for node in ordered_nodes]


def _normalize_learning_path_sections(
    value: Any,
    graph: Dict[str, list],
    aliases: Dict[str, str],
    background: List[str],
) -> List[dict]:
    nodes_by_id = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }
    valid_source_ids = {
        source_id
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        for source_id in _coerce_list_of_strings(node.get("sourceIds"))
    }
    sections = [{"key": key, "title": STAGE_TITLES[key], "items": []} for key in STAGE_ORDER]
    section_items = {section["key"]: section["items"] for section in sections}
    raw_items = value if isinstance(value, list) and value else background
    seen_items = set()

    for index, item in enumerate(raw_items):
        normalized_item = _normalize_learning_item(item, index, len(raw_items), nodes_by_id, aliases, valid_source_ids)
        if not normalized_item:
            continue
        dedupe_key = (normalized_item["stage"], _normalize_label_key(normalized_item["title"]))
        if dedupe_key in seen_items:
            continue
        seen_items.add(dedupe_key)
        section_items[normalized_item["stage"]].append(normalized_item)

    for label in background:
        node_id = _resolve_alias(aliases, label)
        node = nodes_by_id.get(node_id)
        if not node or node_id == ROOT_NODE_ID:
            continue
        stage = _normalize_stage(node.get("stage")) or "foundation"
        dedupe_key = (stage, _normalize_label_key(node.get("label")))
        if dedupe_key in seen_items:
            continue
        seen_items.add(dedupe_key)
        section_items[stage].append(_build_learning_item_from_node(node))

    return sections


def _normalize_learning_item(
    item: Any,
    index: int,
    total: int,
    nodes_by_id: Dict[str, Dict[str, Any]],
    aliases: Dict[str, str],
    valid_source_ids: set,
) -> Optional[Dict[str, Any]]:
    if isinstance(item, dict):
        title = str(item.get("title") or item.get("label") or item.get("name") or f"第 {index + 1} 步").strip()
        goal = str(item.get("goal") or item.get("summary") or "").strip()
        concept_ids = _normalize_concept_ids(item.get("conceptIds"), aliases, nodes_by_id)
        if not concept_ids:
            inferred_id = _resolve_alias(aliases, title)
            if inferred_id in nodes_by_id and inferred_id != ROOT_NODE_ID:
                concept_ids = [inferred_id]
        primary_node = nodes_by_id.get(concept_ids[0]) if concept_ids else None
        stage = _normalize_stage(item.get("stage")) or _normalize_stage(primary_node.get("stage") if primary_node else None)
        stage = stage or _infer_stage_from_text(f"{title} {goal}", index=index, total=total)
        source_ids = _normalize_source_ids(item.get("sourceIds"), valid_source_ids)
        if not source_ids and primary_node:
            source_ids = _coerce_list_of_strings(primary_node.get("sourceIds"))
        if not goal:
            goal = _default_goal(title, stage)
        return {
            "title": title,
            "goal": goal,
            "conceptIds": concept_ids,
            "sourceIds": source_ids,
            "stage": stage,
            "stageLabel": STAGE_TITLES[stage],
        }

    title = str(item).strip()
    if not title:
        return None
    node_id = _resolve_alias(aliases, title)
    node = nodes_by_id.get(node_id) if node_id else None
    if node and node_id != ROOT_NODE_ID:
        return _build_learning_item_from_node(node)

    stage = _infer_stage_from_text(title, index=index, total=total)
    return {
        "title": title,
        "goal": _default_goal(title, stage),
        "conceptIds": [node_id] if node_id and node_id != ROOT_NODE_ID else [],
        "sourceIds": [],
        "stage": stage,
        "stageLabel": STAGE_TITLES[stage],
    }


def _flatten_learning_path_sections(sections: List[dict]) -> List[dict]:
    flattened: List[dict] = []
    step = 1
    for section in sections:
        for item in section.get("items", []):
            flattened.append({
                "step": step,
                "title": item.get("title", f"第 {step} 步"),
                "goal": item.get("goal", ""),
                "conceptIds": item.get("conceptIds", []),
                "sourceIds": item.get("sourceIds", []),
                "stage": item.get("stage"),
                "stageLabel": item.get("stageLabel"),
            })
            step += 1
    return flattened


def _fallback_payload(
    paper_topic: str,
    user_level: str,
    pdf_id: Optional[str],
    rag_sources: List[dict],
    error: Optional[Exception] = None,
) -> Dict[str, Any]:
    fallback_prompt = f"""
Recommend prerequisite knowledge for reading a paper.

Paper topic: {paper_topic}
User knowledge level: {user_level}

Return a short ordered list, one item per line.
"""
    try:
        raw = get_llm()._call(fallback_prompt)
        background = _parse_line_items(raw)
    except Exception as fallback_error:
        print(f"background knowledge fallback LLM failed: {fallback_error}")
        background = [paper_topic, "核心术语", "方法基础", "实验或评估逻辑"]

    payload = _normalize_payload(
        {"paper_topic": paper_topic, "background_knowledge": background},
        paper_topic=paper_topic,
        user_level=user_level,
        pdf_id=pdf_id,
        rag_sources=rag_sources,
    )
    payload["fallback_reason"] = str(error)[:300] if error else ""
    return payload


def _linear_graph(paper_topic: str, background: List[str]) -> Dict[str, list]:
    nodes = [{
        "id": ROOT_NODE_ID,
        "label": paper_topic or "当前论文",
        "type": "paper",
        "level": "target",
        "stage": "critical_perspective",
        "summary": "当前论文的阅读目标。",
        "why": "所有前置概念最终都服务于理解这篇论文。",
        "sourceIds": [],
    }]

    total = max(len(background), 1)
    for index, label in enumerate(background):
        stage = _infer_stage_from_text(label, index=index, total=total)
        nodes.append({
            "id": _stable_id(label) or f"concept-{index + 1}",
            "label": label,
            "type": "concept",
            "level": "basic",
            "stage": stage,
            "summary": "",
            "why": "阅读当前论文前建议先补齐这一概念。",
            "sourceIds": [],
        })

    links = []
    concept_ids = [node["id"] for node in nodes if node["id"] != ROOT_NODE_ID]
    for index, concept_id in enumerate(concept_ids):
        links.append({
            "source": concept_id,
            "target": concept_ids[index + 1] if index + 1 < len(concept_ids) else ROOT_NODE_ID,
            "relation": "prerequisite",
            "label": "前置",
        })

    return {"nodes": nodes, "links": links}


def _attach_graph_metadata(graph: Dict[str, list], rag_sources: List[dict]) -> Dict[str, list]:
    valid_source_ids = {
        item.get("sourceId")
        for item in rag_sources
        if isinstance(item, dict) and item.get("sourceId")
    }
    normalized_nodes = []

    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue

        stage = _normalize_stage(node.get("stage")) or _infer_stage_from_text(
            f"{node.get('label') or ''} {node.get('summary') or ''} {node.get('why') or ''}",
            is_root=node.get("id") == ROOT_NODE_ID,
        )
        source_ids = _normalize_source_ids(node.get("sourceIds"), valid_source_ids)
        if node.get("id") != ROOT_NODE_ID and not source_ids:
            source_ids = _match_source_ids(node, rag_sources)

        normalized = {
            **node,
            "stage": stage,
            "stageLabel": STAGE_TITLES[stage],
            "sourceIds": source_ids,
        }
        normalized["confidence"] = _compute_node_confidence(normalized)
        normalized_nodes.append(normalized)

    return {"nodes": normalized_nodes, "links": graph.get("links", [])}


def _build_source_coverage(graph: Dict[str, list]) -> Dict[str, Any]:
    concept_nodes = [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id") != ROOT_NODE_ID
    ]
    total = len(concept_nodes)
    covered = [node for node in concept_nodes if _coerce_list_of_strings(node.get("sourceIds"))]
    uncovered = [str(node.get("id")) for node in concept_nodes if not _coerce_list_of_strings(node.get("sourceIds"))]

    return {
        "totalConcepts": total,
        "conceptsWithSources": len(covered),
        "ratio": round(len(covered) / total, 2) if total else 0.0,
        "uncoveredConceptIds": uncovered,
    }


def _compute_overall_confidence(graph: Dict[str, list], source_coverage: Dict[str, Any]) -> float:
    concept_nodes = [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id") != ROOT_NODE_ID
    ]
    if not concept_nodes:
        return 0.0

    average_node_confidence = sum(float(node.get("confidence") or 0.0) for node in concept_nodes) / len(concept_nodes)
    coverage_ratio = float(source_coverage.get("ratio") or 0.0)
    return round(min(0.99, average_node_confidence * 0.6 + coverage_ratio * 0.4), 2)


def _persist_optional_neo4j(payload: Dict[str, Any]) -> Dict[str, Any]:
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


def _write_graph_tx(tx, payload: Dict[str, Any], graph: Dict[str, list]) -> None:
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
                c.sourceIds = $sourceIds
            WITH c
            MATCH (p:Paper {id: $paper_id})
            MERGE (p)-[:HAS_BACKGROUND_NODE]->(c)
            """,
            paper_id=paper_id,
            **node,
        )

    for link in graph.get("links", []):
        relation_type = RELATION_TYPE_MAP.get(_normalize_relation(link.get("relation")), "RELATED_TO")
        tx.run(
            f"""
            MATCH (source:Concept {{id: $source}})
            MATCH (target:Concept {{id: $target}})
            MERGE (source)-[r:{relation_type}]->(target)
            SET r.label = $label,
                r.relation = $relation
            """,
            source=link.get("source"),
            target=link.get("target"),
            label=link.get("label"),
            relation=link.get("relation"),
        )


def _parse_line_items(raw: str) -> List[str]:
    return [
        item.strip("-* 0123456789.、").strip()
        for item in (raw or "").splitlines()
        if item.strip("-* 0123456789.、").strip()
    ]


def _normalize_user_level(value: Any) -> str:
    text = _coerce_text(value).lower()
    return USER_LEVEL_ALIASES.get(text, DEFAULT_USER_LEVEL)


def _merge_node(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    merged["label"] = candidate["label"] if len(candidate.get("label", "")) > len(existing.get("label", "")) else existing["label"]
    merged["type"] = _preferred_type(existing.get("type"), candidate.get("type"))
    merged["level"] = _preferred_level(existing.get("level"), candidate.get("level"))
    merged["stage"] = candidate.get("stage") if existing.get("stage") == "foundation" and candidate.get("stage") else existing.get("stage")
    merged["summary"] = candidate["summary"] if len(candidate.get("summary", "")) > len(existing.get("summary", "")) else existing.get("summary", "")
    merged["why"] = candidate["why"] if len(candidate.get("why", "")) > len(existing.get("why", "")) else existing.get("why", "")
    merged["sourceIds"] = _dedupe_strings([*existing.get("sourceIds", []), *candidate.get("sourceIds", [])])
    return merged


def _preferred_type(existing_type: Any, candidate_type: Any) -> str:
    existing = str(existing_type or "concept")
    candidate = str(candidate_type or "concept")
    if existing == "paper" or candidate == "paper":
        return "paper"
    if existing == "concept" and candidate != "concept":
        return candidate
    return existing


def _preferred_level(existing_level: Any, candidate_level: Any) -> str:
    existing = str(existing_level or "basic")
    candidate = str(candidate_level or "basic")
    return candidate if LEVEL_RANK.get(candidate, 0) > LEVEL_RANK.get(existing, 0) else existing


def _build_aliases_from_graph(graph: Dict[str, list]) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        label = str(node.get("label") or "").strip()
        for alias in _alias_keys(node_id):
            aliases[alias] = node_id
        for alias in _alias_keys(label):
            aliases[alias] = node_id
        aliases[node_id] = node_id
    return aliases


def _alias_keys(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    keys = [text, text.lower()]
    normalized_key = _normalize_label_key(text)
    stable_key = _stable_id(text)
    if normalized_key:
        keys.append(normalized_key)
    if stable_key:
        keys.append(stable_key)
    return _dedupe_strings(keys)


def _resolve_alias(aliases: Dict[str, str], value: Any) -> Optional[str]:
    for key in _alias_keys(value):
        if key in aliases:
            return aliases[key]
    return None


def _normalize_concept_ids(value: Any, aliases: Dict[str, str], nodes_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
    concept_ids: List[str] = []
    raw_items = value if isinstance(value, list) else []
    for item in raw_items:
        resolved_id = _resolve_alias(aliases, item)
        if resolved_id and resolved_id in nodes_by_id and resolved_id != ROOT_NODE_ID and resolved_id not in concept_ids:
            concept_ids.append(resolved_id)
    return concept_ids


def _normalize_source_ids(value: Any, valid_source_ids: set) -> List[str]:
    if not valid_source_ids:
        return []
    return [
        source_id
        for source_id in _coerce_list_of_strings(value)
        if source_id in valid_source_ids
    ]


def _match_source_ids(node: Dict[str, Any], rag_sources: List[dict]) -> List[str]:
    label_key = _normalize_label_key(node.get("label"))
    if not label_key:
        return []

    matches = []
    label_tokens = [token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", label_key) if token]
    for item in rag_sources:
        if not isinstance(item, dict):
            continue
        source_id = item.get("sourceId")
        source_text = _normalize_label_key(item.get("text"))
        if not source_id or not source_text:
            continue
        if label_key in source_text:
            matches.append(source_id)
            continue
        if label_tokens and all(token in source_text for token in label_tokens):
            matches.append(source_id)

    return _dedupe_strings(matches)


def _build_learning_item_from_node(node: Dict[str, Any]) -> Dict[str, Any]:
    stage = _normalize_stage(node.get("stage")) or "foundation"
    title = str(node.get("label") or "概念")
    goal = str(node.get("why") or node.get("summary") or _default_goal(title, stage))
    return {
        "title": title,
        "goal": goal,
        "conceptIds": [str(node.get("id"))] if node.get("id") and node.get("id") != ROOT_NODE_ID else [],
        "sourceIds": _coerce_list_of_strings(node.get("sourceIds")),
        "stage": stage,
        "stageLabel": STAGE_TITLES[stage],
    }


def _background_from_sections(sections: List[dict]) -> List[str]:
    background: List[str] = []
    seen = set()
    for section in sections:
        for item in section.get("items", []):
            label = str(item.get("title") or "").strip()
            key = _normalize_label_key(label)
            if not key or key in seen:
                continue
            seen.add(key)
            background.append(label)
    return background


def _default_goal(title: str, stage: str) -> str:
    if stage == "foundation":
        return f"先掌握“{title}”的核心定义、基本作用和常见术语。"
    if stage == "method_prerequisite":
        return f"重点理解“{title}”在方法流程中的输入、输出和关键机制。"
    if stage == "experiment_understanding":
        return f"补齐“{title}”相关的实验设置、指标解释和结果阅读方式。"
    return f"从假设、局限和适用边界角度重新审视“{title}”。"


def _normalize_stage(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text if text in STAGE_TITLES else None


def _infer_stage_from_text(text: Any, index: int = 0, total: int = 1, is_root: bool = False) -> str:
    if is_root:
        return "critical_perspective"

    combined = _normalize_label_key(text)
    for stage in STAGE_ORDER:
        if any(keyword in combined for keyword in STAGE_KEYWORDS[stage]):
            return stage

    if total <= 1:
        return "foundation"

    ratio = index / max(total - 1, 1)
    if ratio < 0.34:
        return "foundation"
    if ratio < 0.68:
        return "method_prerequisite"
    if ratio < 0.84:
        return "experiment_understanding"
    return "critical_perspective"


def _compute_node_confidence(node: Dict[str, Any]) -> float:
    if node.get("id") == ROOT_NODE_ID:
        return 1.0

    score = 0.35
    if _coerce_list_of_strings(node.get("sourceIds")):
        score += 0.25
    if str(node.get("summary") or "").strip():
        score += 0.15
    if str(node.get("why") or "").strip():
        score += 0.15
    if len(_coerce_list_of_strings(node.get("sourceIds"))) >= 2:
        score += 0.05

    return round(min(0.95, score), 2)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return ", ".join(_coerce_text(item) for item in value if _coerce_text(item)).strip()
    if isinstance(value, dict):
        for key in ("title", "name", "label", "value", "text", "summary"):
            text = _coerce_text(value.get(key))
            if text:
                return text
        return _stringify_mapping(value).replace("\n", "; ").strip()
    return str(value).strip()


def _stringify_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    lines = []
    for key, item in value.items():
        if item is None:
            continue
        lines.append(f"{key}: {str(item)[:900]}")
    return "\n".join(lines)


def _stable_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text).strip("-")
    return text[:80]


def _normalize_label_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def _normalize_relation(value: Any) -> str:
    relation = str(value or "related").strip().lower().replace(" ", "_").replace("-", "_")
    if relation in RELATION_TYPE_MAP:
        return relation
    return "related"


def _coerce_list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return _dedupe_strings([str(item).strip() for item in value if str(item).strip()])


def _dedupe_strings(values: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped
