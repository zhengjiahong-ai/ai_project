# Agent 架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前以单一 `task snapshot` 为中心的 Agent 实现重构为以 `project / run / review / artifacts / timeline / workspace` 为核心资源的清晰工作流架构，并完成三层 API、持久化与前端消费迁移。

**Architecture:** 先在 Python 侧建立新的领域对象、状态机、repository 和聚合读模型，再通过适配层逐步替换现有 `agent_project_service.py` 的职责。对外新增 `runs / reviews / artifacts / timeline / workspace` 资源接口，同时在 Java 网关和前端 API 层接入新接口，最后把旧的 `agent-tasks` 契约降为兼容壳或彻底移除。

**Tech Stack:** FastAPI, Python services + SQLite, Java Spring Boot gateway, React + Vite frontend, Node-based frontend unit tests, Python `pytest`, Java `mvn test`

## 执行进度

- 已完成 Task 1：新增 `agent_domain_models.py` 与 `agent_run_service.py`，建立 run 状态机与基础测试。
- 已完成 Task 2：新增 review / artifact / timeline / workspace 服务及对应测试。
- 已完成 Task 3：新增 `agent_state_repository.py`，为旧 `agent_project_service.py` 加入兼容适配职责，并让 `agent_orchestrator.py` 提供更纯粹的 `execute_run(...)` 执行结果。
- 已完成 Task 4-7：对外 run/workspace API、Java 网关、前端消费层和最终兼容层迁移已经收口；旧 `agent-tasks` 路径降级为 compatibility adapter。

---

## 文件结构与职责

### Python 后端

- 修改: `ai-service-python/routes/api.py`
  负责暴露新的 Agent run/review/artifacts/timeline/workspace 路由，并在迁移期保留旧接口适配。
- 修改: `ai-service-python/schemas/requests.py`
  负责新增 run/review/workspace 相关请求模型，保留旧请求模型到兼容层。
- 新建: `ai-service-python/services/agent_domain_models.py`
  负责集中定义 `AgentProject`、`AgentRun`、`PlanReviewPacket`、`FinalReviewPacket`、`RunArtifacts`、`RunTimelineEntry`、`WorkspaceView` 的 TypedDict 或 dataclass 结构。
- 新建: `ai-service-python/services/agent_state_repository.py`
  负责 SQLite 读写和旧 task snapshot 到新资源模型的兼容恢复。
- 新建: `ai-service-python/services/agent_run_service.py`
  负责 run 生命周期状态机与重启恢复。
- 新建: `ai-service-python/services/agent_review_service.py`
  负责双阶段 review packet 的生成、读取和审批推进。
- 新建: `ai-service-python/services/agent_artifact_service.py`
  负责 artifacts 的落库、读取和 risk item 派生。
- 新建: `ai-service-python/services/agent_timeline_service.py`
  负责时间线追加和查询。
- 新建: `ai-service-python/services/agent_workspace_service.py`
  负责聚合读取 `workspace` 视图。
- 修改: `ai-service-python/services/agent_orchestrator.py`
  改造成纯执行器，只返回 execution result，不直接拼 task snapshot。
- 修改: `ai-service-python/services/agent_project_service.py`
  降为旧接口兼容适配层，委托给 project/run/review/workspace 服务。

### Python 测试

- 新建: `ai-service-python/tests/test_agent_run_service.py`
- 新建: `ai-service-python/tests/test_agent_review_service.py`
- 新建: `ai-service-python/tests/test_agent_workspace_service.py`
- 新建: `ai-service-python/tests/test_agent_state_repository.py`
- 修改: `ai-service-python/tests/test_agent_project_service.py`
- 修改: `ai-service-python/tests/test_agent_orchestrator.py`
- 修改: `ai-service-python/tests/test_api_contract_smoke.py`

### 契约与文档

- 修改: `contracts/api-contract-smoke.json`
- 修改: `API.md`
- 修改: `ARCHITECTURE.md`
- 修改: `README.md`
- 修改: `docs/CONSTRAINTS.md`

### Java 网关

- 修改: `backend-java/src/main/java/com/ai/assistant/backend_java/controller/AcademicController.java`
- 修改: `backend-java/src/main/java/com/ai/assistant/backend_java/service/AiService.java`
- 修改: `backend-java/src/test/java/com/ai/assistant/backend_java/controller/AcademicControllerTest.java`
- 修改: `backend-java/src/test/java/com/ai/assistant/backend_java/service/AiServiceTest.java`
- 修改: `backend-java/src/test/java/com/ai/assistant/backend_java/controller/ApiContractSmokeTest.java`

