# Architecture

## 概览

Pixiu Academic Assistant 是一个多服务协作的论文阅读工作台，目前包含两个主要产品界面：

1. 阅读 IDE
   面向单篇论文阅读、分析和学习。
2. Agent 研究
   面向多论文项目工作区和阶段式异步研究任务。

系统分为三层：

1. `frontend`
   负责 UI、浏览器状态、会话恢复和 PDF 交互。
2. `backend-java`
   负责网关、上传编排、H2 持久化和阅读 IDE 的统一 `/api`。
3. `ai-service-python`
   负责 PDF 解析、检索、证据处理、AI 编排、长任务和 trace。

配套服务：

- `GROBID`：PDF 结构抽取。
- `ChromaDB` 和 embeddings：检索。
- 可选 `Neo4j`：背景知识持久化增强。

## 系统链路

### 阅读 IDE 链路

主阅读产品仍使用 Java 网关：

```text
Browser
  -> Frontend (React/Vite)
  -> Backend Java (/api)
  -> AI Service Python (/api)
  -> GROBID / Chroma / optional Neo4j
```

这条链路存在的原因：

- 上传和会话管理已经依赖 Java 侧持久化。
- 阅读 IDE 仍围绕稳定的统一网关契约组织。

### Agent 研究链路

当前 Agent 工作区默认使用另一条链路：

```text
Browser
  -> Frontend Agent workspace
  -> Python AI service (/api) directly by default
```

这样设计的原因：

- Agent 接口在三层源码里已经加入，但本地 Java 运行时可能不会立即重建。
- 直连 Python 可以保证 Agent 面板在本地迭代中保持可用。
- 如果 Java 路由可用，前端仍保留回退兼容空间。

## 前端架构

### 主工作区

`frontend/src/App.jsx` 仍负责应用模式和高层阅读状态。

主要 UI 区域：

- 顶部导航 `Navbar`。
- 左侧论文库和阅读导航。
- 中央 PDF 阅读器和工具栏。
- 右侧功能工作区。
- 底部知识沉淀工作台。

应用模式：

- `reader`。
- `agent`。

### 阅读 IDE 模块

阅读 IDE 由多个可复用面板组成：

- `ChatPanel`。
- `PaperAnalysis`。
- `TranslationPanel`。
- `CriticalAnalysisPanel`。
- `BackgroundKnowledgePanel`。
- `SocraticQuestionsPanel`。
- `DeepResearchPanel`。
- `BottomWorkbench`。

这些面板消费已经归一化的接口输出和浏览器侧持久化状态。

### Agent 工作区模块

Agent 面板已经从单个大型原型文件拆成多个更容易维护的子组件。

关键文件：

- `frontend/src/components/agent/AgentWorkspace.jsx`
- `frontend/src/components/agent/AgentWorkspaceMain.jsx`
- `frontend/src/components/agent/AgentWorkspaceMainSections.jsx`
- `frontend/src/components/agent/AgentWorkspaceMainComposer.jsx`
- `frontend/src/components/agent/AgentWorkspaceSidebar.jsx`
- `frontend/src/components/agent/AgentWorkspaceSidebarSections.jsx`
- `frontend/src/components/agent/AgentWorkspaceEvidenceSections.jsx`
- `frontend/src/components/agent/agentWorkspaceModel.js`
- `frontend/src/components/agent/agentWorkspaceUi.js`
- `frontend/src/components/agent/agentWorkspaceStore.js`

当前 Agent UI 职责：

- 展示项目列表。
- 创建项目。
- 切换项目。
- 恢复项目级任务历史。
- 从项目历史中选择当前任务。
- 展示计划、时间线、工具调用、证据、对比、冲突、开放问题和报告草稿。

### 前端 Agent 状态模型

Agent 工作区现在维护项目级任务历史：

- `projects`
- `activeProjectId`
- `currentTask`
- `tasksByProjectId`

`tasksByProjectId` 是当前保留下来的兼容缓存状态。它支持：

- 每个项目保存多个任务。
- 切换项目时恢复对应任务。
- 在旧任务和新任务之间切换。
- 服务端任务历史接口不可用时通过快照恢复。

正常路径下，Agent 工作区进入、切换、刷新和轮询会优先调用 `GET /api/agent-projects/{projectId}/workspace` 读取聚合视图；`tasksByProjectId` 只保留为旧接口、离线或临时失败时的 fallback 和历史展示缓存。

