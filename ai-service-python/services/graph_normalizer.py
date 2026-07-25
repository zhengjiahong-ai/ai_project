"""
Graph normalization and validation for background knowledge service.

Handles graph structure normalization, prerequisite edge validation,
learning path construction, and metadata attachment. Called by the main
`get_background_knowledge` function in background_knowledge_service.py.
"""

import logging
import re
from typing import Any

from llm.client import get_llm
from services.knowledge_graph_service import build_provenance_summary

_logger = logging.getLogger(__name__)

DEFAULT_USER_LEVEL = "一般"
DEFAULT_PREFERRED_DEPTH = "标准"
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


def _normalize_payload(
    payload: dict[str, Any],
    paper_topic: str,
    reader_profile: dict[str, Any],
    pdf_id: str | None,
    rag_sources: list[dict],
) -> dict[str, Any]:
    user_level = str(reader_profile.get("user_knowledge_level") or DEFAULT_USER_LEVEL)
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
        "reader_profile": {
            "selfAssessedFamiliarity": reader_profile.get("selfAssessedFamiliarity") or user_level,
            "preferredDepth": reader_profile.get("preferredDepth") or DEFAULT_PREFERRED_DEPTH,
            "learningGoal": reader_profile.get("learningGoal") or "",
            "knownConcepts": _coerce_list_of_strings(reader_profile.get("knownConcepts")),
            "confusingConcepts": _coerce_list_of_strings(reader_profile.get("confusingConcepts")),
        },
        "graph": graph,
        "learning_path": learning_path,
        "learning_path_sections": sections,
        "background_knowledge": background,
        "sourceCoverage": source_coverage,
        "confidence": confidence,
        "provenanceSummary": build_provenance_summary(graph),
        "warnings": payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
        "externalKnowledge": payload.get("externalKnowledge") or {
            "enabled": False,
            "status": "disabled",
            "message": "External academic retrieval is not enabled.",
        },
    }


def _normalize_graph(graph: Any, paper_topic: str) -> tuple[dict[str, list], dict[str, str]]:
    raw_nodes = graph.get("nodes") if isinstance(graph, dict) else []
    raw_links = graph.get("links") if isinstance(graph, dict) else []
    raw_edges = graph.get("edges") if isinstance(graph, dict) else []
    suppress_implicit_edges = bool(graph.get("suppressImplicitEdges")) if isinstance(graph, dict) else False
    nodes_by_id: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    aliases: dict[str, str] = {}

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
            "provenanceStatus": str(node.get("provenanceStatus") or ""),
            "confidence": node.get("confidence"),
            "confidenceReason": str(node.get("confidenceReason") or ""),
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
    links: list[dict] = []
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
            "sourceIds": _coerce_list_of_strings(link.get("sourceIds")),
            "provenanceStatus": str(link.get("provenanceStatus") or ""),
            "confidence": link.get("confidence"),
            "confidenceReason": str(link.get("confidenceReason") or ""),
        })

    if not links and not suppress_implicit_edges:
        concept_ids = [node_id for node_id in node_order if node_id != ROOT_NODE_ID]
        for index, concept_id in enumerate(concept_ids):
            target = concept_ids[index + 1] if index + 1 < len(concept_ids) else ROOT_NODE_ID
            links.append({
                "source": concept_id,
                "target": target,
                "relation": "prerequisite",
                "label": "前置",
            })

    edges = _normalize_prerequisite_edges(raw_edges, links, aliases, node_ids)

    return {"nodes": [nodes_by_id[node_id] for node_id in node_order], "links": links, "edges": edges}, aliases


