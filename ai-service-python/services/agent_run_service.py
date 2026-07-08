import copy
from typing import Dict, Set


ALLOWED_RUN_TRANSITIONS: Dict[str, Set[str]] = {
    "draft": {"awaiting_plan_review"},
    "awaiting_plan_review": {"queued", "cancelled"},
    "queued": {"running", "failed", "cancelled"},
    "running": {"awaiting_final_review", "failed", "cancelled"},
    "awaiting_final_review": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


class AgentRunStateError(ValueError):
    pass


def transition_run_status(run: dict, next_status: str, execution_phase: str = "") -> dict:
    current_status = str(run.get("status") or "").strip()
    allowed = ALLOWED_RUN_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise AgentRunStateError(
            f"Illegal Agent run transition: {current_status} -> {next_status}"
        )

    updated = copy.deepcopy(run)
    updated["status"] = next_status
    updated["executionPhase"] = execution_phase if next_status == "running" else ""
    return updated
