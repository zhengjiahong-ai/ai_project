"""Research obligations and source-specific coverage, independent of confidence."""
from __future__ import annotations


def validate_plan(items: list[dict]) -> list[dict]:
    if not isinstance(items, list) or not items or len(items) > 8 or any(not isinstance(item, dict) for item in items):
        raise ValueError("A plan needs one to eight bounded items")
    if any(not isinstance(item.get("itemId"), str) for item in items):
        raise ValueError("Invalid plan identity")
    by_id = {item.get("itemId"): item for item in items}
    if None in by_id or "" in by_id or len(by_id) != len(items):
        raise ValueError("Plan identities must be unique")
    visited, active = set(), set()

    def visit(key):
        if key in active:
            raise ValueError("Cyclic plan dependency")
        if key in visited:
            return
        if key not in by_id:
            raise ValueError("Unknown plan dependency")
        active.add(key)
        for dependency in by_id[key].get("dependencies", []):
            visit(dependency)
        active.remove(key)
        visited.add(key)
    obligation_ids = set()
    for key, item in by_id.items():
        if not isinstance(key, str) or len(key) > 128:
            raise ValueError("Invalid plan identity")
        obligations = item.get("obligations")
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list) or any(not isinstance(value, str) for value in dependencies):
            raise ValueError("Invalid plan dependencies")
        if not isinstance(item.get("question"), str) or not item["question"].strip() or not isinstance(obligations, list) or not obligations:
            raise ValueError("Plan must state research obligations")
        for obligation in item["obligations"]:
            if not isinstance(obligation, dict):
                raise ValueError("Invalid research obligation")
            identity = obligation.get("obligationId")
            if not isinstance(identity, str) or not identity or len(identity) > 128 or identity in obligation_ids or not isinstance(obligation.get("question"), str) or not obligation["question"].strip():
                raise ValueError("Invalid research obligation")
            if not isinstance(obligation.get("requiredSources", []), list) or any(not isinstance(value, str) for value in obligation.get("requiredSources", [])):
                raise ValueError("Invalid obligation sources")
            obligation_ids.add(identity)
        visit(key)
    return items


def coverage_gaps(plan: list[dict], coverage: list[dict], required_sources: list[str]) -> list[dict]:
    """One paper's successful retrieval cannot satisfy another paper's obligation."""
    indexed = {(item["obligationId"], item["sourceWorkId"]): item for item in coverage}
    gaps = []
    for step in plan:
        for obligation in step["obligations"]:
            sources = obligation.get("requiredSources") or required_sources
            for source in sources:
                row = indexed.get((obligation["obligationId"], source))
                if not row or row.get("state") not in {"supported", "contradicted", "not_applicable"}:
                    gaps.append({"obligationId": obligation["obligationId"], "sourceWorkId": source,
                                 "question": obligation["question"],
                                 "checked": bool(row and row.get("checked")),
                                 "missingEvidence": (row or {}).get("missingEvidence", "尚未核实")})
    return gaps
