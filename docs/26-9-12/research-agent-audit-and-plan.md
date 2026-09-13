# 研究 Agent 现状审计与开发计划

审计日期：2026-09-12

## 1. 产品目标

研究 Agent 的产品边界如下：

- 左侧管理研究项目、项目下的研究任务和项目组成论文。
- 右侧是以任务为上下文的连续对话。
- 用户发送研究问题后，Agent 自动规划、检索项目论文、提取证据、比较分析并生成回答。
- 研究链默认收起，展开后显示真实的计划、检索、分析和生成步骤。
- 回答中的结论必须关联证据，证据能够跳转到对应论文页码或章节。
- 项目、任务、消息、运行状态、研究链、证据和报告在刷新及服务重启后仍可恢复。

目标领域关系：

```text
Project
  ├─ Paper[]
  └─ Task[]
       ├─ Message[]
       └─ Run[]
            ├─ Step[]
            ├─ Evidence[]
            └─ Artifact[]
```

其中：

- Task 表示用户可持续对话的一项研究任务。
- Message 表示任务中的用户或 Agent 消息。
- Run 表示 Agent 响应某一条用户消息时的一次后台执行。
- Step、Evidence 和 Artifact 均属于某次 Run。

## 2. 当前真实调用链

### 2.1 页面入口

```text
App.jsx
  → AgentResearchPage.jsx
  → AgentWorkspace.tsx
  → AgentWorkspaceSidebar.jsx / AgentWorkspaceMain.jsx
```

`AgentResearchPage` 将论文库、当前论文、保存产物和原文跳转能力传给 `AgentWorkspace`。

### 2.2 API 链路

```text
frontend/src/services/api.ts
  → http://localhost:8081/api
  → AcademicController.java
  → AiService.java
  → AgentGatewayService.java
  → http://ai-service:8000/api
  → routes/agent_routes.py
  → services/agent_project_service.py 等服务
```

Java 层主要承担转发。Python 层负责项目、任务运行、证据检索、研究产物和 SQLite 持久化。

### 2.3 当前存在的两条任务执行路径

稳定的项目运行路径：

```text
POST /agent-projects/{projectId}/runs
  → create_agent_run
  → SQLite 保存项目归属和 run
  → prepare_agent_task_now
  → 等待计划审核
  → review_agent_run_plan
  → _run_minimal_agent_task
  → 检索、综合、报告
  → 等待最终审核
```

实验性 LangGraph 路径：

```text
POST /agent-graph
  → run_agent_graph
  → LangGraph StateGraph
  → MemorySaver
  → 等待计划审核
  → POST /agent-graph/{threadId}/resume
```

前端当前优先调用实验性路径，失败后才调用稳定的项目运行路径。

## 3. 能力审计

| 能力 | 现状 | 结论 |
|---|---|---|
| 创建、查询、更新、删除项目 | Python SQLite + Java 网关 + 前端已接通 | 可用 |
| 项目关联多篇论文 | 保存 `paperIds`，前端以论文库补全标题 | 基本可用 |
| 项目任务历史 | 稳定路径保存到 SQLite | 可用，但前端优先路径绕开它 |
| 创建研究运行 | `/agent-projects/{projectId}/runs` 可创建 | 可用 |
| 跨论文 RAG 检索 | `retrieve_current_paper` 按 `pdfId` 过滤向量库 | 可用 |
| 证据字段 | 支持 `sourceId/pdfId/chunkIndex/pageIndex/sectionId/text` | 基本可用 |
| 点击证据跳转原文 | 有 `pageIndex` 时可跳转 | 部分可用，取决于索引元数据 |
| 研究链 | 有 plan、timeline、toolCalls、evidence | 数据存在，但两套结构不统一 |
| 跨论文比较 | 有比较表、冲突和开放问题结构 | 主要为规则模板，分析质量有限 |
| LLM 综合回答 | 有 LLM 综合函数 | 稳定主运行链没有使用完整综合函数 |
| 连续对话 | 没有 Message 实体或消息存储 | 不可用 |
| 任务内追问 | 每次输入都创建新的 task/run | 不可用 |
| 刷新恢复 | SQLite 路径可恢复，前端另有 localStorage 快照 | 部分可用 |
| 服务重启恢复 | SQLite 路径支持 | 可用 |
| LangGraph 重启恢复 | 使用进程内 `MemorySaver` | 不可用 |
| 停止运行 | 稳定 task 路径支持取消 | 部分可用；LangGraph 路径未接入取消 |
| 失败重试 | 没有明确重试接口和重试关系 | 不可用 |
| 自动完成研究 | 当前需要计划审核和最终审核 | 与目标交互不符 |
| 研究报告 | 可生成 `draftReport` 并持久化 | 基本可用，内容质量需提升 |
| 外部学术检索和网页检索 | 已有配置、工具、预算与降级结构 | 条件可用，依赖提供方配置 |
| 模型提供方 | 当前运行配置以 DeepSeek 为主 | 已接入；GLM 是开发者，不是当前运行模型 |

