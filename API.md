# API

## 概览

Pixiu Academic Assistant 当前有两条 API 访问路径：

1. 阅读 IDE 链路
   Browser -> Frontend -> Java gateway `http://localhost:8081/api`
2. Agent 研究链路
   Browser -> Frontend -> Python AI service `http://localhost:8000/api`

前端仍保留 Agent 接口走 Java 网关的兼容回退能力，但当前默认行为是：

- `VITE_API_BASE_URL=http://localhost:8081/api`
- `VITE_AGENT_API_BASE_URL=http://localhost:8000/api`

之所以拆成两条链路，是因为阅读 IDE 已经依赖 Java 侧的上传编排和会话持久化，而新的 Agent 工作区需要在本地 Java 运行时尚未重建到最新路由时仍能使用。

## 通用响应形态

大多数接口成功时返回：

```json
{
  "status": "success"
}
```

失败时通常返回：

```json
{
  "status": "error",
  "message": "..."
}
```

部分任务和 trace 接口还会使用 `404`、`409` 或 `400` HTTP 状态码表达资源不存在、索引问题或请求不合法。

## 跨服务契约 Smoke

`contracts/api-contract-smoke.json` 是阅读 IDE 与 Agent 研究关键接口的共享测试契约，当前覆盖 `chat`、`critical`、`background`、`research`、`trace`、`agent-projects`、`agent-tasks` 和 `agent-traces`。Python、Java 和前端测试读取同一份 request/response fixture，分别验证 FastAPI 请求模型与路由、Java `/api` 网关转发，以及前端请求路径和请求体。

契约采用向后兼容规则：`pythonResponseContract` 中声明的必需字段、JSON 类型和枚举值不可删除或改变；响应可以增加未声明的可选字段。任何相关接口字段变化都必须同步更新共享 fixture、三层 contract smoke 和本文件。

## 阅读 IDE API

以下接口主要由单论文阅读工作流使用，并通过 Java 网关访问。

### `POST /api/upload`

上传并解析 PDF。

请求：

- `multipart/form-data`
- 字段：`file`

成功示例：

```json
{
  "status": "success",
  "pdfId": "example_pdf",
  "title": "Example Paper",
  "authors": ["Author A", "Author B"],
  "paper_skeleton": {
    "abstract": "...",
    "introduction": "...",
    "methods": "...",
    "results": "...",
    "discussion": "...",
    "conclusion": "..."
  },
  "paper_structure": {
    "research_problem": "...",
    "core_hypothesis": "...",
    "method_framework": [],
    "claimed_contributions": [],
    "experimental_logic": "...",
    "limitations": "...",
    "outlineVersion": "1.4",
    "sections": []
  },
  "translationLayoutIndex": {},
  "parseStatus": "parsed",
  "ragIndexed": true,
  "ragChunkCount": 42
}
```

说明：

- `pdfId` 是前端后续引用论文的稳定主键。
- `parseStatus` 取值为 `parsed` 或 `scanned_or_low_text`。后者表示 PDF 文本层与 GROBID TEI 正文均低于按页数计算的安全阈值。
- `parseStatus=scanned_or_low_text` 时会额外返回 `parseMessage`，提示先执行 OCR 或更换文字版 PDF；上传本身仍成功，但依赖正文的问答、分析和检索能力可能受限。
- 若 GROBID 未生成 TEI 且 PDF 同样为低文本，接口返回成功的空骨架降级响应并设置 `ragIndexed=false`；PDF 文本充足时仍按解析异常处理。
- 上传成功后，Java 会在 H2 中保存论文记录。

### `POST /api/chat`

单论文问答。

请求示例：

```json
{
  "message": "What is the core method of this paper?",
  "pdfId": "example_pdf",
  "history": [],
  "paperSkeleton": {}
}
```

成功示例：

```json
{
  "status": "success",
  "message": "...",
  "rag_sources": [],
  "sentenceSourceMap": {},
  "queryPlan": {
    "original": "...",
    "rewritten": "...",
    "keywords": [],
    "intent": "explain_method",
    "needsRetrieval": true,
    "queries": [],
    "answerStyle": "concise"
  },
  "retrievalJudge": {
    "verdict": "CORRECT",
    "confidence": 0.82,
    "reason": "...",
    "missingAspects": [],
    "shouldRetry": false
  },
  "traceId": "..."
}
```

