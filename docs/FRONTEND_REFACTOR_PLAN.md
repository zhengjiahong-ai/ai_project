# 前端重构计划

## 2026-06-12 P1-6 Deep Research JUDGE 评分展示

- Deep Research findings 兼容展示后端新增的 `judgeScore`、`coverage` 和 `retryReason`。
- `deepResearchPanelModel.js` 负责归一化证据效用分、覆盖率、证据数量、来源类型和 retry 原因，旧任务快照缺少字段时稳定降级。
- `DeepResearchPanel` 在 finding 卡片要点和详情中展示 `JUDGE N/100`、覆盖百分比、证据条数与 retry 原因，便于用户判断长路径研究是否发生证据漂移。

## 2026-06-12 P1-5 批判阅读引用网络真实化

- 批判阅读面板不得展示固定模拟 citation network，避免用户把 demo 关系误认为真实引用网络。
- `CriticalAnalysisPanel` 仅在批判阅读响应包含有效 `citationGraph.nodes` 和 `citationGraph.links` 时渲染 `ForceGraph`。
- 没有真实 `citationGraph` 时展示“暂无引用网络”空态，并说明当前不会用模拟引用关系兜底。
- citation graph 数据归一化集中在 `criticalAnalysisData.js`，面板组件只消费归一化后的有效图或 `null`。