阅读 IDE 的推荐下一步现在由前端模型统一生成，按当前面板、解析状态、Deep Research 状态和工作台沉淀数量给出 2-3 个动作。Agent 动作只切换到 `agent` 模式，并沿用 `activePaperId` 将当前论文带入 Agent 新项目草稿；不会自动创建项目或启动任务。

## 浏览器持久化

### IndexedDB

浏览器使用 IndexedDB 恢复本地工作现场。

保存内容包括：

- PDF Blob。
- 聊天记录。
- 篇章解构结果。
- 批判阅读结果。
- 高亮和笔记。
- 翻译状态。
- 背景补课结果。
- 工作台产物。
- 论文库记录。
- Agent 工作区快照，包括 `tasksByProjectId`。

### 轻量 UI 状态

当前 tab、上次打开论文等轻量 UI 状态仍单独存储在浏览器本地存储中。

## Java 网关架构

### 职责

Java 层保持轻量：

- 向阅读 IDE 暴露稳定 `/api`。
- 转发请求到 Python。
- 在 H2 中保存论文和聊天记录。
- 归一化部分请求或响应结构。

### 关键类

- `AcademicController`
- `AiService`
- `PaperRepository`
- `ChatMessageRepository`

### Java 侧 Agent 状态

Java 源码中已经包含 Agent 转发路由：

- `/api/agent-projects`
- `/api/agent-projects/{projectId}`
- `/api/agent-projects/{projectId}/papers`
- `/api/agent-projects/{projectId}/tasks`
- `/api/agent-projects/{projectId}/tasks` GET 历史列表
- `/api/agent-projects/{projectId}/tasks/latest`
- `/api/agent-projects/{projectId}/workspace`
- `/api/agent-projects/{projectId}/runs`
- `/api/agent-runs/{runId}`
- `/api/agent-runs/{runId}/artifacts`
- `/api/agent-runs/{runId}/timeline`
- `/api/agent-runs/{runId}/plan-review`
- `/api/agent-runs/{runId}/final-review`
- `/api/agent-tasks/{taskId}` compatibility adapter
- `/api/agent-tasks/{taskId}/cancel`
- `/api/agent-traces/{traceId}`

但当前产品运行时不依赖 Java 访问 Agent，因为前端默认直连 Python Agent API。

## Python AI 服务架构

### 入口和路由

主要入口文件：

- `main.py`
- `app.py`
- `routes/api.py`

`app.py` 创建 FastAPI 应用并配置本地前端 CORS。

### 模块分组

Python 服务大致分为：

- `core/`
  PDF 解析、章节抽取、chunking 和 outline。
- `services/`
  聊天、翻译、背景补课、批判阅读、研究任务、Agent 任务、trace 和安全。
- `rag/`
  检索和索引封装。
- `schemas/`
  请求模型。

### 核心服务职责

#### `analysis_service.py`

负责：

- 上传后的 PDF 分析。
- GROBID 解析。
- 论文骨架和结构抽取。
- chunk 生成与 RAG 索引。
- 批判阅读和相关证据化输出。

#### `chat_service.py`

负责：

- 论文问答。
- 术语解释。
- 苏格拉底式学习。
- 逐页翻译入口。

阅读问答不是单次裸 prompt 调用，而是轻量证据流程：

1. 构建 query plan。
2. 优先检索当前论文。
3. 必要时补充内部文献库。
4. 判断证据质量。
5. 必要时自动重试一次。
6. 基于证据生成回答并附带来源。

#### `research_task_service.py`

负责单论文 Deep Research：

- brief preview。
- 异步任务执行。
- 轮询。
- 取消。
- latest 快照恢复。
- SQLite 持久化。

它现在保留任务生命周期、取消、轮询和 SQLite 快照职责；具体研究编排边界已拆出：

- `research_planner.py`：研究 brief、初始子问题计划和 follow-up 计划。
- `research_executor.py`：单个子问题的 query plan、检索、JUDGE、retry 和 finding 输出。
- `research_aggregator.py`：冲突检测、报告综合和 trace judge 汇总。

当前任务阶段：

- `planning`
- `retrieving`
- `judging`
- `synthesizing`
- `done`

Deep Research 和 Agent 均在现有任务生命周期内实现两个人工 gate：Planner 输出后以 `awaiting_plan_review` 暂停，批准的完整计划成为 Executor 输入；Aggregator 输出草稿和 `reviewRisks` 后以 `awaiting_final_review` 暂停，终稿审批写入 `humanReview` 后才进入 `succeeded`。等待状态及执行上下文保存在各自 SQLite 快照中，前端等待期间停止轮询。