### 前端

- 修改: `frontend/src/services/api.js`
- 修改: `frontend/src/services/api.test.js`
- 修改: `frontend/src/components/agent/agentWorkspaceModel.js`
- 修改: `frontend/src/components/agent/agentWorkspaceStore.js`
- 修改: `frontend/src/components/agent/AgentWorkspace.jsx`
- 修改: `frontend/src/components/agent/AgentWorkspaceMain.jsx`
- 修改: `frontend/src/components/agent/AgentWorkspaceSidebar.jsx`
- 修改: `frontend/src/components/agent/agentWorkspaceModel.test.js`
- 修改: `frontend/tests/fixtures/mockApi.js`
- 修改: `frontend/tests/fixtures/externalProviderRoute.js`
- 修改: `frontend/tests/e2e/reader-agent-smoke.spec.js`

## 实施约束

1. 保持用户侧“双阶段人工审查”流程不变。
2. 外部学术检索授权边界不得放宽，仍需显式审批。
3. `traceSummary` 继续作为独立只读观测资源。
4. 在迁移完成前，旧 `agent-tasks` 路径可以保留兼容适配，但不得再作为新的内部真相来源。
5. 每个任务都先写失败测试，再实现最小代码，再运行相关测试。

### Task 1: 建立新的领域模型与状态机骨架

**Files:**
- Create: `ai-service-python/services/agent_domain_models.py`
- Create: `ai-service-python/services/agent_run_service.py`
- Test: `ai-service-python/tests/test_agent_run_service.py`

- [ ] **Step 1: 写 run 状态机的失败测试**

```python
from services.agent_run_service import (
    ALLOWED_RUN_TRANSITIONS,
    AgentRunStateError,
    transition_run_status,
)


def test_transition_run_status_allows_happy_path():
    run = {"runId": "run-1", "status": "draft", "executionPhase": ""}

    run = transition_run_status(run, "awaiting_plan_review")
    assert run["status"] == "awaiting_plan_review"

    run = transition_run_status(run, "queued")
    assert run["status"] == "queued"

    run = transition_run_status(run, "running", execution_phase="retrieving_evidence")
    assert run["status"] == "running"
    assert run["executionPhase"] == "retrieving_evidence"

    run = transition_run_status(run, "awaiting_final_review")
    assert run["status"] == "awaiting_final_review"
    assert run["executionPhase"] == ""

    run = transition_run_status(run, "completed")
    assert run["status"] == "completed"


def test_transition_run_status_rejects_illegal_jump():
    run = {"runId": "run-2", "status": "awaiting_plan_review", "executionPhase": ""}

    try:
        transition_run_status(run, "completed")
    except AgentRunStateError as error:
        assert "Illegal Agent run transition" in str(error)
    else:
        raise AssertionError("expected AgentRunStateError")


def test_allowed_transition_table_is_explicit():
    assert ALLOWED_RUN_TRANSITIONS["draft"] == {"awaiting_plan_review"}
    assert "completed" not in ALLOWED_RUN_TRANSITIONS["awaiting_plan_review"]
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `pytest ai-service-python/tests/test_agent_run_service.py -v`

Expected: FAIL with `ModuleNotFoundError` or `cannot import name 'transition_run_status'`

- [ ] **Step 3: 写最小领域模型与状态机实现**

```python
# ai-service-python/services/agent_domain_models.py
from typing import Literal, TypedDict


RunStatus = Literal[
    "draft",
    "awaiting_plan_review",
    "queued",
    "running",
    "awaiting_final_review",
    "completed",
    "failed",
    "cancelled",
]


ExecutionPhase = Literal[
    "",
    "planning_context",
    "retrieving_evidence",
    "synthesizing",
    "assembling_artifacts",
]


class AgentRunRecord(TypedDict, total=False):
    runId: str
    projectId: str
    status: RunStatus
    executionPhase: ExecutionPhase
    prompt: str
    focusedPaperIds: list[str]
    constraints: str
    context: dict
    traceId: str