### `GET /api/chat/history/{sessionId}`

读取某篇论文的聊天历史。

### `POST /api/explain`

解释选中文本或术语。

常见请求形态：

```json
{
  "text": "cross-attention",
  "pdfId": "example_pdf",
  "pageNumber": 3,
  "context": "..."
}
```

或：

```json
{
  "term": "cross-attention",
  "context": "..."
}
```

常见成功字段：

- `term`
- `explanation`
- `rag_sources`
- `queryPlan`
- `retrievalJudge`
- `traceId`

### `POST /api/translate-page`

翻译当前论文的单页内容。

### `POST /api/critical-reading/{pdfId}`

对当前论文执行证据化批判阅读。

重要响应字段：

- `claims`
- `contributionScore`
- `riskScore`
- `noveltyDimensions`
- `numericEvidenceSummary`
- 可选 `citationGraph`
- `rag_sources`
- `traceId`

说明：

- `contributionScore`、`riskScore` 和 `noveltyDimensions` 是规则型评分，不是训练模型输出。
- `numericEvidenceCandidates` 是证据候选，不是严格自动验证。
- `citationGraph` 必须是真实数据或 `null`，前端不应伪造 fallback 图谱。

### `POST /api/background-knowledge`

生成自适应背景补课内容和学习路径。

请求可包含：

- `pdfId`
- `paperSkeleton`
- `paperStructure`
- `paper_topic`
- 兼容字段 `user_knowledge_level`
- `reader_profile`
- `behavior_signals`

常见响应字段：

- `background_knowledge`
- `graph`
- `learning_path`
- `learning_path_sections`
- `reader_profile`
- `adaptation_reason`
- `rag_sources`
- `confidence`
- `sourceCoverage`
- `provenanceSummary`
- `warnings`
- `externalKnowledge`
- `sqlite`
- `neo4j`
- `traceId`

P2-3 来源与生成约束：

- 服务只读取当前 `pdfId` 对应的论文片段，不检索论文库中的其他论文。
- 概念发现和 prerequisite 关系判断使用两个独立 LLM 阶段。
- `graph.nodes[*]`、`graph.edges[*]` 和 prerequisite `graph.links[*]` 可包含 `provenanceStatus/sourceIds/confidence/confidenceReason`。
- `provenanceStatus` 可为 `current_paper_supported`、`model_inference` 或预留的 `external_supported`。
- `provenanceSummary.nodes/edges` 分别返回 `total/currentPaperSupported/modelInference/externalSupported/supportedRatio`。
- 当前版本的 `externalKnowledge.status` 为 `disabled`，不会联网搜索；模型推断不能视为当前论文或外部来源证据。
- prerequisite 判断失败时响应可包含 `warnings`，并返回空边而不是按概念列表顺序补造依赖关系。
- `sqlite.status` 描述默认图谱快照写入结果；`error` 只表示持久化降级，不改变本次背景图谱的生成结果。`neo4j` 继续表示可选镜像状态。

### `POST /api/socratic-questions`

旧版一次性苏格拉底问题生成接口。

### `POST /api/socratic-session/start`

启动固定 5 轮引导学习会话。

### `POST /api/socratic-session/answer`

提交引导学习会话中的一轮回答。

### `POST /api/research-tasks/brief-preview`

在启动 Deep Research 前生成 brief preview。

### `POST /api/research-tasks`

创建单论文 Deep Research 任务。

### `GET /api/research-tasks/latest?pdfId=...`

恢复某篇论文最近一次 Deep Research 任务快照。

没有快照时返回 `404`。

### `GET /api/research-tasks/{taskId}`

轮询单个 Deep Research 任务快照。

### `POST /api/research-tasks/{taskId}/cancel`

取消 Deep Research 任务。

### Deep Research 人工审查接口