## 4. P0 问题

### P0-1 前端任务创建优先走错误的执行入口

`AgentWorkspace.handleCreateTask` 首先调用 `runAgentGraph`。该接口请求中没有 `projectId`，返回值经 `normalizeAgentGraphResponse` 转换后明确设置 `projectId: ''`。

随后 `cacheTask` 因任务没有 `projectId` 直接返回，因此成功创建的 LangGraph thread 可能不会进入当前项目任务列表，也不会成为可靠的当前任务。

实际接口验证结果：

```json
{
  "taskId": "<threadId>",
  "projectId": "",
  "status": "awaiting_plan_review"
}
```

影响：用户点击发送后，后端可能已经创建内存任务，但界面和项目历史无法可靠显示或恢复。

修复方向：前端统一使用 `/agent-projects/{projectId}/runs` 作为唯一正式入口。`/agent-graph` 暂时保留为后端实验接口，不进入产品主链。

### P0-2 LangGraph 状态不持久化

`agent_langgraph.py` 使用模块级 `MemorySaver`。它只能在当前 Python 进程存活期间保存 thread，容器重启后状态丢失。

影响：刷新可能短期可查询，服务重启后无法恢复；也无法通过项目工作区列出。

修复方向：第一阶段从产品主链移除；后续如继续采用 LangGraph，应使用 SQLite/Postgres checkpointer，并让 graph run 关联 `projectId/taskId/runId`。

### P0-3 当前还不是对话式任务

当前 `taskId` 与 `runId` 实际为同一 ID。任务对象只有一个 `prompt`，没有 `messages`、`parentMessageId`、`turnIndex` 或消息存储表。

影响：右侧虽然呈现用户气泡和 Agent 卡片，但只能展示一次问题和一次结果。用户再次输入会创建新的任务，无法继承当前任务的对话上下文。

修复方向：分离 Task、Message 和 Run，新增任务消息接口。

### P0-4 自动研究流程被两次人工审核阻断

稳定路径创建 run 后停在 `awaiting_plan_review`，生成草稿后停在 `awaiting_final_review`。目标界面没有把审批作为主要交互，用户预期发送后直接研究并回答。

影响：研究链不能从输入自动走到回答；计划审核位于展开区域内，用户可能不知道为什么任务不继续。

修复方向：为正式对话链增加自动执行模式。计划和风险仍记录在研究链中，但不要求用户逐次批准。人工审核模式可以作为后续高级设置。

### P0-5 正式持久化路径没有使用完整 LLM 综合能力

`_run_minimal_agent_task` 调用 `build_agent_outputs` 和 `build_minimal_report`。其中主要结论由规则和模板生成。更完整的 `agent_orchestrator.execute_run` 会执行 `advanced_analysis` 和 `synthesize_llm_report`，但没有被正式项目运行链调用。

影响：界面可能显示“研究完成”，回答却主要是证据数量、关键词和固定英文模板，无法满足真实的论文比较问题。

修复方向：在持久化 run worker 中接入统一的、证据约束的 LLM 综合服务，并把回答保存为 Agent message 和 run artifact。