```

```python
# ai-service-python/services/agent_run_service.py
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
```

- [ ] **Step 4: 运行测试，确认状态机通过**

Run: `pytest ai-service-python/tests/test_agent_run_service.py -v`

Expected: PASS with `3 passed`

- [ ] **Step 5: 提交**

```bash
git add ai-service-python/services/agent_domain_models.py ai-service-python/services/agent_run_service.py ai-service-python/tests/test_agent_run_service.py
git commit -m "refactor: add agent run domain model and state machine"
```

### Task 2: 抽出 review、artifacts、timeline 与 workspace 的后端服务边界

**Files:**
- Create: `ai-service-python/services/agent_review_service.py`
- Create: `ai-service-python/services/agent_artifact_service.py`
- Create: `ai-service-python/services/agent_timeline_service.py`
- Create: `ai-service-python/services/agent_workspace_service.py`
- Test: `ai-service-python/tests/test_agent_review_service.py`
- Test: `ai-service-python/tests/test_agent_workspace_service.py`

- [ ] **Step 1: 写 review packet 与 workspace 聚合的失败测试**

```python
from services.agent_review_service import build_plan_review_packet, build_final_review_packet
from services.agent_workspace_service import build_workspace_view


def test_build_plan_review_packet_carries_external_search_request():
    packet = build_plan_review_packet(
        run={"runId": "run-1"},
        plan_items=[{"id": "evidence", "label": "Collect claim-level evidence"}],
        focused_paper_ids=["paper-a"],
        constraints="Only compare methods.",
        allow_external_search=True,
    )

    assert packet["runId"] == "run-1"
    assert packet["status"] == "pending"
    assert packet["externalSearchRequest"]["allowed"] is True
    assert packet["focusedPaperIds"] == ["paper-a"]


def test_build_final_review_packet_derives_risk_items_from_artifacts():
    artifacts = {
        "conflicts": [{"id": "conflict-1", "summary": "Method conflict", "severity": "medium"}],
        "openQuestions": ["Need stronger evidence for paper-b."],
        "draftReport": "# Draft",
    }
    packet = build_final_review_packet(run={"runId": "run-2"}, artifacts=artifacts)

    assert packet["runId"] == "run-2"
    assert packet["status"] == "pending"
    assert len(packet["riskItems"]) == 2


def test_build_workspace_view_joins_project_run_review_artifacts_and_timeline():
    workspace = build_workspace_view(
        project={"projectId": "project-1", "title": "Project"},
        active_run={"runId": "run-1", "status": "awaiting_plan_review"},
        pending_review={"runId": "run-1", "status": "pending"},
        latest_artifacts={"runId": "run-1", "findings": []},
        recent_runs=[{"runId": "run-1", "status": "awaiting_plan_review"}],
        timeline=[{"id": "entry-1", "type": "plan_prepared"}],
    )

    assert workspace["project"]["projectId"] == "project-1"
    assert workspace["activeRun"]["runId"] == "run-1"
    assert workspace["pendingReview"]["status"] == "pending"
    assert workspace["timeline"][0]["type"] == "plan_prepared"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `pytest ai-service-python/tests/test_agent_review_service.py ai-service-python/tests/test_agent_workspace_service.py -v`

Expected: FAIL with missing service modules

- [ ] **Step 3: 写最小 review / artifacts / timeline / workspace 服务**

```python
# ai-service-python/services/agent_review_service.py
def build_plan_review_packet(run, plan_items, focused_paper_ids, constraints, allow_external_search):
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
```

```python
# ai-service-python/services/agent_workspace_service.py
def build_workspace_view(project, active_run, pending_review, latest_artifacts, recent_runs, timeline):
    return {
        "project": project,
        "activeRun": active_run,
        "pendingReview": pending_review,
        "latestArtifacts": latest_artifacts,
        "recentRuns": list(recent_runs),
        "timeline": list(timeline),
        "uiHints": {},
    }
```

- [ ] **Step 4: 运行测试，确认聚合边界通过**

Run: `pytest ai-service-python/tests/test_agent_review_service.py ai-service-python/tests/test_agent_workspace_service.py -v`

Expected: PASS with `3 passed`

- [ ] **Step 5: 提交**