#### `agent_project_service.py`

这是当前 Agent 研究项目和任务生命周期的后端核心。

它负责：

- 创建、列出、读取、更新项目。
- 添加或移除项目论文。
- 创建异步 Agent 任务。
- 查询 Agent 任务。
- 取消 Agent 任务。

2026-07-08 起，这个模块还承担“兼容适配层”职责：

- 对外已经暴露 `workspace + runs` 主资源，同时继续保留 `agent-tasks` 兼容路径，避免旧调用方一次性失效。
- 对内开始复用拆分后的 run / review / artifact / timeline / workspace 边界，而不是继续把所有状态都堆在单个 task snapshot 上。
- `_build_legacy_task_snapshot(...)` 明确用于把新资源形态适配回旧任务快照，方便前端与 Java 网关在迁移完成前继续读取。

当前 Agent 任务阶段：

- `planning`
- `retrieving`
- `synthesizing`
- `done`

当前任务行为：

- 创建项目级任务。
- 按论文收集证据。
- 聚合规范化 evidence item。
- 构建对比表。
- 生成冲突候选。
- 生成开放问题。
- 生成报告草稿。

任务生命周期仍由 `agent_project_service.py` 管理；计划项生成、检索工具调用摘要、证据聚合、对比表、冲突候选、开放问题和草稿报告综合已拆到 `agent_orchestrator.py`，后续可以在该边界内替换更强的 Agent 执行策略。

第一阶段资源化重构已经落地的内部边界：

- `agent_run_service.py`：维护 Agent run 状态机，主状态为 `draft / awaiting_plan_review / queued / running / awaiting_final_review / completed / failed / cancelled`，`executionPhase` 只作为运行中的附加阶段信息。
- `agent_review_service.py`：生成并维护计划审查与终稿审查 packet。
- `agent_artifact_service.py`：承载 findings、conflicts、open questions、draft report 等运行产物。
- `agent_timeline_service.py`：负责 run 时间线条目的追加与读取。
- `agent_workspace_service.py`：负责把项目、活动 run、待处理审查、最新产物与时间线聚合成工作区视图。
- `agent_state_repository.py`：提供新的 SQLite 资源持久化入口，单独保存 project/run/plan review/artifacts/timeline，而不再只依赖旧 `agent_tasks` 表形态。

这意味着当前 Agent 的“内部真相”已经从 task-shaped snapshot 迁移到 resource-shaped records；公开 API 以 run/workspace 资源为主，旧 `agent-tasks` 只负责兼容映射。

当前 AI 结论行为：

- 报告草稿不再是通用空占位。
- 服务会根据论文证据密度、支持画像和共同主题生成规则型结论。
- 报告里显式包含冲突候选和开放问题。

当前重要限制：

- Agent 项目、任务和事件摘要已保存到 Python SQLite 快照。
- 后端已经提供项目级任务历史接口，按 `updatedAt` 倒序返回完整任务快照。
- Python 服务重启后会恢复终态 Agent 任务；重启前仍在运行的任务会标记为 `failed` 并记录 `task_expired` 事件。

#### `council_service.py`

这是 Council Reviewer 的内部边界。服务复用 Provider 中立的 `LLMProvider`，以两个互不可见的请求分别生成 evidence reviewer 与 contradiction reviewer 意见；证据最多 8 条、每条最多 900 字符，Reviewer 只能引用本次输入中的 `sourceId`。

结构化意见随后进入不调用 LLM 的确定性聚合器。只有 verdict 一致且存在共同来源时才形成强 agreement；无共同证据、弃权和分歧会原样保留，高风险分歧及 conflict 意见只能建议人工核查。

P4-08 对照评测后已移除 Council 的 Deep Research 生产接入：不再提供 `allowCouncil`、Council 任务快照、public trace 或前端审查流程。`council_service.py` 仅作为内部实验边界和可复现 benchmark 保留；当前唯一付费 Provider 仍为默认 DeepSeek，P4-05 第二 Provider 已因安全决策取消。

#### `tool_registry.py`

内部工具注册层为 Python 能力编排提供稳定边界。

