import copy
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from services.knowledge_graph_service import build_provenance_summary


DEFAULT_MAX_NODES = 8
DEFAULT_MAX_EDGES = 12
CONTEXT_NOTE = "图谱邻域仅用于解释背景和来源覆盖，不代表自动裁决；冲突仍需人工核查。"
SEED_STOPWORDS = {
    "about", "actual", "candidate", "claim", "conclusion", "conflict", "cross", "current",
    "different", "evidence", "major", "paper", "papers", "related", "source", "sources",
    "存在", "不同", "冲突", "相关", "结论", "证据", "来源", "需要", "人工", "核查",
}


def save_graph_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    pdf_id = _clean_text(payload.get("pdfId"))
    graph = payload.get("graph")
    if not pdf_id or not isinstance(graph, dict):
        return {"enabled": True, "status": "skipped", "message": "A pdfId and graph are required."}

    try:
        db_path = _knowledge_graph_db_path()
        _initialize_storage(db_path)
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute(
                """
                INSERT INTO knowledge_graph_snapshots (pdf_id, paper_topic, graph_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pdf_id) DO UPDATE SET
                    paper_topic=excluded.paper_topic,
                    graph_json=excluded.graph_json,
                    updated_at=excluded.updated_at
                """,
                (
                    pdf_id,
                    _clean_text(payload.get("paper_topic")),
                    json.dumps(graph, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        return {"enabled": True, "status": "success", "message": "Knowledge graph snapshot persisted to SQLite."}
    except Exception as error:
        return {"enabled": True, "status": "error", "message": str(error)[:300]}


def read_graph_neighborhood(payload: Dict[str, Any]) -> Dict[str, Any]:
    paper_ids = _string_list(payload.get("paperIds"))
    source_ids = _string_list(payload.get("sourceIds"))
    seed_terms = _string_list(payload.get("seedTerms"))
    max_nodes = _bounded_int(payload.get("maxNodes"), DEFAULT_MAX_NODES, 1, DEFAULT_MAX_NODES)
    max_edges = _bounded_int(payload.get("maxEdges"), DEFAULT_MAX_EDGES, 1, DEFAULT_MAX_EDGES)
    empty = _empty_result("unavailable", paper_ids, seed_terms)

    try:
        snapshots, invalid_count = _load_snapshots()
    except Exception:
        return empty

    candidates = [
        snapshot
        for snapshot in snapshots
        if _snapshot_matches_scope(snapshot, paper_ids, source_ids)
    ]
    if not candidates:
        return _empty_result("partial" if invalid_count else "unavailable", paper_ids, seed_terms)

    selected_nodes: List[Dict[str, Any]] = []
    selected_edges: List[Dict[str, Any]] = []
    matched_paper_ids: List[str] = []
    seen_nodes = set()
    seen_edges = set()

    for snapshot in candidates:
        graph = snapshot["graph"]
        nodes = [item for item in graph.get("nodes", []) if isinstance(item, dict)]
        edges = _normalized_edges(graph)
        seeds = [node for node in nodes if _node_matches(node, seed_terms, source_ids)]
        if not seeds:
            continue

        seed_ids = {_clean_text(node.get("id")) for node in seeds if _clean_text(node.get("id"))}
        neighbor_ids = set(seed_ids)
        for edge in edges:
            source = _clean_text(edge.get("source"))
            target = _clean_text(edge.get("target"))
            if source in seed_ids or target in seed_ids:
                neighbor_ids.update(item for item in (source, target) if item)

        ordered_nodes = seeds + [node for node in nodes if _clean_text(node.get("id")) in neighbor_ids and node not in seeds]
        added_ids = set()
        for node in ordered_nodes:
            node_id = _clean_text(node.get("id"))
            key = (snapshot["pdfId"], node_id)
            if not node_id or key in seen_nodes or len(selected_nodes) >= max_nodes:
                continue
            seen_nodes.add(key)
            added_ids.add(node_id)
            selected_nodes.append({**_public_node(node), "paperId": snapshot["pdfId"]})

        for edge in edges:
            source = _clean_text(edge.get("source"))
            target = _clean_text(edge.get("target"))
            key = (snapshot["pdfId"], source, target, _clean_text(edge.get("type") or edge.get("relation")))
            if source not in added_ids or target not in added_ids or key in seen_edges or len(selected_edges) >= max_edges:
                continue
            seen_edges.add(key)
            selected_edges.append({**_public_edge(edge), "paperId": snapshot["pdfId"]})

        if added_ids:
            matched_paper_ids.append(snapshot["pdfId"])
        if len(selected_nodes) >= max_nodes and len(selected_edges) >= max_edges:
            break

    if not selected_nodes:
        return _empty_result("partial", [item["pdfId"] for item in candidates], seed_terms)

    graph = {"nodes": selected_nodes, "edges": selected_edges}
    return {
        "status": "available",
        "paperIds": _dedupe(matched_paper_ids),
        "seedTerms": seed_terms,
        "nodes": selected_nodes,
        "edges": selected_edges,
        "sourceIds": _collect_source_ids([*selected_nodes, *selected_edges]),
        "provenanceSummary": build_provenance_summary(graph),
        "contextNote": CONTEXT_NOTE,
    }


def enrich_conflicts_with_graph_context(conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []
    for conflict in conflicts or []:
        current = copy.deepcopy(conflict)
        if _clean_text(current.get("id")) == "no-major-conflict":
            enriched.append(current)
            continue
        sources = [item for item in current.get("sources", []) if isinstance(item, dict)]
        paper_ids = _dedupe([
            *_string_list(current.get("papers")),
            *_string_list(current.get("paperIds")),
            *(_clean_text(item.get("pdfId")) for item in sources if _clean_text(item.get("pdfId"))),
        ])
        source_ids = _dedupe([
            *_string_list(current.get("sourceIds")),
            *(_clean_text(item.get("sourceId")) for item in sources if _clean_text(item.get("sourceId"))),
        ])
        seed_terms = _conflict_seed_terms(current)
        current["graphContext"] = read_graph_neighborhood({
            "paperIds": paper_ids,
            "sourceIds": source_ids,
            "seedTerms": seed_terms,
            "maxNodes": DEFAULT_MAX_NODES,
            "maxEdges": DEFAULT_MAX_EDGES,
        })
        enriched.append(current)
    return enriched


def _conflict_seed_terms(conflict: Dict[str, Any]) -> List[str]:
    explicit_topic = _clean_text(conflict.get("topic"))
    text = " ".join(_clean_text(conflict.get(key)) for key in ("claim", "summary"))
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text)
    values = [explicit_topic] if explicit_topic else []
    values.extend(token.lower() for token in tokens if token.lower() not in SEED_STOPWORDS)
    return _dedupe(item for item in values if item)[:8]


def _initialize_storage(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_graph_snapshots (
                pdf_id TEXT PRIMARY KEY,
                paper_topic TEXT NOT NULL,
                graph_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _load_snapshots() -> tuple[List[Dict[str, Any]], int]:
    db_path = _knowledge_graph_db_path()
    if not db_path.exists():
        return [], 0
    _initialize_storage(db_path)
    snapshots = []
    invalid_count = 0
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT pdf_id, paper_topic, graph_json FROM knowledge_graph_snapshots ORDER BY updated_at DESC"
        ).fetchall()
    for row in rows:
        try:
            graph = json.loads(row["graph_json"])
            if not isinstance(graph, dict):
                raise ValueError("graph_json must be an object")
            snapshots.append({"pdfId": row["pdf_id"], "paperTopic": row["paper_topic"], "graph": graph})
        except Exception:
            invalid_count += 1
    return snapshots, invalid_count


def _snapshot_matches_scope(snapshot: Dict[str, Any], paper_ids: List[str], source_ids: List[str]) -> bool:
    if paper_ids and snapshot["pdfId"] in paper_ids:
        return True
    if source_ids:
        graph_items = [*(snapshot["graph"].get("nodes") or []), *_normalized_edges(snapshot["graph"])]
        return bool(set(source_ids).intersection(_collect_source_ids(graph_items)))
    return not paper_ids


def _node_matches(node: Dict[str, Any], seed_terms: List[str], source_ids: List[str]) -> bool:
    if source_ids and set(source_ids).intersection(_string_list(node.get("sourceIds"))):
        return True
    searchable = " ".join(
        _clean_text(node.get(key)).lower()
        for key in ("id", "label", "summary", "why")
    )
    return any(term.lower() in searchable for term in seed_terms if term)


def _normalized_edges(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    edges.extend(item for item in graph.get("links", []) if isinstance(item, dict))
    result = []
    seen = set()
    for edge in edges:
        key = (_clean_text(edge.get("source")), _clean_text(edge.get("target")), _clean_text(edge.get("type") or edge.get("relation")))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def _public_node(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: node.get(key)
        for key in ("id", "label", "type", "level", "summary", "why", "sourceIds", "provenanceStatus", "confidence", "confidenceReason")
        if key in node
    }


def _public_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: edge.get(key)
        for key in ("source", "target", "type", "relation", "label", "sourceIds", "provenanceStatus", "confidence", "confidenceReason")
        if key in edge
    }


def _empty_result(status: str, paper_ids: List[str], seed_terms: List[str]) -> Dict[str, Any]:
    return {
        "status": status,
        "paperIds": paper_ids,
        "seedTerms": seed_terms,
        "nodes": [],
        "edges": [],
        "sourceIds": [],
        "provenanceSummary": {"nodes": _empty_provenance(), "edges": _empty_provenance()},
        "contextNote": CONTEXT_NOTE,
    }


def _empty_provenance() -> Dict[str, Any]:
    return {"total": 0, "currentPaperSupported": 0, "modelInference": 0, "externalSupported": 0, "supportedRatio": 0.0}


def _collect_source_ids(items: Iterable[Dict[str, Any]]) -> List[str]:
    values = []
    for item in items:
        if isinstance(item, dict):
            values.extend(_string_list(item.get("sourceIds")))
    return _dedupe(values)


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return _dedupe(_clean_text(item) for item in value if _clean_text(item))


def _dedupe(values: Iterable[str]) -> List[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _knowledge_graph_db_path() -> Path:
    configured = os.environ.get("KNOWLEDGE_GRAPH_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "knowledge_graph.sqlite3"
