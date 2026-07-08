def build_timeline_entry(entry_id, entry_type, title="", detail="", phase="", meta=None):
    return {
        "id": entry_id,
        "type": entry_type,
        "title": title,
        "detail": detail,
        "phase": phase,
        "meta": dict(meta or {}),
    }


def get_timeline(run_id: str):
    from services import agent_project_service

    return agent_project_service.get_agent_run_timeline(run_id)