```bash
git add ai-service-python/services/agent_review_service.py ai-service-python/services/agent_artifact_service.py ai-service-python/services/agent_timeline_service.py ai-service-python/services/agent_workspace_service.py ai-service-python/tests/test_agent_review_service.py ai-service-python/tests/test_agent_workspace_service.py
git commit -m "refactor: add agent review and workspace services"
```

### Task 3: 引入 repository 与新资源持久化，并让旧 service 走适配层

**Files:**
- Create: `ai-service-python/services/agent_state_repository.py`
- Modify: `ai-service-python/services/agent_project_service.py`
- Modify: `ai-service-python/services/agent_orchestrator.py`
- Test: `ai-service-python/tests/test_agent_state_repository.py`
- Modify: `ai-service-python/tests/test_agent_project_service.py`
- Modify: `ai-service-python/tests/test_agent_orchestrator.py`

- [ ] **Step 1: 写 repository 与兼容适配的失败测试**

```python
from services.agent_state_repository import AgentStateRepository


def test_repository_persists_run_review_artifacts_and_timeline(tmp_path):
    repo = AgentStateRepository(str(tmp_path / "agent_state.sqlite3"))
    repo.initialize()

    repo.save_project({"projectId": "project-1", "title": "Project", "paperIds": []})
    repo.save_run({"runId": "run-1", "projectId": "project-1", "status": "awaiting_plan_review"})
    repo.save_plan_review({"runId": "run-1", "status": "pending", "planItems": []})
    repo.save_artifacts({"runId": "run-1", "findings": [], "conflicts": [], "openQuestions": []})
    repo.append_timeline_entry({"runId": "run-1", "id": "entry-1", "type": "plan_prepared"})

    assert repo.get_run("run-1")["status"] == "awaiting_plan_review"
    assert repo.get_plan_review("run-1")["status"] == "pending"
    assert repo.list_timeline("run-1")[0]["type"] == "plan_prepared"
```

```python
from services import agent_project_service


def test_legacy_project_service_returns_task_shaped_adapter_for_old_callers():
    project = {"projectId": "project-1", "title": "Project", "paperIds": ["paper-a"]}
    run = {"runId": "run-1", "projectId": "project-1", "status": "awaiting_plan_review", "prompt": "Compare methods."}
    review = {"runId": "run-1", "status": "pending", "planItems": [{"id": "evidence", "label": "Collect evidence"}]}

    adapted = agent_project_service._build_legacy_task_snapshot(project, run, review, None, [])

    assert adapted["taskId"] == "run-1"
    assert adapted["projectId"] == "project-1"
    assert adapted["status"] == "awaiting_plan_review"
    assert adapted["planItems"][0]["id"] == "evidence"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `pytest ai-service-python/tests/test_agent_state_repository.py ai-service-python/tests/test_agent_project_service.py -v`

Expected: FAIL with missing repository class or missing `_build_legacy_task_snapshot`

- [ ] **Step 3: 写最小 repository、适配层与 orchestrator 返回 execution result**

```python
# ai-service-python/services/agent_state_repository.py
class AgentStateRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize(self):
        ...

    def save_project(self, project: dict):
        ...

    def save_run(self, run: dict):
        ...

    def save_plan_review(self, review: dict):
        ...

    def save_artifacts(self, artifacts: dict):
        ...

    def append_timeline_entry(self, entry: dict):
        ...

    def get_run(self, run_id: str) -> dict:
        ...
```

```python
# ai-service-python/services/agent_project_service.py
def _build_legacy_task_snapshot(project, run, pending_review, artifacts, timeline):
    return {
        "taskId": run["runId"],
        "projectId": project["projectId"],
        "status": run["status"],
        "stage": run.get("executionPhase", ""),
        "prompt": run.get("prompt", ""),
        "planItems": (pending_review or {}).get("planItems", []),
        "findings": (artifacts or {}).get("findings", []),
        "conflicts": (artifacts or {}).get("conflicts", []),
        "openQuestions": (artifacts or {}).get("openQuestions", []),
        "events": list(timeline or []),
    }
