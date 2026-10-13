"""Abrupt process restart with real SQLite and controlled capability outputs.

This establishes recovery semantics, not live model report quality.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


WORKER = r'''
import json,os,sys
from pathlib import Path
from services import research_task_service as service
from schemas.requests import ResearchTaskCreateRequest
root=Path(sys.argv[1]);phase=sys.argv[2]
service._load_current_paper_documents=lambda _: ([{"text":"controlled evidence"}],"paper")
service._should_create_follow_up=lambda _: False
service._detect_research_conflicts=lambda _: []
service._build_research_report=lambda *args,**kwargs: "controlled report"
def finding(**kwargs):
    with (root/"calls.txt").open("a",encoding="utf-8") as log:
        log.write(kwargs["sub_question"]+"\n")
    return {"subQuestion":kwargs["sub_question"],"summary":"saved result","sources":[],"missingAspects":[]}
service._research_sub_question=finding
if phase=="crash":
    task=service.create_research_task(ResearchTaskCreateRequest(question="Question",pdfId="paper"),start_async=False)["task"]
    identity=task["taskId"];(root/"identity.txt").write_text(identity)
    plan=service._build_initial_plan_items(["completed question","remaining question"])
    service._TASK_CONTEXTS[identity]["approvedPlan"]=plan
    service._update_task_snapshot(identity,status="running",plan=plan)
    update=service._update_task_snapshot
    def checkpoint(task_id,**values):
        result=update(task_id,**values)
        if len(values.get("findings",[]))==1:
            os._exit(23) # No finally or executor shutdown: persisted worker checkpoint only.
        return result
    service._update_task_snapshot=checkpoint
    service.run_research_task_now(identity)
    raise AssertionError("crash checkpoint was not reached")
identity=(root/"identity.txt").read_text()
before=service.get_research_task(identity)["task"]
assert before["status"]=="failed"
assert len(before["findings"])==1
scheduled=[]
def dispatch(fn,task_id):
    scheduled.append(task_id)
    return fn(task_id)
service._TASK_EXECUTOR.submit=dispatch
service.resume_research_task(identity)
service.resume_research_task(identity)
after=service.get_research_task(identity)["task"]
assert after["status"]=="awaiting_final_review", (after["status"],after.get("error"))
assert after["traceId"] != before["traceId"]
assert all(item["status"]=="done" for item in after["plan"])
assert len(after["findings"])==2
assert len(scheduled)==1
print(json.dumps({"before":before["status"],"after":after["status"],"findings":len(after["findings"]),"scheduled":len(scheduled)}))
'''


def test_abrupt_restart_resumes_only_unfinished_saved_plan(tmp_path):
    environment = {**os.environ, "RESEARCH_TASK_DB_PATH": str(tmp_path / "research.sqlite3"),
                   "PIXIU_LLM_CACHE_PATH": ":memory:", "HF_HUB_OFFLINE": "1"}
    directory = Path(__file__).resolve().parents[1]
    crash = subprocess.run([sys.executable, "-c", WORKER, str(tmp_path), "crash"],
                           cwd=directory, env=environment, capture_output=True, text=True, timeout=30)
    assert crash.returncode == 23, crash.stderr
    assert (tmp_path / "calls.txt").read_text(encoding="utf-8").splitlines() == ["completed question"]
    restart = subprocess.run([sys.executable, "-c", WORKER, str(tmp_path), "resume"],
                             cwd=directory, env=environment, capture_output=True, text=True, timeout=30)
    assert restart.returncode == 0, restart.stderr
    result = json.loads(restart.stdout.strip().splitlines()[-1])
    assert result == {"before": "failed", "after": "awaiting_final_review", "findings": 2, "scheduled": 1}
    assert (tmp_path / "calls.txt").read_text(encoding="utf-8").splitlines() == ["completed question", "remaining question"]
