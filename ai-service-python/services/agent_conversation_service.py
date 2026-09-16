"""Persistent research tasks and their user/assistant messages."""
import copy
import uuid
from datetime import UTC, datetime


def _now():
    return datetime.now(UTC).isoformat()


def _repository():
    from services.agent_project_service import _get_agent_state_repository
    return _get_agent_state_repository()


def require_task(repository, task_id):
    try:
        return repository.get_research_task(str(task_id or "").strip())
    except KeyError as error:
        raise ValueError("Research task not found.") from error


def start_turn(project_id, task_id, run_id, prompt, paper_ids, *, record_user_message=True):
    repository = _repository()
    if task_id:
        task = require_task(repository, task_id)
        if task.get("projectId") != project_id:
            raise ValueError("Research task does not belong to this project.")
    else:
        task = {"taskId": str(uuid.uuid4()), "projectId": project_id, "title": str(prompt)[:120],
                "paperIds": list(paper_ids), "latestRunId": "", "createdAt": _now(), "updatedAt": _now()}
    task["latestRunId"] = run_id
    task["paperIds"] = list(dict.fromkeys([*(task.get("paperIds") or []), *paper_ids]))
    task["updatedAt"] = _now()
    repository.save_research_task(task)
    if record_user_message:
        repository.save_message({"messageId": f"user:{run_id}", "taskId": task["taskId"], "runId": run_id,
                                 "role": "user", "content": prompt, "sourceIds": [], "createdAt": _now()})
    return copy.deepcopy(task)


def append_assistant_message(run, content, findings=None):
    task_id = str(run.get("conversationId") or "").strip()
    if not task_id:
        return None
    source_ids = list(dict.fromkeys(source_id for finding in (findings or [])
                                    for source_id in (finding.get("sourceIds") or [])))
    message = {"messageId": f"assistant:{run['taskId']}", "taskId": task_id, "runId": run["taskId"],
               "role": "assistant", "content": str(content or ""), "sourceIds": source_ids,
               "status": run.get("status"), "createdAt": _now()}
    _repository().save_message(message)
    return message


def list_tasks(project_id):
    return _repository().list_research_tasks(project_id)


def get_task(task_id):
    repository = _repository()
    task = require_task(repository, task_id)
    return {"task": task, "messages": repository.list_messages(task_id)}


def list_messages(repository_or_task_id, task_id=None):
    repository = repository_or_task_id if task_id is not None else _repository()
    resolved_task_id = task_id if task_id is not None else repository_or_task_id
    require_task(repository, resolved_task_id)
    return repository.list_messages(resolved_task_id)