- `POST /api/research-tasks/{taskId}/plan-review`：提交 `{ "subQuestions": ["..."], "reviewNotes": "..." }`，子问题必须为 1–5 个合法非空项；成功后任务从 `awaiting_plan_review` 进入 `running`。
- `POST /api/research-tasks/{taskId}/final-review`：提交 `{ "reviewNotes": "...", "riskReviews": [{ "riskId": "...", "reviewStatus": "reviewed|needs_follow_up" }] }`。成功后任务从 `awaiting_final_review` 进入 `succeeded`。
- 创建任务只启动 Planner。Planner 快照包含 `plan/humanReview/reviewRisks`；等待审查期间可取消，并且服务重启后保持等待状态。
- 非法字段返回 `422`，不允许的状态转换返回 `409`；已进入后续阶段的重复审批返回当前快照。

### `GET /api/traces/{traceId}`

读取脱敏 public trace summary。

说明：

- trace 输出会被刻意裁剪，不暴露完整 prompt、API key 或完整论文正文。
- 已完成的 Deep Research 任务会把 trace summary 写入 SQLite 快照，服务重启后通常仍可恢复。
- `trace.counters` 固定包含基础计数 `llmCalls/retrievalCalls/retryCount/truncationCount/estimatedInputTokens/estimatedOutputTokens`，并兼容包含外部学术检索计数 `externalSearchCalls/externalSearchCacheHits/externalSearchFailures/externalEvidenceCount/externalSearchLatencyMs/externalSearchBudgetBlocks`。
- 外部学术检索 step 只记录 Provider、预算状态、结果数量和脱敏 query 摘要；query 摘要为 `queryHash/queryLength/tokenCount`，不保存完整 query、完整摘要、Provider 响应体、headers 或密钥。
- 外部检索超过任务级默认预算时不会调用 Provider，工具返回 `status=budget_exceeded` 并在 trace 中计入 `externalSearchBudgetBlocks`。
- Deep Research 的对外接口、字段和状态码保持不变；Python 内部已将 planning、sub-question execution、report/conflict aggregation 拆到 `research_planner.py`、`research_executor.py`、`research_aggregator.py`，用于后续低风险替换编排策略。

## Agent 研究 API

以下接口已经实现，并被当前 Agent 工作区使用。它们不再只是规划中的接口草案。

当前前端行为：

- Agent 面板可以创建和列出项目级研究工作区。
- Agent 面板可以删除项目，删除会移除该项目及其任务历史。
- Agent 任务是异步执行的，需要轮询。
- Python 侧会把 Agent 项目、任务和事件摘要写入 SQLite 快照，服务重启后可恢复项目、latest task 和终态任务输出。
- 后端提供项目级任务历史接口，前端进入或切换项目时优先从服务端恢复任务历史。
- 前端仍会在本地快照中保存每个项目的任务历史，作为旧接口、离线或临时失败时的 fallback。

### `POST /api/agent-projects`

创建 Agent 研究项目。

请求示例：

```json
{
  "title": "RAG vs Self-RAG",
  "goal": "Compare research problem, method design, evidence coverage, and limitations.",
  "paperIds": ["rag-paper", "self-rag-paper"]
}
```

成功示例：

```json
{
  "status": "success",
  "project": {
    "projectId": "project-1",
    "title": "RAG vs Self-RAG",
    "goal": "Compare research problem, method design, evidence coverage, and limitations.",
    "paperIds": ["rag-paper", "self-rag-paper"],
    "papers": [
      {
        "pdfId": "rag-paper",
        "title": "rag-paper",
        "indexed": true
      }
    ],
    "latestTaskId": "",
    "defaultConstraints": "",
    "createdAt": "2026-06-14T10:00:00Z",
    "updatedAt": "2026-06-14T10:00:00Z"
  }
}
```

### `GET /api/agent-projects`

列出 Agent 项目。

### `GET /api/agent-projects/{projectId}`

读取单个 Agent 项目。

### `PATCH /api/agent-projects/{projectId}`

更新项目标题、目标或默认约束。

请求示例：

```json
{
  "title": "Method Comparison",
  "goal": "Focus on method and experiment differences.",
  "defaultConstraints": "Prioritize method and experiment sections."
}
```