def _normalize_prerequisite_edges(
    raw_edges: Any,
    links: list[dict],
    aliases: dict[str, str],
    node_ids: set,
) -> list[dict]:
    edges: list[dict] = []
    seen_edges = set()

    edge_candidates = raw_edges if isinstance(raw_edges, list) else []
    link_candidates = [
        {**link, "type": "prerequisite"}
        for link in links
        if isinstance(link, dict) and _normalize_relation(link.get("relation")) == "prerequisite"
    ]

    for item in [*edge_candidates, *link_candidates]:
        if not isinstance(item, dict):
            continue

        edge_type = str(item.get("type") or item.get("relation") or "").strip().lower().replace("-", "_")
        if edge_type != "prerequisite":
            continue

        source = _resolve_alias(aliases, item.get("source"))
        target = _resolve_alias(aliases, item.get("target"))
        if source not in node_ids or target not in node_ids or source == target:
            continue

        key = (source, target, "prerequisite")
        if key in seen_edges:
            continue
        seen_edges.add(key)

        confidence_reason = str(item.get("confidenceReason") or item.get("reason") or "").strip()
        edges.append({
            "source": source,
            "target": target,
            "type": "prerequisite",
            "sourceIds": _coerce_list_of_strings(item.get("sourceIds")),
            "confidenceReason": confidence_reason,
            "provenanceStatus": str(item.get("provenanceStatus") or ""),
            "confidence": item.get("confidence"),
        })

    return edges


def _normalize_background(value: Any, graph: dict[str, list], aliases: dict[str, str]) -> list[str]:
    nodes_by_id = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }

    labels: list[str] = []
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
    graph: dict[str, list],
    aliases: dict[str, str],
    background: list[str],
) -> list[dict]:
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
    nodes_by_id: dict[str, dict[str, Any]],
    aliases: dict[str, str],
    valid_source_ids: set,
) -> dict[str, Any] | None:
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


def _flatten_learning_path_sections(sections: list[dict]) -> list[dict]:
    flattened: list[dict] = []
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
    reader_profile: dict[str, Any],
    pdf_id: str | None,
    rag_sources: list[dict],
    error: Exception | None = None,
) -> dict[str, Any]:
    # Lazy import to avoid circular dependency at module level.
    from services.background_knowledge_service import _parse_line_items

    user_level = str(reader_profile.get("user_knowledge_level") or DEFAULT_USER_LEVEL)
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
        _logger.error(f"background knowledge fallback LLM failed: {fallback_error}")
        background = [paper_topic, "核心术语", "方法基础", "实验或评估逻辑"]

    payload = _normalize_payload(
        {
            "paper_topic": paper_topic,
            "background_knowledge": background,
            "warnings": ["概念发现失败，已使用背景主题降级结果。"],
        },
        paper_topic=paper_topic,
        reader_profile=reader_profile,
        pdf_id=pdf_id,
        rag_sources=rag_sources,
    )
    payload["fallback_reason"] = str(error)[:300] if error else ""
    return payload


def _linear_graph(paper_topic: str, background: list[str]) -> dict[str, list]:
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

    edges = [
        {
            "source": link["source"],
            "target": link["target"],
            "type": "prerequisite",
            "sourceIds": [],
            "confidenceReason": "根据补课清单顺序推断的前置学习关系。",
        }
        for link in links
        if _normalize_relation(link.get("relation")) == "prerequisite"
    ]

    return {"nodes": nodes, "links": links, "edges": edges}


def _attach_graph_metadata(graph: dict[str, list], rag_sources: list[dict]) -> dict[str, list]:
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
        provenance_status = _resolve_provenance_status(node.get("provenanceStatus"), source_ids)
        normalized["provenanceStatus"] = provenance_status
        normalized["confidence"] = min(
            _coerce_confidence(node.get("confidence"), _compute_node_confidence(normalized)),
            _provenance_confidence_cap(provenance_status),
        )
        normalized["confidenceReason"] = str(
            node.get("confidenceReason")
            or ("当前论文片段支持该概念。" if source_ids else "模型根据当前论文推断的隐含前置概念。")
        )
        normalized_nodes.append(normalized)

    normalized_edges = _attach_edge_metadata(graph.get("edges", []), normalized_nodes, valid_source_ids)

    return {"nodes": normalized_nodes, "links": graph.get("links", []), "edges": normalized_edges}


