# 前端 Agent 面板更新计划书

## 1. 现状结论

基于当前 `ARCHITECTURE.md`、`README.md` 和前端源码，Agent 面板已经从早期交互原型升级为可恢复的项目工作区。当前核心特征如下：

- 入口已经存在：`frontend/src/App.jsx` 通过 `appMode` 在 `reader / agent` 两种模式间切换。
- 导航已经存在：`frontend/src/components/Navbar.jsx` 提供 `阅读 IDE / Agent 研究` 模式切换。
- 三栏界面已经拆分为多个 Agent 子组件。
- 数据已接入真实 Agent API，不再依赖 `agentMockData.js` 驱动主流程。
- 前端已有项目、任务、任务历史、轮询、取消和 trace 查询状态模型。
- 项目级任务历史优先由服务端 `GET /api/agent-projects/{projectId}/tasks` 恢复，本地 `tasksByProjectId` 作为 fallback。

这意味着前端最关键的工作，不是“继续美化原型”，而是把这个原型升级为一个真实的研究工作台，并且复用现有阅读侧能力，而不是再造一套平行系统。

## 2. 前端应该新增什么

### 2.1 状态层

需要新增一套面向 Agent 研究模式的前端状态模型，至少包括：

- `agentProject`
  - 当前研究项目 ID、标题、目标、创建时间、更新时间。
- `selectedPaperIds`
  - 当前研究项目中选中的多篇论文 ID。
- `activeTask`
  - 当前 Agent 任务 ID、状态、阶段、最近事件、最近输出。
- `planItems`
  - 执行计划项，包含状态、依赖关系、来源问题、是否 follow-up。
- `toolCalls`
  - 工具调用列表，包含开始时间、结束时间、输入摘要、输出摘要、错误、traceId。
- `evidenceItems`
  - 证据列表，必须复用现有 evidence item 结构，确保可跳转原文。
- `draftReport`
  - 当前研究结论草稿、对比表、研究摘要、待确认项。

建议新增：

- `frontend/src/hooks/useAgentProjectSession.js`
- `frontend/src/hooks/useAgentTaskStream.js`
- `frontend/src/components/agent/agentWorkspaceModel.js`

其中 `useAgentProjectSession` 负责项目级数据，`useAgentTaskStream` 负责任务轮询或事件流，`agentWorkspaceModel.js` 负责把 API 返回归一化成 UI 消费模型。

### 2.2 服务层

需要在 `frontend/src/services/api.js` 中新增 Agent 研究模式相关调用，而不是把逻辑散落到组件中。建议新增：

- `listAgentProjects()`
- `createAgentProject()`
- `getAgentProject(projectId)`
- `updateAgentProject(projectId, payload)`
- `addProjectPapers(projectId, paperIds)`
- `removeProjectPaper(projectId, paperId)`
- `createAgentTask(projectId, payload)`
- `getAgentTask(taskId)`
- `listAgentProjectTasks(projectId, limit)`
- `cancelAgentTask(taskId)`
- `getLatestAgentTask(projectId)`
- `getAgentTrace(traceId)`

如果后端最终支持事件流，还需要预留：

- `streamAgentTask(taskId)`

### 2.3 组件层

当前 `AgentWorkspace.jsx` 需要从单文件原型拆分为真实模块。建议拆成：

- `AgentWorkspace.jsx`
  - 页面级容器，负责布局和数据装配。
- `AgentProjectSidebar.jsx`
  - 研究项目、项目元信息、多论文列表、索引状态、快捷入口。
- `AgentTaskTimeline.jsx`
  - 中间主区域，展示消息流、计划变化、阶段结果、最终草稿。
- `AgentComposer.jsx`
  - 底部输入框、快捷任务、约束输入、任务发起。
- `AgentEvidencePanel.jsx`
  - 工具调用、证据卡片、来源跳转、trace 入口。
- `AgentPlanPanel.jsx`
  - 计划项、follow-up、依赖状态。
- `AgentReportPanel.jsx`
  - 结论草稿、差异对比表、导出入口。

### 2.4 与现有阅读工作流的打通点

前端不应把 Agent 模式做成“孤岛”。至少要打通以下能力：

- 复用论文库：
  - 从 `LibrarySidebar` 所在数据源中选择多篇论文加入研究项目。
- 复用当前论文上下文：
  - 在阅读 IDE 中可将当前论文“一键加入 Agent 项目”。
- 复用 evidence 跳转：
  - Agent 证据卡片必须复用现有 `onJumpToSource` 能力。
- 复用现有分析结果：
  - 批判阅读、背景补课、深度研究结果应能作为 Agent 工具产物展示。
- 复用底部工作台：
  - Agent 阶段结论、证据摘录、对比表、研究摘要应能保存到 `BottomWorkbench`。

### 2.5 持久化

当前 Agent 面板还没有本地持久化。建议：

- IndexedDB 增加 `agentProjectStore`
- IndexedDB 增加 `agentTaskStore`
- IndexedDB 增加 `agentDraftStore`
- IndexedDB 增加 `agentSelectionStore`

持久化原则：

- 本地存“用户工作现场”
- 服务端存“项目元数据与任务快照”
- 证据正文仍以服务端快照为准，避免前端伪造状态

## 3. 前端分阶段计划

### Phase 1：把原型接上真实数据

目标：保留现有三栏视觉结构，先替换掉全部 mock 数据。

任务：

- 抽离 `AgentWorkspace.jsx` 的 mock 数据依赖。
- 增加 Agent 项目与任务的前端状态模型。
- 接入项目详情、论文列表、任务详情、trace 摘要查询。
- 支持从论文库把论文加入 Agent 项目。
- 支持最小任务发起、轮询刷新、取消任务、失败提示。

验收标准：

- 页面不再依赖 `agentMockData.js`
- 刷新后能恢复当前项目和最近任务
- 证据卡片可跳回原文

### Phase 2：把 Agent 变成“研究工作台”

目标：让 Agent 模式真正能承载跨论文研究，而不只是“会显示一段回答”。

任务：

- 新增项目管理和多论文选择。
- 支持计划项、工具调用、证据链和结论草稿分区展示。
- 支持将现有能力以工具结果方式嵌入时间线。
- 支持保存草稿到工作台、导出 Markdown / JSON。

验收标准：

- 用户可围绕一个研究问题多次迭代任务
- 同一项目内保留多轮研究历史
- 结论区可复用证据并导出

### Phase 3：增强可观测性和协作感

目标：让用户理解 Agent “为什么这么做”，而不是只看到最终答案。

任务：

- 展示阶段性 reasoning 摘要，但不泄露完整 prompt。
- 展示计划变更、follow-up 来源和证据不足原因。
- 展示工具级 trace、耗时、调用次数、失败原因。
- 增加“需要人工确认”的显式标记。

验收标准：

- 用户可以区分已确认结论、草稿结论和待核查项
- 工具失败、证据冲突、计划追加都可见

## 4. 需要避免的前端误区

- 不要把现有阅读 IDE 能力复制一份到 Agent 模式，应该复用。
- 不要把 trace 原样暴露成调试日志，应该做面向用户的摘要模型。
- 不要让 Agent 页面自己维护一套论文元数据真相，论文索引状态应以服务端为准。
- 不要先做复杂动画和“智能感”，优先做状态可恢复、证据可跳转、任务可理解。

## 5. 推荐交付顺序

1. 先补前端状态模型和 API service。
2. 再补项目侧边栏和真实任务时间线。
3. 再补证据面板、导出和工作台沉淀。
4. 最后再做流式体验、阶段动画和高级交互。
