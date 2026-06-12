# 前端重构计划

## 2026-06-12 P1-5 批判阅读引用网络真实化

- 批判阅读面板不得展示固定模拟 citation network，避免用户把 demo 关系误认为真实引用网络。
- `CriticalAnalysisPanel` 仅在批判阅读响应包含有效 `citationGraph.nodes` 和 `citationGraph.links` 时渲染 `ForceGraph`。
- 没有真实 `citationGraph` 时展示“暂无引用网络”空态，并说明当前不会用模拟引用关系兜底。
- citation graph 数据归一化集中在 `criticalAnalysisData.js`，面板组件只消费归一化后的有效图或 `null`。
