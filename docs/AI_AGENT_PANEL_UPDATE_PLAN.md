# AI 服务 Agent 面板更新计划书

## 1. 现状结论

当前 Python AI 服务已经具备很多“可复用能力块”，但还没有一个真正面向 Agent 面板的研究编排层。

已经存在的能力：

- 论文解析与索引：
  - `analysis_service.py`
- 聊天式 agentic RAG：
  - `chat_service.py`
- 背景补课：
  - `background_knowledge_service.py`
- 深度研究任务：
  - `research_task_service.py`
- 工具注册层：
  - `tool_registry.py`
- trace 能力：
  - `trace_service.py`
- 安全包装：
  - `safety_service.py`

缺失的能力：

- 没有“项目级多论文上下文”数据模型
- 没有“Agent 项目任务”与“单论文 research task”区分
- 没有把现有工具串成多步研究编排的稳定对外接口
- 没有面向前端时间线的结构化事件输出
- 没有项目级结论草稿和证据面板的公共响应模型

换句话说，AI 层当前已经有砖，但还没有搭成 Agent 面板要用的房子。

## 2. AI 服务应该新增什么

### 2.1 新增 Agent 项目数据模型

建议在 Python 侧建立稳定的项目模型，而不是只把多篇 `pdfId` 临时拼成一个请求参数。

建议新增：

- `schemas/agent_requests.py`
- `services/agent_project_service.py`
- `services/agent_task_service.py`

建议项目结构：

- `projectId`
- `title`
- `goal`
- `paperIds`
- `paperStates`
  - 每篇论文是否已解析、是否已索引、可用能力状态
- `defaultConstraints`
- `createdAt`
- `updatedAt`

### 2.2 新增 Agent 任务编排服务

建议新增独立服务：

- `services/agent_task_service.py`

它不应直接替代 `research_task_service.py`，而应复用已有能力作为底层工具。

建议职责：

- 接收项目级问题
- 生成研究计划
- 按项目中的多篇论文构建检索范围
- 调度已有工具：
  - `retrieve_current_paper`
  - `retrieve_library`
  - `read_paper_skeleton`
  - `run_critical_analysis`
  - `generate_background_graph`
- 产出阶段性事件
- 产出最终结构化报告
- 产出 evidence panel 可直接消费的证据链

### 2.3 新增项目级检索策略

当前能力大多默认“当前论文优先”。Agent 模式下需要升级为“项目论文优先，单篇论文有权重”。

建议新增检索策略：

- 第一层：
  - 在 `selectedPaperIds` 范围内检索
- 第二层：
  - 对当前聚焦论文优先加权
- 第三层：
  - 仅在证据不足时补内部文献库

建议输出新增字段：

- `retrievalScope`
  - `project_papers | focused_paper | library`
- `paperSourceBreakdown`
  - 每篇论文贡献了多少证据
- `coverageByPaper`
  - 每篇论文对当前子问题覆盖情况

### 2.4 新增前端友好的事件流模型

Agent 面板不是只要最终答案，它还需要“过程可见”。

建议任务输出不要只有最终 `task` 快照，还应有事件序列。建议事件类型：

- `task_created`
- `task_understood`
- `plan_generated`
- `plan_item_started`
- `tool_called`
- `tool_completed`
- `evidence_added`
- `finding_generated`
- `report_updated`
- `task_completed`
- `task_failed`

每个事件建议包含：

- `eventId`
- `type`
- `timestamp`
- `taskId`
- `stage`
- `summary`
- `meta`

这样前端中间栏就可以真实展示“时间线”，而不是把后端快照硬拆成聊天 UI。

### 2.5 新增结构化结果模型

Agent 模式最终结果建议拆成以下几块，而不是只返回大段 Markdown：

- `summary`
  - 研究结论摘要
- `comparisonTable`
  - 跨论文对比表
- `findings`
  - 子问题级结论
- `openQuestions`
  - 尚待人工确认的问题
- `conflicts`
  - 证据冲突
- `draftReport`
  - Markdown 或富文本草稿
- `evidenceItems`
  - 所有关键证据条目
- `toolCalls`
  - 面向用户摘要后的工具调用结果

### 2.6 新增 Agent trace 规范

现有 `trace_service.py` 已经很好，但 Agent 模式要补项目级元数据。

建议新增 trace 维度：

- `projectId`
- `paperIds`
- `focusedPaperIds`
- `planItemCount`
- `evidenceItemCount`
- `conflictCount`
- `reportRevisionCount`

同时保持已有安全边界：

- 不记录完整 prompt
- 不记录完整论文正文
- 不记录 API key

### 2.7 新增持久化

建议 Python SQLite 不只存 `research_tasks`，还要新增：

- `agent_projects`
- `agent_tasks`
- `agent_task_events`

其中：

- `agent_projects`
  - 存项目元数据
- `agent_tasks`
  - 存任务快照和最终报告
- `agent_task_events`
  - 存面向时间线的事件摘要

这样可以支持：

- 刷新恢复
- 最近任务恢复
- 任务过程回放
- trace 和事件分离

## 3. AI 分阶段计划

### Phase 1：基于现有工具拼出最小 Agent 编排

目标：先跑通“多论文输入 -> 计划 -> 检索 -> 证据 -> 结论”的最小闭环。

任务：

- 新增项目 schema 和 task schema。
- 新增 `agent_task_service.py`。
- 基于 `tool_registry.py` 复用已有工具。
- 支持项目论文范围检索。
- 返回最小 task 快照和结构化事件列表。

验收标准：

- 可以针对多个 `pdfId` 发起一次任务
- 返回计划、证据、结论和 traceId

### Phase 2：增强结果质量和过程表达

目标：让 Agent 模式比单篇深度研究更适合跨论文比较与综述。

任务：

- 增加对比表输出。
- 增加每篇论文的证据覆盖统计。
- 增加冲突检测和人工核查标记。
- 增加草稿报告增量更新。

验收标准：

- 前端能直接渲染对比表和证据面板
- 冲突项不会被自动合并为单一结论

### Phase 3：增强稳态能力

目标：让 Agent 任务真正成为长期研究工具，而不是 demo。

任务：

- 持久化事件流
- 支持 latest task / project history
- 支持增量追加 follow-up 任务
- 支持从已有项目上下文继续追问

验收标准：

- 用户在同一项目里可持续追问和积累结论
- 刷新或服务重启后仍能恢复核心状态

## 4. 推荐复用而非重写的能力

- 检索：优先复用 `tool_registry.py`
- 证据 judge：优先复用现有 judge 逻辑
- 冲突检测：优先复用 deep research 的冲突检测思路
- trace：优先扩展 `trace_service.py`
- 安全包装：继续统一走 `safety_service.py`

## 5. 需要避免的 AI 侧误区

- 不要为了 Agent 面板重新造一套聊天、检索、批判阅读实现。
- 不要把“能流式输出”误当成“已经有稳定编排模型”。
- 不要直接把内部 debug 信息当作前端事件流返回。
- 不要引入外部 Web 搜索，当前系统仍应遵守“项目论文优先、内部库补充、不做外网检索”的边界。
