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

`tasksByProjectId` 是当前新增的关键状态。它支持：

- 每个项目保存多个任务。
- 切换项目时恢复对应任务。
- 在旧任务和新任务之间切换。
- 服务端任务历史接口不可用时通过快照恢复。

正常路径下，Agent 工作区进入或切换项目会优先调用 `GET /api/agent-projects/{projectId}/tasks` 从 Python SQLite 快照恢复服务端任务历史；`tasksByProjectId` 只保留为旧接口、离线或临时失败时的 fallback。

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
- `/api/agent-tasks/{taskId}`
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

#### `agent_project_service.py`

这是当前 Agent 研究项目和任务生命周期的后端核心。

它负责：

- 创建、列出、读取、更新项目。
- 添加或移除项目论文。
- 创建异步 Agent 任务。
- 查询 Agent 任务。
- 取消 Agent 任务。

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

当前 AI 结论行为：

- 报告草稿不再是通用空占位。
- 服务会根据论文证据密度、支持画像和共同主题生成规则型结论。
- 报告里显式包含冲突候选和开放问题。

当前重要限制：

- Agent 项目、任务和事件摘要已保存到 Python SQLite 快照。
- 后端已经提供项目级任务历史接口，按 `updatedAt` 倒序返回完整任务快照。
- Python 服务重启后会恢复终态 Agent 任务；重启前仍在运行的任务会标记为 `failed` 并记录 `task_expired` 事件。

#### `tool_registry.py`

内部工具注册层为 Python 能力编排提供稳定边界。

注册表契约格式为 `schemaVersion=1.0`。每个工具声明 `name/version/description/inputSchema/outputSchema/safetyScope`；注册时校验契约定义，调用前后分别严格校验输入和输出。`list_tools()` 只返回可序列化契约，不暴露 handler。

`safetyScope` 固定描述只读访问、数据范围、模型网络访问、外部副作用和敏感输出。Agent 成功或 fallback 的 `toolCalls` 都会记录工具版本与安全范围；旧 SQLite 快照缺少这些字段时继续兼容。

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

- 前端生产构建仍会因为缺少 `rehype-katex` 失败。