def _attach_edge_metadata(edges: Any, nodes: list[dict], valid_source_ids: set) -> list[dict]:
    node_map = {
        str(node.get("id")): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }
    normalized_edges: list[dict] = []
    seen_edges = set()

    for edge in edges if isinstance(edges, list) else []:
        if not isinstance(edge, dict):
            continue

        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source not in node_map or target not in node_map or source == target:
            continue

        edge_type = str(edge.get("type") or "").strip().lower().replace("-", "_")
        if edge_type != "prerequisite":
            continue

        key = (source, target, "prerequisite")
        if key in seen_edges:
            continue
        seen_edges.add(key)

        confidence_reason = str(edge.get("confidenceReason") or "").strip()
        source_ids = _normalize_source_ids(edge.get("sourceIds"), valid_source_ids)
        if not source_ids and not confidence_reason:
            source_node = node_map.get(source) or {}
            source_ids = _normalize_source_ids(source_node.get("sourceIds"), valid_source_ids)
        if not source_ids and not confidence_reason:
            confidence_reason = "根据概念顺序、阶段和学习路径推断的前置关系。"

        normalized_edges.append({
            "source": source,
            "target": target,
            "type": "prerequisite",
            "sourceIds": source_ids,
            "confidenceReason": confidence_reason,
            "provenanceStatus": _resolve_provenance_status(edge.get("provenanceStatus"), source_ids),
            "confidence": min(
                _coerce_confidence(edge.get("confidence"), 0.6 if not source_ids else 0.85),
                _provenance_confidence_cap(_resolve_provenance_status(edge.get("provenanceStatus"), source_ids)),
            ),
        })

    return normalized_edges


def _resolve_provenance_status(value: Any, source_ids: list[str]) -> str:
    if source_ids:
        return "current_paper_supported"
    normalized = str(value or "").strip()
    if normalized == "external_supported":
        return normalized
    return "model_inference"


def _provenance_confidence_cap(status: str) -> float:
    return {
        "model_inference": 0.60,
        "current_paper_supported": 0.85,
        "external_supported": 0.95,
    }.get(status, 0.60)


def _coerce_confidence(value: Any, fallback: float) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 2)
    except (TypeError, ValueError):
        return round(max(0.0, min(1.0, float(fallback))), 2)


def _build_source_coverage(graph: dict[str, list]) -> dict[str, Any]:
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


def _compute_overall_confidence(graph: dict[str, list], source_coverage: dict[str, Any]) -> float:
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

def _merge_node(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
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


def _build_aliases_from_graph(graph: dict[str, list]) -> dict[str, str]:
    aliases: dict[str, str] = {}
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


def _alias_keys(value: Any) -> list[str]:
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


def _resolve_alias(aliases: dict[str, str], value: Any) -> str | None:
    for key in _alias_keys(value):
        if key in aliases:
            return aliases[key]
    return None


def _normalize_concept_ids(value: Any, aliases: dict[str, str], nodes_by_id: dict[str, dict[str, Any]]) -> list[str]:
    concept_ids: list[str] = []
    raw_items = value if isinstance(value, list) else []
    for item in raw_items:
        resolved_id = _resolve_alias(aliases, item)
        if resolved_id and resolved_id in nodes_by_id and resolved_id != ROOT_NODE_ID and resolved_id not in concept_ids:
            concept_ids.append(resolved_id)
    return concept_ids


def _normalize_source_ids(value: Any, valid_source_ids: set) -> list[str]:
    if not valid_source_ids:
        return []
    return [
        source_id
        for source_id in _coerce_list_of_strings(value)
        if source_id in valid_source_ids
    ]


def _match_source_ids(node: dict[str, Any], rag_sources: list[dict]) -> list[str]:
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


def _build_learning_item_from_node(node: dict[str, Any]) -> dict[str, Any]:
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


def _background_from_sections(sections: list[dict]) -> list[str]:
    background: list[str] = []
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


def _normalize_stage(value: Any) -> str | None:
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


def _compute_node_confidence(node: dict[str, Any]) -> float:
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


def _coerce_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe_strings([str(item).strip() for item in value if str(item).strip()])


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped
