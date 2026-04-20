import os
import re
from typing import Any, Dict, List, Optional

from llm.client import get_llm
from rag.store import get_rag, retrieve_hybrid_for_vector
from schemas.requests import BackgroundKnowledgeRequest
from services.utils import parse_json_from_llm


DEFAULT_USER_LEVEL = "普通/一般"
ROOT_NODE_ID = "current-paper"

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
    user_level = _coerce_text(request.user_knowledge_level) or DEFAULT_USER_LEVEL
    normalized_pdf_id = _normalize_pdf_id(request.pdfId)
    paper_context, current_paper_sources = _load_current_paper_context(request, normalized_pdf_id)
    paper_topic = _resolve_topic(request, paper_context)
    rag_sources = _retrieve_related_sources(paper_topic, normalized_pdf_id)

    try:
        llm_payload = _generate_graph_payload(
            paper_topic=paper_topic,
            user_level=user_level,
            paper_context=paper_context,
            rag_sources=rag_sources,
            request=request,
        )
        payload = _normalize_payload(llm_payload, paper_topic, user_level, normalized_pdf_id)
    except Exception as error:
        print(f"background knowledge graph generation fell back to linear plan: {error}")
        payload = _fallback_payload(
            paper_topic=paper_topic,
            user_level=user_level,
            pdf_id=normalized_pdf_id,
            error=error,
        )

    payload["rag_sources"] = _compact_sources(rag_sources or current_paper_sources)
    payload["neo4j"] = _persist_optional_neo4j(payload)
    return payload


def _normalize_pdf_id(pdf_id: Optional[str]) -> Optional[str]:
    if not pdf_id:
        return None

    try:
        return get_rag().normalize_id(pdf_id)
    except Exception:
        return re.sub(r"[^a-zA-Z0-9.\-_]", "_", str(pdf_id)).lower()


def _load_current_paper_context(request: BackgroundKnowledgeRequest, normalized_pdf_id: Optional[str]) -> tuple[str, List[dict]]:
    parts: List[str] = []
    sources: List[dict] = []

    if isinstance(request.paperStructure, dict) and request.paperStructure:
        parts.append(f"Paper structure:\n{_stringify_mapping(request.paperStructure)}")

    if isinstance(request.paperSkeleton, dict) and request.paperSkeleton:
        parts.append(f"Paper section summaries:\n{_stringify_mapping(request.paperSkeleton)}")

    if normalized_pdf_id:
        try:
            documents = get_rag().get_documents_by_metadata({"id": normalized_pdf_id}, limit=40)
            sources = documents[:5]
            document_text = "\n\n".join(item.get("text", "") for item in documents if item.get("text"))
            if document_text.strip():
                parts.append(f"Current indexed paper excerpts:\n{document_text[:9000]}")
        except Exception as error:
            print(f"background knowledge current-paper retrieval skipped: {error}")

    return "\n\n".join(part for part in parts if part.strip())[:12000], sources


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


def _retrieve_related_sources(paper_topic: str, normalized_pdf_id: Optional[str]) -> List[dict]:
    query = f"prerequisite concepts background knowledge for {paper_topic}"
    try:
        return retrieve_hybrid_for_vector(query, top_k=5)
    except Exception as error:
        print(f"background knowledge related-source retrieval skipped: {error}")

    if normalized_pdf_id:
        try:
            return get_rag().retrieve(query, top_k=5, filter_metadata={"id": normalized_pdf_id})
        except Exception as error:
            print(f"background knowledge filtered retrieval skipped: {error}")

    return []


def _generate_graph_payload(
    paper_topic: str,
    user_level: str,
    paper_context: str,
    rag_sources: List[dict],
    request: BackgroundKnowledgeRequest,
) -> Dict[str, Any]:
    source_context = "\n\n".join(
        f"Source {index + 1}: {item.get('text', '')[:1200]}"
        for index, item in enumerate(rag_sources[:5])
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
    {{"step": 1, "title": "concept or task", "goal": "what the user should understand", "conceptIds": ["node-id"]}}
  ],
  "graph": {{
    "nodes": [
      {{"id": "stable-id", "label": "Concept label", "type": "paper|concept|method|theory|tool", "level": "basic|intermediate|advanced", "summary": "short explanation", "why": "why it matters for this paper", "sourceIds": ["source-1"]}}
    ],
    "links": [
      {{"source": "source-node-id", "target": "target-node-id", "relation": "prerequisite|supports|explains|extends|related", "label": "short relation label"}}
    ]
  }}
}}

Rules:
- Include one node with id "{ROOT_NODE_ID}" for the current paper or target topic.
- Use concise Chinese for labels, summaries, and learning goals.
- Tune the path for user level: {user_level}.
- Prefer 6 to 10 concept nodes. Avoid invented citations.

Paper topic:
{paper_topic}

Paper structure:
{_stringify_mapping(request.paperStructure) if isinstance(request.paperStructure, dict) else ""}

Paper summaries and indexed current-paper excerpts:
{paper_context[:9000]}

RAG snippets:
{source_context}
"""

    raw = get_llm()._call(prompt)
    try:
        return parse_json_from_llm(raw)
    except Exception:
        items = _parse_line_items(raw)
        if items:
            return {"background_knowledge": items}
        raise


def _normalize_payload(payload: Dict[str, Any], paper_topic: str, user_level: str, pdf_id: Optional[str]) -> Dict[str, Any]:
    graph = _normalize_graph(payload.get("graph"), paper_topic)
    background = _normalize_background(payload.get("background_knowledge"), graph)
    if len(graph.get("nodes", [])) <= 1 and background:
        graph = _linear_graph(paper_topic, background)
    learning_path = _normalize_learning_path(payload.get("learning_path"), graph, background)

    return {
        "status": "success",
        "pdfId": pdf_id,
        "paper_topic": str(payload.get("paper_topic") or paper_topic),
        "user_knowledge_level": user_level,
        "graph": graph,
        "learning_path": learning_path,
        "background_knowledge": background,
    }


def _normalize_graph(graph: Any, paper_topic: str) -> Dict[str, list]:
    raw_nodes = graph.get("nodes") if isinstance(graph, dict) else []
    raw_links = graph.get("links") if isinstance(graph, dict) else []
    nodes: List[dict] = []
    aliases: Dict[str, str] = {}

    for index, node in enumerate(raw_nodes if isinstance(raw_nodes, list) else []):
        if not isinstance(node, dict):
            continue

        label = str(node.get("label") or node.get("name") or node.get("id") or f"概念 {index + 1}").strip()
        node_id = _stable_id(node.get("id") or label or f"concept-{index + 1}")
        if not node_id:
            node_id = f"concept-{index + 1}"
        while any(item["id"] == node_id for item in nodes):
            node_id = f"{node_id}-{index + 1}"

        normalized = {
            "id": node_id,
            "label": label,
            "type": str(node.get("type") or ("paper" if node_id == ROOT_NODE_ID else "concept")),
            "level": str(node.get("level") or "basic"),
            "summary": str(node.get("summary") or ""),
            "why": str(node.get("why") or ""),
            "sourceIds": node.get("sourceIds") if isinstance(node.get("sourceIds"), list) else [],
        }
        nodes.append(normalized)
        aliases[str(node.get("id") or "")] = node_id
        aliases[label] = node_id

    if not any(node["id"] == ROOT_NODE_ID for node in nodes):
        nodes.insert(0, {
            "id": ROOT_NODE_ID,
            "label": paper_topic or "当前论文",
            "type": "paper",
            "level": "target",
            "summary": "当前论文的阅读目标。",
            "why": "所有前置概念最终都服务于理解这篇论文。",
            "sourceIds": [],
        })
        aliases[ROOT_NODE_ID] = ROOT_NODE_ID

    links: List[dict] = []
    for link in raw_links if isinstance(raw_links, list) else []:
        if not isinstance(link, dict):
            continue

        source = aliases.get(str(link.get("source")), _stable_id(link.get("source")))
        target = aliases.get(str(link.get("target")), _stable_id(link.get("target")))
        node_ids = {node["id"] for node in nodes}
        if source not in node_ids or target not in node_ids or source == target:
            continue

        relation = _normalize_relation(str(link.get("relation") or "related"))
        links.append({
            "source": source,
            "target": target,
            "relation": relation,
            "label": str(link.get("label") or relation),
        })

    if not links:
        concept_ids = [node["id"] for node in nodes if node["id"] != ROOT_NODE_ID]
        for index, concept_id in enumerate(concept_ids):
            target = concept_ids[index + 1] if index + 1 < len(concept_ids) else ROOT_NODE_ID
            links.append({
                "source": concept_id,
                "target": target,
                "relation": "prerequisite",
                "label": "前置",
            })

    return {"nodes": nodes, "links": links}


def _normalize_background(value: Any, graph: Dict[str, list]) -> List[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if items:
            return items

    return [
        node["label"]
        for node in graph.get("nodes", [])
        if node.get("id") != ROOT_NODE_ID and node.get("label")
    ]


def _normalize_learning_path(value: Any, graph: Dict[str, list], background: List[str]) -> List[dict]:
    if isinstance(value, list) and value:
        path = []
        for index, item in enumerate(value):
            if isinstance(item, dict):
                path.append({
                    "step": int(item.get("step") or index + 1),
                    "title": str(item.get("title") or item.get("label") or f"第 {index + 1} 步"),
                    "goal": str(item.get("goal") or item.get("summary") or ""),
                    "conceptIds": item.get("conceptIds") if isinstance(item.get("conceptIds"), list) else [],
                })
            else:
                path.append({"step": index + 1, "title": str(item), "goal": "", "conceptIds": []})
        return path

    label_to_id = {node.get("label"): node.get("id") for node in graph.get("nodes", [])}
    return [
        {
            "step": index + 1,
            "title": label,
            "goal": f"先补齐“{label}”的核心定义、适用场景和常见误区。",
            "conceptIds": [label_to_id[label]] if label in label_to_id else [],
        }
        for index, label in enumerate(background)
    ]


def _fallback_payload(
    paper_topic: str,
    user_level: str,
    pdf_id: Optional[str],
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

    graph = _linear_graph(paper_topic, background)
    return {
        "status": "success",
        "pdfId": pdf_id,
        "paper_topic": paper_topic,
        "user_knowledge_level": user_level,
        "graph": graph,
        "learning_path": _normalize_learning_path([], graph, background),
        "background_knowledge": background,
        "fallback_reason": str(error)[:300] if error else "",
    }


def _linear_graph(paper_topic: str, background: List[str]) -> Dict[str, list]:
    nodes = [{
        "id": ROOT_NODE_ID,
        "label": paper_topic or "当前论文",
        "type": "paper",
        "level": "target",
        "summary": "当前论文的阅读目标。",
        "why": "所有前置概念最终都服务于理解这篇论文。",
        "sourceIds": [],
    }]

    for index, label in enumerate(background):
        nodes.append({
            "id": f"concept-{index + 1}",
            "label": label,
            "type": "concept",
            "level": "basic",
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


def _persist_optional_neo4j(payload: Dict[str, Any]) -> Dict[str, Any]:
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not uri or not user or not password:
        return {
            "enabled": False,
            "status": "skipped",
            "message": "NEO4J_URI, NEO4J_USER, or NEO4J_PASSWORD is not configured.",
        }

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(user, password))
        graph = payload.get("graph", {})
        with driver.session() as session:
            session.execute_write(_write_graph_tx, payload, graph)
        driver.close()
        return {"enabled": True, "status": "success", "message": "Knowledge graph persisted to Neo4j."}
    except Exception as error:
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
                c.why = $why
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


def _compact_sources(sources: List[dict]) -> List[dict]:
    compacted = []
    for index, item in enumerate(sources[:5] if isinstance(sources, list) else []):
        if not isinstance(item, dict):
            continue
        compacted.append({
            "id": f"source-{index + 1}",
            "text": str(item.get("text") or "")[:700],
            "metadata": item.get("metadata") or {},
            "similarity": item.get("similarity"),
            "score": item.get("score"),
        })
    return compacted


def _parse_line_items(raw: str) -> List[str]:
    return [
        item.strip("-* 0123456789.、").strip()
        for item in (raw or "").splitlines()
        if item.strip("-* 0123456789.、").strip()
    ]


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


def _normalize_relation(value: Any) -> str:
    relation = str(value or "related").strip().lower().replace(" ", "_").replace("-", "_")
    if relation in RELATION_TYPE_MAP:
        return relation
    return "related"