### `DELETE /api/agent-projects/{projectId}`

删除 Agent 项目。

成功示例：

```json
{
  "status": "success",
  "projectId": "project-1"
}
```

说明：

- 删除项目会同步删除该项目关联的 Agent 任务历史和已持久化事件摘要。
- 项目不存在时返回 `404` 和 `{ "status": "error", "message": "Agent project not found." }`。
- 前端默认删除前会弹出确认，删除后不会重排已有项目标题编号，也不会回退后续默认项目编号。

### `POST /api/agent-projects/{projectId}/papers`

向项目添加论文。

请求示例：

```json
{
  "paperIds": ["toolformer-paper"]
}
```

### `DELETE /api/agent-projects/{projectId}/papers/{pdfId}`

从项目中移除论文。

### `POST /api/agent-projects/{projectId}/tasks`

为项目创建一个异步 Agent 任务。

请求示例：

```json
{
  "prompt": "Compare these papers on research question, method design, experimental evidence, and limitations.",
  "focusedPaperIds": ["rag-paper", "self-rag-paper"],
  "constraints": "Show a comparison table first, then a draft conclusion.",
  "context": {
    "activePaperId": "rag-paper",
    "activeSection": "Method"
  }
}
```

成功示例：

```json
{
  "status": "success",
  "task": {
    "taskId": "agent-task-1",
    "projectId": "project-1",
    "traceId": "trace-1",
    "status": "running",
    "stage": "planning",
    "progress": 0.1,
    "prompt": "Compare these papers on research question, method design, experimental evidence, and limitations.",
    "focusedPaperIds": ["rag-paper", "self-rag-paper"],
    "constraints": "Show a comparison table first, then a draft conclusion.",
    "context": {
      "activePaperId": "rag-paper",
      "activeSection": "Method"
    },
    "planItems": [],
    "events": [],
    "toolCalls": [],
    "evidenceItems": [],
    "findings": [],
    "comparisonTable": {
      "columns": [],
      "rows": []
    },
    "conflicts": [],
    "openQuestions": [],
    "draftReport": "",
    "error": "",
    "createdAt": "2026-06-14T10:05:00Z",
    "updatedAt": "2026-06-14T10:05:00Z"
  }
}
```

执行语义：

- 接口会立即创建任务并返回 `status=running`。
- 当前阶段流转为 `planning -> retrieving -> synthesizing -> done`。
- 前端应通过 `GET /api/agent-tasks/{taskId}` 轮询更新。
- Agent 任务的 API 契约保持不变；Python 内部已将计划项生成、工具调用摘要、证据聚合、对比/冲突/开放问题和报告草稿综合拆到 `agent_orchestrator.py`。
- 服务重启后会从 Agent SQLite 快照恢复任务；重启前仍处于 `running` 或 `pending` 的任务会恢复为 `failed`、`stage=done`、`progress=1.0`，`error` 为 `Agent task was interrupted by service restart.`，并追加 `task_expired` 事件。

### `GET /api/agent-projects/{projectId}/tasks`

读取某项目的 Agent 任务历史。

查询参数：

- `limit`：可选，默认 `20`，Python 侧会约束到 `1..100`；非法或小于等于 0 时回退为 `20`。

成功示例：

```json
{
  "status": "success",
  "projectId": "project-1",
  "limit": 20,
  "tasks": [
    {
      "taskId": "agent-task-2",
      "projectId": "project-1",
      "status": "succeeded",
      "stage": "done",
      "updatedAt": "2026-06-17T10:10:00Z"
    }
  ]
}
```

说明：

- `tasks` 按 `updatedAt` 倒序返回。
- 返回完整 Agent task 快照，字段与 `GET /api/agent-tasks/{taskId}` 一致，前端可直接恢复旧任务详情。
- 项目存在但没有任务时返回 `200` 和空数组。
- 项目不存在时返回 `404` 和 `{ "status": "error", "message": "Agent project not found." }`。

### `GET /api/agent-projects/{projectId}/tasks/latest`

读取某项目最近一次 Agent 任务。

如果项目没有任务，返回 `404`。

### `GET /api/agent-tasks/{taskId}`