注册表契约格式为 `schemaVersion=1.0`。每个工具声明 `name/version/description/inputSchema/outputSchema/safetyScope`；注册时校验契约定义，调用前后分别严格校验输入和输出。`list_tools()` 只返回可序列化契约，不暴露 handler。

`safetyScope` 固定描述只读访问、数据范围、模型网络访问、外部副作用和敏感输出。Agent 成功或 fallback 的 `toolCalls` 都会记录工具版本与安全范围；旧 SQLite 快照缺少这些字段时继续兼容。

#### 受限 code-native 可行性边界

`ai-service-python/code_worker/` 是 P5-04/P5-05 的内部隔离原型，不挂载 FastAPI 路由，也不注册 Agent/MCP 工具。同步入口 `run_job(job, input_path)` 只接受已经审批、输入大小与 SHA-256 匹配、脚本与固定模板完全一致的任务；内部 `start_job(job, input_path)` 返回仅供进程内使用的可取消执行句柄。宿主 `input_path` 不来自模型、CSV 或任务 wire 字段。

Worker 通过 Docker CLI 按不可变镜像 ID 运行 Python 3.13.9 固定模板：根文件系统只读，输入单文件只读挂载，输出仅写入每任务唯一临时目录，网络为 `none`，capabilities 清空，启用 `no-new-privileges` 与固定 seccomp，进程以 UID/GID `10001` 运行且环境由 `env -i` 收紧到固定 `PATH`。Docker 同时限制 CPU 速率与累计时间、墙钟、内存、swap、PID、输入、stdout/stderr 总量、tmpfs、输出字节和文件数。超限、超时或取消统一强制终止容器，并执行 `kill → rm -f → 残留核验 → 临时目录清理`；清理失败返回有界 `cleanup_failed` 摘要且污染资源不复用。结果不回传 Docker stderr、宿主路径或原始 CSV。P5-07 前仍不得新增 API、UI 或工具接入。

#### `mcp_adapter/`

只读 MCP adapter 是与 FastAPI 并列的独立本机进程入口。MCP 客户端仅在设置 `PIXIU_MCP_ENABLED=true` 后通过 `python -m mcp_adapter` 拉起 `stdio` server；默认应用启动和 Docker Compose 不会创建 MCP 监听。

Adapter 从 `tool_registry.list_tools()` 动态筛选三个无网络、无副作用的工具，并把协议调用统一送回 `ToolRegistry.invoke()`。MCP 层还拒绝当前论文 `includeAll` 全量读取并收紧检索预算。该边界不提供 HTTP/SSE、resources、prompts、文件系统、模型工具或 trace 读取。

示例工具：

- `retrieve_current_paper`
- `retrieve_library`
- `read_paper_skeleton`
- `judge_evidence`
- `generate_background_graph`
- `run_critical_analysis`
- `translate_page`

Agent 服务当前通过这一层使用检索类能力，而不是散落调用底层模块。

#### `trace_service.py`

为以下能力提供脱敏 trace summary：

- 聊天。
- 术语解释。
- 背景补课。
- 批判阅读。
- Deep Research。
- Agent Research。

trace 不保存：

- 完整 prompt。
- API key。
- 完整论文正文。
- 不安全的原始上下文转储。

#### `safety_service.py`

把论文正文、RAG 片段和页面文本视为不可信上下文，在进入模型前做包装和约束。

主要防护：

- 论文文本中的提示注入。
- 检索片段中的越权指令。
- 特权上下文的意外暴露。

## Agent 研究执行模型

当前 Agent 系统刻意保持轻量，目标是先把整体链路搭起来。

### 项目模型

每个 Agent 项目包含：

- 标题。
- 目标。
- 论文 ID 列表。
- 论文 stub。
- 最新任务指针。
- 默认约束。

### 任务模型

每个 Agent 任务包含：

- 项目关联。
- 任务状态和阶段。
- 进度。
- prompt 和约束。
- 聚焦论文。
- 计划项。
- 时间线事件。
- 工具调用。
- 证据项。
- findings。
- 对比表。
- 冲突候选。
- 开放问题。
- 报告草稿。
- trace ID。

### 输出理念

Agent 面板不再只展示最终答案快照，而是开始展示研究过程：

- 生成了什么计划。
- 收集了什么证据。
- 哪些论文证据更强或更弱。
- 哪里存在冲突或证据覆盖不均衡。
- 当前证据能支持什么草稿结论。

### Agent 推理管线（14-1 增强）

