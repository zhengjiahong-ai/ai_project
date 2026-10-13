"""Pure report templates and structured output validation; graph.py owns model calls."""
from typing import Any

OUTPUT_KIND_SECTIONS = {
    "direction_survey": ["核心判断", "方法脉络", "代表工作", "关键争议", "推荐阅读顺序"],
    "paper_comparison": ["比较结论", "共同维度表", "差异原因", "选用条件"],
    "claim_verification": ["判断", "支持证据", "反对证据", "适用条件", "未解决事项"],
    "experiment_design": ["假设", "分组表", "固定条件", "执行步骤", "指标", "结果解释", "风险"],
    "research_entry": ["已有证据", "缺口", "候选假设", "可行性", "最小验证方案"],
}

# Legacy alias mapping for backward compatibility
_OUTPUT_KIND_ALIASES = {
    "claim_check": "claim_verification",
    "research_opportunity": "research_entry",
}


def resolve_output_kind(kind: str) -> str:
    """Normalize output kind to canonical form."""
    return _OUTPUT_KIND_ALIASES.get(kind, kind)



def _validate_section_claim_binding(
    sections: list[dict[str, Any]],
    verified_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure section claimIds reference actual verified claims.
    
    Removes unbound claim IDs to prevent unchecked model prose in sections.
    """
    valid_claim_ids = {c.get("claimId") for c in verified_claims if c.get("claimId")}
    
    validated = []
    for section in sections:
        raw_claim_ids = section.get("claimIds", [])
        if not isinstance(raw_claim_ids, list):
            raw_claim_ids = []
        
        bound_ids = [cid for cid in raw_claim_ids if cid in valid_claim_ids]
        
        validated.append({
            "title": section.get("title", ""),
            "content": section.get("content", ""),
            "claimIds": bound_ids,
            "citations": section.get("citations", []),
        })
    
    return validated


def _validate_proposals(proposals: Any) -> list[dict[str, Any]]:
    """Ensure proposals are clearly labeled as hypothesis/proposal, not facts."""
    if not isinstance(proposals, list):
        return []
    
    validated = []
    for prop in proposals:
        if isinstance(prop, str):
            validated.append({"text": prop, "kind": "proposal"})
        elif isinstance(prop, dict):
            text = prop.get("text", "")
            kind = prop.get("kind", "proposal")
            if kind not in ("hypothesis", "proposal"):
                kind = "proposal"
            if text:
                validated.append({"text": text, "kind": kind})
    
    return validated