轮询单个 Agent 任务快照。

重要任务字段：

- `taskId`
- `projectId`
- `traceId`
- `status`
- `stage`
- `progress`
- `prompt`
- `focusedPaperIds`
- `constraints`
- `context`
- `planItems`
- `events`
- `toolCalls`
- `evidenceItems`
- `findings`
- `comparisonTable`
- `conflicts`
- `openQuestions`
- `draftReport`
- `error`
- `createdAt`
- `updatedAt`

终态状态：

- `succeeded`
- `failed`
- `cancelled`

说明：

- `events` 驱动 Agent 时间线。
- `toolCalls` 描述检索或工具活动；新任务中的每条调用会额外包含可选的 `version` 和 `safetyScope`。`version` 是工具 SemVer，`safetyScope` 固定包含 `access/dataScopes/networkAccess/sideEffects/sensitiveOutput`。
- Agent SQLite 中的旧任务可能没有 `version/safetyScope`，读取和前端展示必须继续兼容；新增字段不会改变任务状态码、轮询方式或其他路由。
- `comparisonTable` 和 `conflicts` 是面向研究过程的轻量输出，不只是最终快照。
- `draftReport` 当前包含 `## Task`、`## Scope`、`## Evidence Snapshot`、`## Current Conclusion`、`## Conflict Candidates` 和 `## Open Questions` 等章节。
- Deep Research 和 Agent 的真实 `conflicts[*]` 可兼容新增 `graphContext`：

```json
{
  "status": "available",
  "paperIds": ["paper-a"],
  "seedTerms": ["accuracy"],
  "nodes": [],
  "edges": [],
  "sourceIds": [],
  "provenanceSummary": {},
  "contextNote": "图谱邻域仅用于解释背景和来源覆盖，不代表自动裁决；冲突仍需人工核查。"
}
```

- `graphContext.status` 取值为 `available`、`partial` 或 `unavailable`。邻域限制为一跳、最多 8 个节点和 12 条边；旧任务和旧客户端可缺省或忽略该字段。
- 该字段只补充已有背景图谱中的上下文与来源覆盖，不改变冲突类型、严重度或人工核查要求；Java 网关继续透传，不新增路由。

### `POST /api/agent-tasks/{taskId}/cancel`

取消 Agent 任务。

### Agent 人工审查接口

- `POST /api/agent-tasks/{taskId}/plan-review`：提交完整 `planItems`、项目内 `focusedPaperIds`、`constraints` 和可选 `reviewNotes`。批准后的研究指令会参与检索 query 与综合上下文。
- `POST /api/agent-tasks/{taskId}/final-review`：提交 `reviewNotes` 与 `riskReviews`，用于核查冲突和开放问题；确认后才进入 `succeeded`。
- `status` 新增 `awaiting_plan_review`、`awaiting_final_review`；对应 `stage` 仍为 `planning`、`synthesizing`。任务快照新增 `humanReview` 与 `reviewRisks`，旧快照可缺省。
- 等待审查的 SQLite 快照可跨重启恢复；`running/pending` 任务仍按原规则恢复为 `failed`。

### `GET /api/agent-traces/{traceId}`

读取 Agent 任务的脱敏 trace summary。

当前复用其他 AI 流程使用的 trace summary 服务。Agent 终态任务会把 public trace summary 写入 SQLite 任务快照；进程内 trace 清空或服务重启后，可通过任务快照按 `traceId` 恢复关键 trace summary。旧 Agent 快照缺少 `traceSummary` 时按空对象兼容。

## Java 到 Python 的转发关系

### 阅读 IDE 映射