Agent 执行阶段 `synthesizing` 内部已拆分为三个独立推理节点，由 LangGraph StateGraph 串联：

```
execute → evidence_weighing → cross_paper_reasoning → synthesize → conflict_resolution
                                                                          ↓
                                                              follow_up_decision
                                                              ↙ loop / proceed ↘
```

**evidence_weighing**：对每条证据计算四维确定性可信度评分（0.0-1.0）：
- 来源类型信任度（权重 0.35）：`current_paper=1.0`, `library=0.85`, `external_academic=0.65`, `web_search=0.45`
- 页码锚定覆盖（权重 0.20）：有页码 1.0，无页码 0.65
- 跨来源一致性（权重 0.20）：基于与其他证据的关键词重叠
- JUDGE 评分（权重 0.25）：从检索 judge 归一化
- 综合评分 ≥ 0.75 为 high，≥ 0.50 为 medium，≥ 0.30 为 low，< 0.30 为 insufficient

**cross_paper_reasoning**：基于加权证据的确定性跨论文分析，产出四类洞察：
- **consensus**：两篇论文的高可信度（≥ 0.60）主张共享 ≥ 4 个关键词
- **complementary**：两篇论文话题交集小（< 3 个共享词），各自覆盖互补主题
- **contradictory**：一篇论文的低可信度（≤ 0.35）主张与另一篇高可信度主张共享 ≥ 3 个关键词
- **gaps**：论文无高可信度证据时记录 `high` 缺口；完全无证据时记录 `critical` 缺口

**conflict_resolution**：双重职责——
- 冲突自动裁决：当冲突双方的可信度差距 ≥ 0.4 且高权重方来源可信度 ≥ 0.8 时自动判定；否则标记为 `needs_manual_review`
- follow-up 循环状态管理：计算信息增益率并更新计数器

### Follow-Up 循环与信息增益自适应终止

Agent 在执行后可能进入 follow-up 循环，根据信息增益自适应决定是否继续检索：

| 终止条件 | 参数 | 效果 |
|---|---|---|
| 安全上限 | `max_follow_up = 5` | 最多 5 轮后强制停止 |
| 信息增益停滞 | < 10% 新增证据持续 2 轮 | 边际价值不足时自动停止 |
| 证据饱和 | ≥ 12 条证据 | 已收集足够证据 |
| 无缺口信号 | `open_questions` 无缺口关键词且无 high/critical gap | 缺口已覆盖 |

信息增益计算：`gain_rate = (new_count - old_count) / max(old_count, 1)`。增益 < 0.10 时递增 `low_gain_count`，≥ 0.10 时重置为 0。`low_gain_count ≥ 2` 时终止循环。该逻辑在 LangGraph 路径（`agent_langgraph.py` `conflict_resolution_node` + `follow_up_decision`）和经典 `execute_run` 路径（`agent_orchestrator.py`）中保持一致。

所有推理节点实现位于 `ai-service-python/services/agent_langgraph_reasoning.py`，可信度评分位于 `ai-service-python/services/evidence_credibility.py`。

## 持久化边界

### 浏览器

保存用户工作现场和恢复快照。

### Java H2

保存网关会话数据：

- 论文记录。
- 聊天历史。

### Python SQLite

保存 Deep Research 快照：

- 任务元数据。
- 阶段和进度。
- findings。
- 报告。
- 错误。
- 已完成任务的 trace summary。

保存 Agent 工作区快照：

- 项目元数据、论文列表、latest task 指针和默认约束。
- 任务状态、阶段、进度、计划项、工具调用、证据、findings、对比表、冲突、开放问题和报告草稿。
- 面向前端时间线的任务事件摘要。
- 非终态 Agent 任务在服务重启后恢复为失败快照，避免把已中断任务误展示为仍在运行。

### Python RAG / Chroma

保存可检索论文片段和 metadata：

- chunk 文本。
- 论文关联。
- 页码和章节 metadata。

## 设计约束

### 证据优先

大多数 AI 能力遵守同一边界：

- 优先使用当前论文证据。
- 不足时补充内部文献库。
- 主流程不做外部 Web 搜索。

### 外部学术检索信任边界

外部学术检索仍为默认关闭的未来能力，完整威胁模型见 [`docs/EXTERNAL_ACADEMIC_SEARCH_PLAN.md`](docs/EXTERNAL_ACADEMIC_SEARCH_PLAN.md)。`external_search_provider.py` 已提供 Provider 中立的单 query 协议、`DisabledExternalSearchProvider` 和严格配置工厂，并只注册 benchmark 选定的 Crossref 客户端；Semantic Scholar 仍未实现。