```

```python
# ai-service-python/services/agent_orchestrator.py
def execute_run(prompt: str, paper_ids: list[str], allow_external_search: bool = False) -> dict:
    paper_contexts, tool_calls, evidence_items = collect_project_evidence(
        prompt,
        paper_ids,
        allow_external_search=allow_external_search,
    )
    finding, comparison_table, conflicts, open_questions = build_agent_outputs(
        prompt,
        paper_contexts,
        evidence_items,
    )
    return {
        "paperContexts": paper_contexts,
        "toolCalls": tool_calls,
        "artifacts": {
            "evidenceItems": evidence_items,
            "findings": [finding],
            "comparisonTable": comparison_table,
            "conflicts": conflicts,
            "openQuestions": open_questions,
            "draftReport": build_minimal_report(
                prompt,
                {"title": "Project"},
                paper_contexts,
                evidence_items,
                conflicts,
                open_questions,
            ),
        },
    }
```

- [ ] **Step 4: 运行 Python 服务层测试**

Run: `pytest ai-service-python/tests/test_agent_state_repository.py ai-service-python/tests/test_agent_project_service.py ai-service-python/tests/test_agent_orchestrator.py -v`

Expected: PASS with repository and compatibility adapter coverage green

- [ ] **Step 5: 提交**

```bash
git add ai-service-python/services/agent_state_repository.py ai-service-python/services/agent_project_service.py ai-service-python/services/agent_orchestrator.py ai-service-python/tests/test_agent_state_repository.py ai-service-python/tests/test_agent_project_service.py ai-service-python/tests/test_agent_orchestrator.py
git commit -m "refactor: persist agent resources and add legacy adapter"
```

### Task 4: 新增 Python 资源 API，并更新契约 fixture 与文档

**Files:**
- Modify: `ai-service-python/routes/api.py`
- Modify: `ai-service-python/schemas/requests.py`
- Modify: `contracts/api-contract-smoke.json`
- Modify: `ai-service-python/tests/test_api_contract_smoke.py`
- Modify: `API.md`
- Modify: `ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `docs/CONSTRAINTS.md`

- [ ] **Step 1: 写 API 契约的失败测试**

```python
def test_contract_fixture_contains_agent_run_workspace_and_review_resources():
    fixture = load_contract_fixture()
    operations = {item["operation"]: item for item in fixture["operations"]}

    assert "agent-runs" in operations
    assert "agent-workspace" in operations
    assert "agent-run-plan-review" in operations
    assert "agent-run-final-review" in operations
    assert "agent-run-artifacts" in operations
    assert "agent-run-timeline" in operations
```

- [ ] **Step 2: 运行契约测试，确认当前失败**

Run: `pytest ai-service-python/tests/test_api_contract_smoke.py -v`

Expected: FAIL because the new operations are absent

- [ ] **Step 3: 增加新路由、新请求模型和契约 fixture**

```python
# ai-service-python/routes/api.py
@router.post("/agent-projects/{project_id}/runs")
def create_agent_run(project_id: str, request: AgentRunCreateRequest):
    return run_service.create_run(project_id, request)


@router.get("/agent-projects/{project_id}/workspace")
def get_agent_workspace(project_id: str):
    return workspace_service.get_workspace(project_id)


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: str):
    return run_service.get_run(run_id)


@router.get("/agent-runs/{run_id}/artifacts")
def get_agent_run_artifacts(run_id: str):
    return artifact_service.get_artifacts(run_id)
```

```python
# ai-service-python/schemas/requests.py
class AgentRunCreateRequest(BaseModel):
    prompt: str
    focusedPaperIds: List[str] = Field(default_factory=list)
    constraints: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    allowExternalSearch: bool = False


class AgentRunPlanReviewRequest(BaseModel):
    planItems: List[AgentPlanItemRequest]
    focusedPaperIds: List[str]
    constraints: str = ""
    reviewNotes: str = ""
    allowExternalSearch: bool = False
```

```json
{
  "operation": "agent-workspace",
  "method": "GET",
  "frontendPath": "/agent-projects/project-contract-1/workspace",
  "javaPath": "/api/agent-projects/project-contract-1/workspace",
  "pythonPath": "/api/agent-projects/{project_id}/workspace"
}
```

- [ ] **Step 4: 运行契约与文档相关测试**

Run: `pytest ai-service-python/tests/test_api_contract_smoke.py -v`

Expected: PASS with new run/workspace operations recognized

- [ ] **Step 5: 提交**

```bash
git add ai-service-python/routes/api.py ai-service-python/schemas/requests.py contracts/api-contract-smoke.json ai-service-python/tests/test_api_contract_smoke.py API.md ARCHITECTURE.md README.md docs/CONSTRAINTS.md
git commit -m "feat: expose agent run workspace and review resource APIs"
```

