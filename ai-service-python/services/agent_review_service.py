def build_plan_review_packet(
    run,
    plan_items,
    focused_paper_ids,
    constraints,
    allow_external_search,
):
    return {
        "runId": run["runId"],
        "version": 1,
        "status": "pending",
        "planItems": list(plan_items),
        "focusedPaperIds": list(focused_paper_ids),
        "constraints": constraints,
        "externalSearchRequest": {
            "allowed": bool(allow_external_search),
            "providerPolicy": "whitelisted_academic_only",
            "budget": {"callLimit": 3, "evidenceLimit": 15},
            "reviewReason": "",
        },
        "reviewNotes": "",
        "reviewedBy": "",
        "reviewedAt": "",
    }


def build_final_review_packet(run, artifacts):
    risk_items = []
    for conflict in artifacts.get("conflicts", []):
        risk_items.append(
            {
                "riskId": f"conflict:{conflict['id']}",
                "type": "conflict",
                "label": conflict.get("summary", ""),
                "reviewStatus": "pending",
            }
        )
    for index, question in enumerate(artifacts.get("openQuestions", []), 1):
        risk_items.append(
            {
                "riskId": f"open:{index}",
                "type": "open_question",
                "label": question,
                "reviewStatus": "pending",
            }
        )

    return {
        "runId": run["runId"],
        "version": 1,
        "status": "pending",
        "summary": artifacts.get("draftReport", ""),
        "riskItems": risk_items,
        "reviewNotes": "",
        "reviewedBy": "",
        "reviewedAt": "",
    }


def review_plan(run_id, request):
    from services import agent_project_service

    return agent_project_service.review_agent_run_plan(run_id, request)


def review_final(run_id, request):
    from services import agent_project_service

    return agent_project_service.review_agent_run_final(run_id, request)


def answer_clarification(run_id, request):
    from services import agent_project_service

    return agent_project_service.answer_agent_clarification(run_id, request)