### P0-6 检索失败会生成伪证据占位符

稳定路径的 `_fallback_tool_result` 会生成文本为 `Fallback project evidence placeholder...` 的 evidence item。

影响：失败占位符进入证据数组、比较表和报告后，可能被界面当成真实论文证据。

修复方向：检索失败应记录 tool error 和 evidence gap，不能生成 evidence item。没有证据时回答必须明确说明无法形成结论。

## 5. P1 问题

- 项目中的 `papers` 是由 ID 生成的 stub，服务端没有保存论文标题、作者和版本快照。
- 前端同时依赖服务端状态和 localStorage 快照，可能出现服务端已删除、前端仍显示旧任务的短暂不一致。
- `openQuestions` 在 LangGraph 适配器中被转换成对象，而主 `AgentTask` 类型定义为字符串数组，契约不一致。
- LangGraph 适配器丢失 `constraints`、external search 状态、trace 和 report source 映射。
- 主运行链的 cancel 依赖线程周期性检查；没有统一的 run cancel API。
- clarification 接口存在，但当前正式执行链没有明确进入 `awaiting_clarification` 的触发节点。
- 研究链同时使用 events、timeline 和 researchTimeline 三套字段。
- 前端以 `findings[0].summary` 优先显示回答，可能遮盖内容更完整的 `draftReport` 或 LLM synthesis。
- 没有任务重试、从失败步骤继续、运行幂等键和重复提交保护。

## 6. 已验证事实

### 自动化测试

在当前 `ai_service_python` 容器中执行：

```text
tests/test_agent_project_service.py
tests/test_agent_workspace_service.py
tests/test_agent_run_service.py
tests/test_agent_langgraph.py
```

结果：69 passed，2 subtests passed。

### 真实网关闭环

通过 `http://localhost:8081/api` 完成了临时项目创建、run 创建、workspace 查询和项目清理：

```text
projectStatus: success
runStatus: success
workspaceProjectId 与 projectId 一致
activeRunStatus: awaiting_plan_review
recentRunCount: 1
```

这证明 Java 网关与 Python 的持久化项目运行链当前可连接。

### 验证限制

本机 Maven 使用的 JDK 版本低于项目编译目标，Java 测试未能启动。正在运行的 Java 容器网关已通过上述真实接口闭环验证。

## 7. 开发批次

### 批次 1：统一正式执行入口

目标：让前端创建的研究任务可靠进入当前项目、可显示并可恢复。

范围：

- 前端创建任务只调用 `/agent-projects/{projectId}/runs`。
- 轮询只读取 project workspace 或 `/agent-runs/{runId}`。
- 计划与最终审核只调用 `/agent-runs/{runId}/*-review`。
- 删除前端产品主链中的 LangGraph 优先调用和静默三级回退。
- 保留旧 task 读取适配器用于历史兼容；不用于创建新任务。
- 不改视觉样式。

验收：

- 新 run 的 `projectId` 等于当前项目 ID。
- 发送后当前任务立即可见。
- 刷新页面后该任务仍在对应项目下。
- Python 服务重启后仍可恢复。
- API 失败时显示真实错误，不创建孤立 graph thread。
- 前端类型检查、Agent 单元测试和生产构建通过。

### 批次 2：自动执行模式

目标：发送问题后自动完成计划、检索、综合和回答。

- 给 run 增加明确的 `reviewMode` 或 `autoExecute` 字段。
- 自动模式保存计划后直接执行。
- 生成报告后直接完成 run，同时保留风险记录。
- 研究链显示真实步骤，不显示审批操作。
- 手动审核模式保留为兼容能力，不作为默认入口。

### 批次 3：Task、Message、Run 数据模型

目标：建立真正的任务内连续对话。

- 新增独立 Task 实体。
- 新增 Message 持久化表和接口。
- 每条用户消息创建一个 Run。
- Agent 完成后追加 Agent message。
- 新问题默认继承当前任务历史和项目论文范围。
- 创建“新任务”时才清空对话上下文。