### Task 5: 接入 Java 网关的新 Agent 资源接口

**Files:**
- Modify: `backend-java/src/main/java/com/ai/assistant/backend_java/controller/AcademicController.java`
- Modify: `backend-java/src/main/java/com/ai/assistant/backend_java/service/AiService.java`
- Modify: `backend-java/src/test/java/com/ai/assistant/backend_java/controller/AcademicControllerTest.java`
- Modify: `backend-java/src/test/java/com/ai/assistant/backend_java/service/AiServiceTest.java`
- Modify: `backend-java/src/test/java/com/ai/assistant/backend_java/controller/ApiContractSmokeTest.java`

- [ ] **Step 1: 写 Java 网关转发的失败测试**

```java
@Test
void shouldForwardAgentWorkspaceRequest() throws Exception {
    when(aiService.getAgentWorkspace("project-1"))
        .thenReturn(ResponseEntity.ok("{\"status\":\"success\"}"));

    mockMvc.perform(get("/api/agent-projects/project-1/workspace"))
        .andExpect(status().isOk());
}

@Test
void shouldForwardAgentRunArtifactsRequest() throws Exception {
    when(aiService.getAgentRunArtifacts("run-1"))
        .thenReturn(ResponseEntity.ok("{\"status\":\"success\"}"));

    mockMvc.perform(get("/api/agent-runs/run-1/artifacts"))
        .andExpect(status().isOk());
}
```

- [ ] **Step 2: 运行 Java 测试，确认当前失败**

Run: `mvn test -Dtest=AcademicControllerTest,ApiContractSmokeTest,AiServiceTest`

Expected: FAIL with missing controller mappings or service methods

- [ ] **Step 3: 增加控制器与转发方法**

```java
// AcademicController.java
@GetMapping("/agent-projects/{projectId}/workspace")
public ResponseEntity<String> getAgentWorkspace(@PathVariable String projectId) {
    return aiService.getAgentWorkspace(projectId);
}

@PostMapping("/agent-projects/{projectId}/runs")
public ResponseEntity<String> createAgentRun(@PathVariable String projectId, @RequestBody String request) {
    return aiService.createAgentRun(projectId, request);
}

@GetMapping("/agent-runs/{runId}/artifacts")
public ResponseEntity<String> getAgentRunArtifacts(@PathVariable String runId) {
    return aiService.getAgentRunArtifacts(runId);
}
```

```java
// AiService.java
public ResponseEntity<String> getAgentWorkspace(String projectId) {
    String encodedProjectId = UriUtils.encodePathSegment(projectId, StandardCharsets.UTF_8);
    return forwardAgentRequest(HttpMethod.GET, "/agent-projects/" + encodedProjectId + "/workspace", null);
}
```

- [ ] **Step 4: 运行 Java 测试，确认网关通过**

Run: `mvn test -Dtest=AcademicControllerTest,ApiContractSmokeTest,AiServiceTest`

Expected: BUILD SUCCESS

- [ ] **Step 5: 提交**

```bash
git add backend-java/src/main/java/com/ai/assistant/backend_java/controller/AcademicController.java backend-java/src/main/java/com/ai/assistant/backend_java/service/AiService.java backend-java/src/test/java/com/ai/assistant/backend_java/controller/AcademicControllerTest.java backend-java/src/test/java/com/ai/assistant/backend_java/service/AiServiceTest.java backend-java/src/test/java/com/ai/assistant/backend_java/controller/ApiContractSmokeTest.java
git commit -m "feat: forward new agent run and workspace APIs in java gateway"
```

### Task 6: 迁移前端 API、工作区模型与测试夹具

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/services/api.test.js`
- Modify: `frontend/src/components/agent/agentWorkspaceModel.js`
- Modify: `frontend/src/components/agent/agentWorkspaceStore.js`
- Modify: `frontend/src/components/agent/AgentWorkspace.jsx`
- Modify: `frontend/src/components/agent/AgentWorkspaceMain.jsx`
- Modify: `frontend/src/components/agent/AgentWorkspaceSidebar.jsx`
- Modify: `frontend/src/components/agent/agentWorkspaceModel.test.js`
- Modify: `frontend/tests/fixtures/mockApi.js`
- Modify: `frontend/tests/fixtures/externalProviderRoute.js`
- Modify: `frontend/tests/e2e/reader-agent-smoke.spec.js`

- [ ] **Step 1: 写前端 API 与工作区模型的失败测试**

```javascript
test('agent api uses workspace and runs resources', async () => {
  await api.getAgentWorkspace('project 1');
  assert.equal(getLastAgentUrl(), '/agent-projects/project%201/workspace');

  await api.createAgentRun('project 1', { prompt: 'Compare methods' });
  assert.equal(getLastAgentUrl(), '/agent-projects/project%201/runs');
});