| Java API | Python API |
| --- | --- |
| `POST /api/upload` | `POST /api/analyze-pdf` |
| `POST /api/explain` | `POST /api/explain-term` |
| `POST /api/chat` | `POST /api/chat` |
| `POST /api/translate-page` | `POST /api/translate-page` |
| `POST /api/critical-reading/{pdfId}` | `POST /api/deep-analysis` |
| `POST /api/background-knowledge` | `POST /api/background-knowledge` |
| `POST /api/socratic-questions` | `POST /api/socratic-questions` |
| `POST /api/socratic-session/start` | `POST /api/socratic-session/start` |
| `POST /api/socratic-session/answer` | `POST /api/socratic-session/answer` |
| `POST /api/research-tasks` | `POST /api/research-tasks` |
| `POST /api/research-tasks/brief-preview` | `POST /api/research-tasks/brief-preview` |
| `GET /api/research-tasks/latest` | `GET /api/research-tasks/latest` |
| `GET /api/research-tasks/{taskId}` | `GET /api/research-tasks/{taskId}` |
| `POST /api/research-tasks/{taskId}/cancel` | `POST /api/research-tasks/{taskId}/cancel` |
| `GET /api/traces/{traceId}` | `GET /api/traces/{traceId}` |

### 源码中的 Agent 映射

Java 网关源码中已经暴露以下 Agent 路由，并转发到 Python：

| Java API | Python API |
| --- | --- |
| `POST /api/agent-projects` | `POST /api/agent-projects` |
| `GET /api/agent-projects` | `GET /api/agent-projects` |
| `GET /api/agent-projects/{projectId}` | `GET /api/agent-projects/{projectId}` |
| `PATCH /api/agent-projects/{projectId}` | `PATCH /api/agent-projects/{projectId}` |
| `DELETE /api/agent-projects/{projectId}` | `DELETE /api/agent-projects/{projectId}` |
| `POST /api/agent-projects/{projectId}/papers` | `POST /api/agent-projects/{projectId}/papers` |
| `DELETE /api/agent-projects/{projectId}/papers/{pdfId}` | `DELETE /api/agent-projects/{projectId}/papers/{pdfId}` |
| `POST /api/agent-projects/{projectId}/tasks` | `POST /api/agent-projects/{projectId}/tasks` |
| `GET /api/agent-projects/{projectId}/tasks` | `GET /api/agent-projects/{projectId}/tasks` |
| `GET /api/agent-projects/{projectId}/tasks/latest` | `GET /api/agent-projects/{projectId}/tasks/latest` |
| `GET /api/agent-tasks/{taskId}` | `GET /api/agent-tasks/{taskId}` |
| `POST /api/agent-tasks/{taskId}/cancel` | `POST /api/agent-tasks/{taskId}/cancel` |
| `GET /api/agent-traces/{traceId}` | `GET /api/agent-traces/{traceId}` |

不过当前前端默认直接访问 Python Agent API，因为本地 Java 运行时可能滞后于源码更新。

## Python 直接暴露的内部接口

这些接口存在于 Python 服务，但不是当前产品主流程中的浏览器优先入口。

### `POST /api/rag/add-literature`

向 Python 内部 RAG 库上传文献。

### `POST /api/rag/retrieve`

直接调用 Python 侧检索。

## 受限代码执行内部模型（P5-03）

`services/code_execution_models.py` 只定义可持久化的内部任务、审批和产物描述，不注册 FastAPI 路由，不创建 SQLite 数据库，也不授权执行代码。当前系统、旧 SQLite 快照、Java 网关和前端行为均不受影响。

任务快照使用 `schemaVersion=1.0` 和稳定 camelCase 字段：

```json
{
  "schemaVersion": "1.0",
  "jobId": "job-001",
  "status": "awaiting_approval",
  "inputArtifacts": [{"artifactId": "artifact-001", "digest": "<sha256>", "mediaType": "text/csv", "sizeBytes": 1024}],
  "scriptText": "<fixed template text>",
  "scriptDigest": "<sha256>",
  "runtime": {"name": "python", "version": "3.13.9", "templateId": "descriptive-statistics-v1"},
  "image": "sha256:c978142193ccdaa88f63356daa2b0d9c64fdc6de933c643d7cd47286160fdb1e",
  "limits": {"wallClockSeconds": 5, "cpuCount": 1, "memoryBytes": 134217728, "pids": 32, "stdoutBytes": 1048576, "tmpfsBytes": 16777216, "inputBytes": 1048576},
  "networkPolicy": "none",
  "expectedOutputs": [{"name": "statistics", "format": "json", "mediaType": "application/json", "maxBytes": 1048576}],
  "approval": {"decision": "pending", "approvedBy": null, "approvedAt": null, "approvedTaskDigest": null},
  "auditSummary": {"createdAt": "", "updatedAt": "", "event": "code_execution_job_created", "warnings": []},
  "taskDigest": "<canonical task sha256>"
}
```

