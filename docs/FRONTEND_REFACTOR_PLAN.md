# 前端重构计划

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