test('normalizeAgentWorkspaceResponse keeps run review artifacts separate', () => {
  const normalized = normalizeAgentWorkspaceResponse({
    status: 'success',
    workspace: {
      project: { projectId: 'project-1', title: 'Project' },
      activeRun: { runId: 'run-1', status: 'awaiting_plan_review' },
      pendingReview: { runId: 'run-1', status: 'pending' },
      latestArtifacts: { runId: 'run-1', findings: [] },
      recentRuns: [],
      timeline: [],
    },
  });

  assert.equal(normalized.workspace.activeRun.runId, 'run-1');
  assert.equal(normalized.workspace.pendingReview.status, 'pending');
});
```

- [ ] **Step 2: 运行前端测试，确认当前失败**

Run: `npm.cmd test`

Expected: FAIL in `src/services/api.test.js` or `src/components/agent/agentWorkspaceModel.test.js`

- [ ] **Step 3: 改造前端 API 调用与工作区归一化**

```javascript
// frontend/src/services/api.js
getAgentWorkspace: async (projectId) =>
  requestAgentFallback(
    () => agentPrimaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}/workspace`, { skipErrorLog: true }),
    agentSecondaryClient
      ? () => agentSecondaryClient.get(`/agent-projects/${encodeURIComponent(projectId)}/workspace`)
      : null,
  ),

createAgentRun: async (projectId, payload) =>
  requestAgentFallback(
    () => agentPrimaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/runs`, payload, { skipErrorLog: true }),
    agentSecondaryClient
      ? () => agentSecondaryClient.post(`/agent-projects/${encodeURIComponent(projectId)}/runs`, payload)
      : null,
  ),
```

```javascript
// frontend/src/components/agent/agentWorkspaceModel.js
export const normalizeAgentWorkspaceResponse = (response) => ({
  status: `${response?.status ?? ''}`.trim() || 'error',
  workspace: {
    project: normalizeAgentProject(response?.workspace?.project),
    activeRun: normalizeAgentRun(response?.workspace?.activeRun),
    pendingReview: response?.workspace?.pendingReview ?? null,
    latestArtifacts: response?.workspace?.latestArtifacts ?? null,
    recentRuns: Array.isArray(response?.workspace?.recentRuns) ? response.workspace.recentRuns.map(normalizeAgentRun) : [],
    timeline: Array.isArray(response?.workspace?.timeline) ? response.workspace.timeline : [],
    uiHints: response?.workspace?.uiHints ?? {},
  },
});
```

- [ ] **Step 4: 运行前端单测与关键 e2e**

Run: `npm.cmd test`

Expected: PASS with `src/services/api.test.js` and `src/components/agent/agentWorkspaceModel.test.js` green

Run: `npm.cmd run test:e2e -- reader-agent-smoke.spec.js`

Expected: PASS with Agent workspace loading the new aggregate API

- [ ] **Step 5: 提交**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js frontend/src/components/agent/agentWorkspaceModel.js frontend/src/components/agent/agentWorkspaceStore.js frontend/src/components/agent/AgentWorkspace.jsx frontend/src/components/agent/AgentWorkspaceMain.jsx frontend/src/components/agent/AgentWorkspaceSidebar.jsx frontend/src/components/agent/agentWorkspaceModel.test.js frontend/tests/fixtures/mockApi.js frontend/tests/fixtures/externalProviderRoute.js frontend/tests/e2e/reader-agent-smoke.spec.js
git commit -m "refactor: migrate frontend to agent workspace and run resources"
```

### Task 7: 删除新的内部写入对旧 task snapshot 的依赖，并完成回归验证

**Files:**
- Modify: `ai-service-python/services/agent_project_service.py`
- Modify: `ai-service-python/tests/test_agent_project_service.py`
- Modify: `contracts/api-contract-smoke.json`
- Modify: `API.md`
- Modify: `ARCHITECTURE.md`
- Modify: `README.md`