- `status` 预留 `draft/awaiting_approval/approved/queued/running/succeeded/failed/cancelled`；P5-03 helper 只能创建 `awaiting_approval` 任务、批准为 `approved`，或在执行描述变化后退回 `awaiting_approval`。
- `scriptDigest` 是 `scriptText` UTF-8 字节的 SHA-256；两者必须匹配，但未来持久化时分开存储。
- `taskDigest` 对规范化 JSON 执行 SHA-256，覆盖 `schemaVersion/jobId/inputArtifacts/scriptDigest/runtime/image/limits/networkPolicy/expectedOutputs`，不覆盖脚本文本、状态、审批人、审批时间或审计时间。
- `approval.approvedTaskDigest` 必须等于当前 `taskDigest`。脚本、输入、模板、镜像、配额、网络策略或预期产物发生任何有效变化时清除旧审批；超出固定安全范围的变化直接拒绝。
- 审计摘要只允许有界元数据和警告，不保存 CSV 行、脚本文本、凭据或无限 stdout/stderr。

未来 SQLite 规划使用两个独立表，不在 P5-03 创建：

| 表 | 规划字段 | 边界 |
| --- | --- | --- |
| `code_execution_jobs` | `job_id` 主键、`schema_version`、`status`、`task_digest`、`snapshot_json`、`created_at`、`updated_at` | `snapshot_json` 保存除 `scriptText` 外的完整 camelCase 快照；读取后必须重新校验模型与 digest。 |
| `code_execution_scripts` | `job_id` 主键/外键、`script_text`、`script_digest` | 脚本文本与摘要分列；读取时重新计算 SHA-256，不允许 Worker 修改。 |

后续引入存储层时应在单个事务中写入两表，禁止只恢复其中一部分；旧系统不需要迁移或预建表。

## 关键数据结构

### Council 内部模型

`services/council_service.py` 不注册独立 FastAPI 路由。内部入口为 `run_council(question, evidence_items, provider=None)`，同一 Provider 分别接收 evidence reviewer 与 contradiction reviewer 的独立请求；任一请求不得包含另一 Reviewer 的输出。P4-06 仅通过上述默认关闭的 Deep Research Pilot 调用该内部入口，不增加 Council UI 或独立 `/api`。

```json
{
  "opinions": [{"reviewerId": "evidence-reviewer", "role": "evidence_reviewer", "provider": "fixture", "model": "offline-council-evidence-reviewer", "verdict": "supported", "conclusion": "证据支持该结论。", "reason": "给定来源提供直接支持。", "sourceIds": ["source-1"], "confidence": 0.82, "abstain": false, "abstainReason": "", "usage": {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30, "estimated": false}}],
  "agreements": [],
  "disagreements": [],
  "abstentions": [],
  "evidenceCoverage": {"allowedSourceCount": 1, "citedSourceCount": 1, "sharedSourceIds": ["source-1"], "uncitedSourceIds": [], "ratio": 1.0},
  "recommendedAction": "accept_with_caution"
}
```

- opinion `verdict` 兼容值为 `supported/insufficient/conflict/abstain`；证据不足、解析失败、Provider 失败或非法引用最终归一为 `abstain`。
- 强 agreement 必须由两份非弃权意见在相同 verdict 下共享至少一个 `sourceId`；相同 verdict 但引用不相交时输出 `evidence_basis_disagreement`，不得伪装成共识。
- 不同 verdict 输出 `verdict_disagreement`，保存双方 `positions/sourceIds/reason` 并标记 `highRisk=true`。聚合器不选择获胜意见或自动裁决冲突。
- `recommendedAction` 仅为 `manual_review_required`、`collect_more_evidence` 或 `accept_with_caution`。

### Evidence Item

`rag_sources`、`sources` 和 Agent evidence 中常见字段：