### 批次 4：证据约束回答

目标：输出能够直接回答研究问题的中文综合结论。

- 移除伪证据 fallback item。
- 统一证据结构和定位字段。
- 接入证据约束的 LLM 综合。
- 每个核心结论保存 `sourceIds`。
- 无证据、单篇证据和冲突证据分别使用明确状态。

### 批次 5：前端对话和研究链接入

目标：当前参考图对应的交互全部由真实数据驱动。

- 消息列表读取 Task messages。
- 用户消息、Agent 运行状态、Agent 回答按时间排列。
- 研究链对应每次 Run，可展开查看。
- 引用点击打开对应论文和页码。
- 页面刷新恢复当前项目、任务和消息。

### 批次 6：失败恢复和端到端质量门

- 增加 retry run 接口和 `retryOfRunId`。
- 添加提交幂等键。
- 容器重启恢复测试。
- 多论文真实 PDF 端到端测试。
- 引用完整率、无证据拒答率和跨论文覆盖率测试。

## 8. GLM 开发提示词：批次 1

```text
你负责实施 Pixiu Academic Assistant 研究 Agent 的“批次 1：统一正式执行入口”。

仓库：D:\aiproj\ai_project

先阅读：
- docs/26-9-12/research-agent-audit-and-plan.md
- frontend/src/components/agent/AgentWorkspace.tsx
- frontend/src/components/agent/agentWorkspaceModel.ts
- frontend/src/services/api.ts
- ai-service-python/routes/agent_routes.py
- ai-service-python/services/agent_project_service.py

本批目标：
前端创建的研究任务必须通过项目持久化 run 接口执行，并可靠归属当前项目。不要开发多轮对话、自动审核、回答质量和新 UI。

必须修改：
1. AgentWorkspace.handleCreateTask 不再优先调用 apiService.runAgentGraph。
2. 新任务只调用 apiService.createAgentRun(activeProject.projectId, payload)。
3. 创建成功后使用返回的 run 或重新读取 workspace，将任务设置为当前任务并加入当前项目任务列表。
4. 运行轮询不再读取 getAgentGraphState；统一读取项目 workspace，必要时读取 getAgentRun。
5. 计划审核只调用 reviewAgentRunPlan。
6. 最终审核只调用 reviewAgentRunFinal。
7. 新任务创建、审核和轮询过程不得静默回退到 /agent-tasks 兼容接口。
8. 旧 task 列表和读取兼容逻辑可以保留，仅用于读取历史数据。
9. 不删除 Python 的 /agent-graph 路由，本批只把它移出正式前端链路。
10. 不修改当前前端布局、颜色、文案和卡片样式。

错误处理：
- 正式接口失败时在现有 state.error 中显示后端消息。
- 不吞掉异常。
- 不创建无 projectId 的前端任务。

测试要求：
- 增加或修改前端测试，验证创建任务调用 createAgentRun，参数包含当前 projectId。
- 验证不会调用 runAgentGraph 或 createAgentTask。
- 验证 createAgentRun 返回后当前任务的 projectId 正确。
- 验证计划与最终审核使用 run API。
- 运行 npm.cmd test、npm.cmd run typecheck、npm.cmd run build。

限制：
- 不修改 docs/26-9-12/research-agent-audit-and-plan.md。
- 不重构无关代码。
- 不覆盖仓库中已有未提交改动。
- 不提交 git commit。

交付时输出：
1. 修改文件清单。
2. 每项行为变化。
3. 测试命令和完整结果。
4. git diff --check 结果。
5. 仍未解决的问题，必须明确属于后续哪个批次。
```

## 9. 评审规则

GLM 每批提交后由 Codex 执行以下评审：

1. 对照本批范围检查是否夹带其他重构。
2. 阅读完整 diff，检查错误处理和状态一致性。
3. 独立运行测试，不直接采用 GLM 的测试结论。
4. 通过真实 Java 网关执行最小闭环。
5. 检查刷新、项目切换和失败路径。
6. 发现问题后给 GLM 精确修复提示词；评审通过后才进入下一批。