- [ ] **Step 1: 写兼容层只读化的失败测试**

```python
from services import agent_project_service


def test_legacy_task_endpoint_reads_from_new_resources_only():
    snapshot = agent_project_service._build_legacy_task_snapshot(
        {"projectId": "project-1"},
        {"runId": "run-1", "status": "completed"},
        None,
        {"findings": [{"id": "finding-1"}], "conflicts": [], "openQuestions": []},
        [{"id": "entry-1", "type": "final_review_approved"}],
    )

    assert snapshot["taskId"] == "run-1"
    assert snapshot["findings"][0]["id"] == "finding-1"
```

- [ ] **Step 2: 运行最终 Python 回归测试**

Run: `pytest ai-service-python/tests/test_agent_run_service.py ai-service-python/tests/test_agent_review_service.py ai-service-python/tests/test_agent_workspace_service.py ai-service-python/tests/test_agent_state_repository.py ai-service-python/tests/test_agent_project_service.py ai-service-python/tests/test_agent_orchestrator.py ai-service-python/tests/test_api_contract_smoke.py -v`

Expected: PASS

- [ ] **Step 3: 清理旧写入路径并更新文档说明**

```python
# ai-service-python/services/agent_project_service.py
def create_agent_task(project_id: str, request):
    response = run_service.create_run(
        project_id,
        {
            "prompt": request.prompt,
            "focusedPaperIds": request.focusedPaperIds,
            "constraints": request.constraints,
            "context": request.context,
            "allowExternalSearch": request.allowExternalSearch,
        },
    )
    return {"status": "success", "task": _build_legacy_task_snapshot_from_run(response["runId"])}
```

The documentation updates in `API.md`, `ARCHITECTURE.md`, and `README.md` must clearly state that:

1. new write paths are run-based
2. old task paths are compatibility adapters
3. new internal source of truth is resource-shaped, not task-shaped

- [ ] **Step 4: 运行三层最终验证**

Run: `pytest ai-service-python/tests/test_agent_run_service.py ai-service-python/tests/test_agent_review_service.py ai-service-python/tests/test_agent_workspace_service.py ai-service-python/tests/test_agent_state_repository.py ai-service-python/tests/test_agent_project_service.py ai-service-python/tests/test_agent_orchestrator.py ai-service-python/tests/test_api_contract_smoke.py -v`

Expected: PASS

Run: `mvn test -Dtest=AcademicControllerTest,ApiContractSmokeTest,AiServiceTest`

Expected: BUILD SUCCESS

Run: `npm.cmd test`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ai-service-python/services/agent_project_service.py ai-service-python/tests/test_agent_project_service.py contracts/api-contract-smoke.json API.md ARCHITECTURE.md README.md
git commit -m "refactor: finish agent resource migration and keep legacy task adapter"
```

## 计划自检

### Spec 覆盖检查

1. 目标形态 `project / run / review / artifacts / timeline / workspace` 由 Task 1、Task 2、Task 3 覆盖。
2. 混合型 API 与 `workspace` 聚合读模型由 Task 4、Task 5、Task 6 覆盖。
3. 单一 run 状态机与 `executionPhase` 降级由 Task 1 覆盖。
4. 持久化从 task snapshot 转向资源化表结构由 Task 3 覆盖。
5. 三层契约、前端消费和文档迁移由 Task 4、Task 5、Task 6、Task 7 覆盖。
6. 旧 `agent-tasks` 路径降为兼容适配层由 Task 3 和 Task 7 覆盖。

### Placeholder 检查

1. 所有任务都给出了明确文件路径。
2. 每个任务都给出了实际测试代码或实现代码片段。
3. 每个任务都给出了明确命令和预期结果。
4. 没有使用 `TODO`、`TBD` 或“类似 Task N”一类占位说明。

### 类型与命名一致性检查

1. 生命周期主对象统一为 `run`，不再在新实现里把它称作 `task`。
2. 第一阶段审查对象统一为 `PlanReviewPacket` 与 `/plan-review`。
3. 第二阶段审查对象统一为 `FinalReviewPacket` 与 `/final-review`。
4. 聚合读模型统一为 `WorkspaceView` 与 `/workspace`。
