# 前端重构计划

## 2026-06-20 P2-6 OCR/扫描 PDF 检测与提示

- 上传响应的 `parseStatus` 与 `parseMessage` 随论文库条目和解构快照保存，旧 IndexedDB 记录无需迁移。
- `parseStatusModel.js` 统一机器状态、旧中文状态、展示标签和低文本警告；“需 OCR”优先于普通索引异常。
- 论文库新增“需 OCR”筛选、状态徽标和处理说明；篇章解构在所有阅读模式持续展示警告，不把空骨架标记为“已解构”。
- 本阶段只做本地检测与提示，不接 OCR 引擎或外部 OCR 服务。

## 2026-06-18 P1-15 翻译、篇章解构与 Agent 产物沉淀

- 全景翻译当前页和篇章解构的单章节摘要新增“加入工作台”，分别保留 `pdfId/pageIndex` 与 `pdfId/sectionId`。
- Agent 报告草稿、跨论文对比表和单条关键证据新增统一保存入口；报告与对比表归入当前论文工作台，证据卡额外保留来源 `pdfId/sourceId/pageIndex/sectionId`。
- artifact 模型新增 `taskId/projectId` 等可回溯字段并兼容旧卡片；Agent 模式没有当前论文或产物尚未生成时明确禁用保存。
- 本阶段不新增项目级工作台、不把 Agent 产物复制到项目全部论文，也不合并 P1-16 的统一来源跳转工作。

## 2026-06-17 P1-14 阅读 IDE 到 Agent 下一步建议

- `App.jsx` 的推荐下一步从单个 primary/secondary 建议升级为 2-3 个动作，覆盖继续单论文阅读、发起 Deep Research 和进入 Agent 研究。
- 新增 `readingWorkflowModel.js` 统一生成建议，输入当前 PDF、活动面板、解析状态、Deep Research 状态、工作台沉淀数量和 `pdfId`，并用模型测试覆盖关键状态。
- Agent 建议点击后只切换到 Agent 研究模式，不自动创建项目或任务；当前论文继续通过 `activePaperId` 进入 Agent 新项目草稿，沿用论文库存在性校验。

## 2026-06-14 P2-1 Agent 研究模式前端框架

- `Navbar` 新增 `阅读 IDE / Agent 研究` 双模式切换，默认仍进入原有阅读 IDE，避免影响现有单论文阅读工作流。
- `App.jsx` 新增轻量 `appMode` 状态，`reader` 模式渲染原有 PDF 阅读工作台，`agent` 模式渲染新增 `AgentWorkspace`。
- 新增 `frontend/src/components/agent/AgentWorkspace.jsx`，先实现三栏前端框架：左侧研究工作区、中间 Codex 风格 Agent 对话任务区、右侧工具调用与证据链。
- 新增 `frontend/src/components/agent/agentMockData.js`，当前仅使用 mock 数据展示多论文、执行计划、工具调用、阶段性结果和证据片段。
- 本阶段不引入复杂智能体概念，不接真实后端 Agent；目标是先固定产品形态，后续再逐步接入论文库多选、跨论文 RAG、深度研究和工具 trace。

## 2026-06-13 P1-10 Deep Research trace 预算指标展示

- Deep Research trace summary 兼容后端稳定 counters 字段，旧 trace 缺少预算字段时统一降级为 0。
- `deepResearchPanelModel.js` 归一化 `llmCalls/retrievalCalls/retryCount/truncationCount/estimatedInputTokens/estimatedOutputTokens`，同时保留原始 counters 供展开详情调试。
- `DeepResearchPanel` 将 trace “计数器”改为固定预算指标卡，直接展示 LLM 调用、检索调用、retry、截断和估算输入/输出 token。

## 2026-06-13 P1-8 Deep Research 跨源冲突核查展示

- Deep Research 任务快照兼容后端新增的 `conflicts` 字段，旧快照没有冲突列表时稳定降级为空态。
- `deepResearchPanelModel.js` 归一化冲突类型、严重度、摘要、来源 ID 和 evidence source 跳转元数据。
- `DeepResearchPanel` 在 Findings 与研究报告之间新增“证据冲突/需人工核查”区，展示数值不一致或正反结论冲突，并复用来源跳回原文入口。

## 2026-06-13 P1-7 Deep Research 动态 follow-up 计划展示

- Deep Research 任务计划兼容后端新增的对象型 `plan` 项，并继续支持旧字符串计划快照。
- `deepResearchPanelModel.js` 新增 `planItems` 归一化，保留 `question/kind/status/sourceQuestion/sourceMissingAspects`，用于区分初始子问题和证据缺口驱动的 follow-up。
- `DeepResearchPanel` 的研究计划区展示 follow-up 来源、缺失点和执行状态，帮助用户理解为什么系统追加了新的探索节点。

## 2026-06-12 P1-6 Deep Research JUDGE 评分展示

- Deep Research findings 兼容展示后端新增的 `judgeScore`、`coverage` 和 `retryReason`。
- `deepResearchPanelModel.js` 负责归一化证据效用分、覆盖率、证据数量、来源类型和 retry 原因，旧任务快照缺少字段时稳定降级。
- `DeepResearchPanel` 在 finding 卡片要点和详情中展示 `JUDGE N/100`、覆盖百分比、证据条数与 retry 原因，便于用户判断长路径研究是否发生证据漂移。

## 2026-06-12 P1-5 批判阅读引用网络真实化

- 批判阅读面板不得展示固定模拟 citation network，避免用户把 demo 关系误认为真实引用网络。
- `CriticalAnalysisPanel` 仅在批判阅读响应包含有效 `citationGraph.nodes` 和 `citationGraph.links` 时渲染 `ForceGraph`。
- 没有真实 `citationGraph` 时展示“暂无引用网络”空态，并说明当前不会用模拟引用关系兜底。
- citation graph 数据归一化集中在 `criticalAnalysisData.js`，面板组件只消费归一化后的有效图或 `null`。