工厂只在 `PIXIU_EXTERNAL_SEARCH_ENABLED=1|true|yes|on` 时处理 Provider 配置；默认或其他值直接返回禁用实现，不读取 `PIXIU_EXTERNAL_SEARCH_PROVIDER`，也不构造客户端。显式选择 `crossref` 时创建固定只读客户端，选择尚未实现的 `semantic_scholar` 或提供缺失、未知、无效配置时严格报脱敏配置错误，不静默降级或切换来源。知识图谱通过该工厂取得默认 Provider，同时保留显式依赖注入边界；当前尚未把 Crossref 搜索接入任何用户任务或业务检索链路。

未来数据流固定为：

1. 检索当前论文。
2. 证据不足时检索内部文献库。
3. JUDGE 仍确认存在明确证据缺口时生成受限 query。
4. 只有任务显式授权且配置与预算完整时，调用白名单 Provider adapter。
5. adapter 校验、裁剪、脱敏并归一化响应，再把外部学术元数据作为不可信补充证据交给研究流程和人工审查。

Provider adapter 是唯一允许跨越网络信任边界的组件。当前仅 Crossref adapter 获准访问固定 `https://api.crossref.org/works` 搜索端点：使用结构化参数、连接与读取超时、明确 `User-Agent`、最多 20 条结果、1 MiB 响应上限且禁止重定向；响应只保留有界论文元数据并归一化为统一外部证据。Semantic Scholar 未实现，LLM、前端、Java 网关、内部检索层和 MCP adapter 均不得直接访问 Provider。禁止任意 URL、跨 host 重定向、通用 Web 搜索、推荐或数据集 API、PDF/全文下载、写操作和文件系统访问。

Crossref adapter 在实际 HTTP 前先查询 1 小时 TTL 的版本化 JSON 缓存，默认路径为 `ai-service-python/tmp/external_search_cache.json`。缓存 key 只保存 Provider 与规范化 query 的 SHA-256，entry 不保存原始 query、header、凭据或请求 URL；写入使用同目录临时文件和原子替换，文件缺失、过期、损坏或 schema 非法时安全视为空缓存。缓存未命中时，同一客户端实例把请求起始时间间隔限制为至少 1 秒；仅对 `429/500/502/503/504` 最多重试 2 次，采用有限指数退避并遵守不超过 30 秒的 `Retry-After`，更长等待直接停止重试。结果在写缓存前按 DOI、Provider ID 和规范化标题去重并保留首次出现项。

外部内容、链接和响应均视为不可信输入，不能覆盖内部证据或自动裁决冲突。Provider 超时、限流、响应无效、不可用或预算耗尽时，研究任务保留当前论文和内部文献库结果并记录脱敏降级原因。trace 只记录 Provider、计数、结果、延迟和脱敏 query 摘要，不记录 API key、认证 header、完整响应、全文或完整摘要。

### 安全降级

前端在旧缓存或 metadata 不完整时应安全降级：

- 缺少页码锚点时不要伪造跳转入口。
- 缺少 trace 或任务快照时展示空态，不伪造恢复成功。
- fallback evidence 应明确弱于 indexed evidence。

### Agent 成熟度

当前 Agent 架构应理解为：

- 真实端到端链路。
- 有意义的过程可视化。
- 轻量规则型综合。
- 尚未达到最终 AI 质量目标。

## 部署说明

默认仍通过 `docker-compose.yml` 编排：

- `frontend`
- `backend`
- `ai-service`
- `grobid`
- 可选 `neo4j`

关键 volume：

- `java_data`
- `chroma_data`
- `research_task_data`
- `huggingface_cache`
- `grobid_data`
- `neo4j_data`

## 测试和验证

常用命令：

前端：

```bash
npm run lint
npm test
npm run build
```

Python：

```bash
pytest tests -q
```

Java：

```bash
mvn test
```

最近 Agent 相关代码工作已完成的验证：

- `node frontend/src/services/api.test.js` 通过。
- `python -m py_compile ai-service-python/services/agent_project_service.py` 通过。
- `python -m py_compile ai-service-python/tests/test_agent_project_service.py` 通过。

已知非本次问题：

- 前端 chunk 体积较大（~2.3 MB），可考虑代码分割优化。
