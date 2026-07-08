def build_artifacts_record(
    run_id,
    *,
    evidence_items=None,
    tool_call_summary=None,
    findings=None,
    comparison_table=None,
    conflicts=None,
    open_questions=None,
    draft_report="",
):
    return {
        "runId": run_id,
        "version": 1,
        "evidenceItems": list(evidence_items or []),
        "toolCallSummary": list(tool_call_summary or []),
        "findings": list(findings or []),
        "comparisonTable": comparison_table or {"columns": [], "rows": []},
        "conflicts": list(conflicts or []),
        "openQuestions": list(open_questions or []),
        "draftReport": draft_report,
        "externalEvidenceSummary": {},
        "graphContextSummary": {},
    }


def get_artifacts(run_id: str):
    from services import agent_project_service

    return agent_project_service.get_agent_run_artifacts(run_id)
