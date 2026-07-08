def build_workspace_view(
    project,
    active_run,
    pending_review,
    latest_artifacts,
    recent_runs,
    timeline,
):
    return {
        "project": project,
        "activeRun": active_run,
        "pendingReview": pending_review,
        "latestArtifacts": latest_artifacts,
        "recentRuns": list(recent_runs),
        "timeline": list(timeline),
        "uiHints": {},
    }


def get_workspace(project_id: str):
    from services import agent_project_service

    return agent_project_service.get_agent_workspace(project_id)