- `sourceId`
- `id`，部分旧流程中的兼容别名。
- `sourceType`
- `text`
- `pdfId`
- `pageIndex`
- `sectionId`
- `chunkIndex`
- `metadata`
- `similarity`
- `score`

说明：

- `pageIndex` 是 0-based。
- 前端展示页码时通常使用 `pageIndex + 1`。
- 旧缓存或旧索引可能没有页码锚点。

### Agent Event Item

Agent 时间线使用以下事件对象：

- `eventId`
- `type`
- `timestamp`
- `taskId`
- `stage`
- `summary`
- `meta`

当前常见事件类型：

- `task_created`
- `task_started`
- `task_understood`
- `plan_generated`
- `retrieval_started`
- `paper_evidence_collected`
- `tool_completed`
- `judgement_completed`
- `report_updated`
- `task_completed`
- `task_cancelled`
- `task_failed`
- `task_expired`

## 前端 Agent 状态说明

前端 Agent 工作区在 API 之上增加了一层本地状态：

- 项目级任务历史优先来自 `GET /api/agent-projects/{projectId}/tasks`。
- `tasksByProjectId` 仍保存浏览器快照，作为服务端历史接口不可用时的 fallback。
- 切换项目时优先从服务端恢复历史，失败时从该 map 恢复历史。
- 当前任务可以在旧任务之间切换。
- 任务历史会作为前端快照持久化。
- 阅读 IDE 的推荐下一步可以切换到 Agent 研究模式；该动作不新增 API、不自动创建项目或任务，只通过前端 `activePaperId` 把当前论文带入 Agent 项目草稿。
- 默认项目标题使用本地快照中的 `nextProjectNumber` 单调递增；旧快照缺少该字段时，会按现有 `Agent 项目 N` 标题最大值和项目数量推导。
- 删除项目不会重排已有项目标题编号，也不会降低 `nextProjectNumber`。

## 错误处理建议

- 同时读取 HTTP 状态码和响应体中的 `status/message`。
- `latest` 任务接口返回 `404` 时，应视为正常空态。
- `paper_not_indexed` 或检索 fallback 应作为可引导用户处理的业务状态，而不是通用崩溃。
- 缺失 trace 或任务时不要伪造恢复成功。

## 调试清单

如果 Agent 请求失败，优先检查：

1. 阅读 IDE base URL 是否仍指向 `http://localhost:8081/api`。
2. Agent base URL 是否指向 `http://localhost:8000/api`，或 Java 网关是否已重建。
3. Python 服务 CORS 是否允许前端来源。
4. GROBID 和 Python RAG 是否可用。
5. 项目挂载的论文是否已经完成索引。

## 只读 MCP adapter（非 `/api` 接口）

P2-2 新增独立的本机 MCP `stdio` server。它不监听 HTTP、不挂载 FastAPI，也不经过 Java 网关；因此以下能力不属于 `/api` 路由。

启动前必须在 MCP 客户端进程环境中设置：

```text
PIXIU_MCP_ENABLED=true
```

启动命令：

```bash
cd ai-service-python
python -m mcp_adapter
```

MCP 协议 `tools/list` 仅返回：

- `read_paper_skeleton`：整理客户端请求中提供的论文骨架，不读取服务器文件。
- `retrieve_current_paper`：按 `pdfId + query` 检索当前论文的有限证据片段。
- `retrieve_library`：从内部文献索引检索有限证据片段。

每个工具的 `inputSchema/outputSchema` 来自内部 `tool_registry`，`_meta.pixiu` 包含 `schemaVersion/version/safetyScope/runtimeBudgets`。`tools/call` 仍经过 `ToolRegistry.invoke()` 的严格输入输出校验。

MCP 额外限制：当前论文检索拒绝 `includeAll=true`；`retrieve_current_paper` 的 `topK/limit/maxTextChars` 上限为 `8/5/900`，`retrieve_library` 为 `5/4/700`，论文骨架的 `maxSections/maxCharsPerSection` 上限为 `6/220`。成功调用同时返回 JSON text content 和 `structuredContent`；验证错误保留工具名和字段路径，其他内部异常只返回脱敏 tool error。
