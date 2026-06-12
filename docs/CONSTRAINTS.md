# Pixiu 当前接口约束

## API 边界

- 浏览器端统一访问 Java 网关 `/api`，Java 对外接口保持 `/api` 前缀。
- Python 新接口或内部转发目标统一挂在 Python `/api` 下。
- 前端新增后端调用时集中维护在 `frontend/src/services/api.js`。
- 新增或变更接口字段时，同步更新 `API.md`、本文件和相关测试。

## 批判阅读数值证据字段

- `POST /api/critical-reading/{pdfId}` 由 Java 转发到 Python `POST /api/deep-analysis`，Java 继续透传 Python 响应并包装到 `analysis`。
- `analysis.claims[*].numericVerificationStatus` 兼容取值：
  - `not_applicable`
  - `candidate_found`
  - `insufficient_for_auto_verification`
  - `not_found`
- `analysis.claims[*].numericEvidenceCandidates` 是候选定位结果，不代表自动表格 OCR 或严格数值核验。
- 每个 candidate 的 `sourceId` 必须来自同次 `analysis.rag_sources[*].sourceId`，不得生成前端无法追溯的伪来源。
- candidate 可携带 `text/pageIndex/sectionId/chunkIndex/label/metrics/numbers/reason/status`；`pageIndex` 仍为 0-based。
- `analysis.numericEvidenceSummary` 只汇总本次 claims 的数值候选覆盖情况，不参与贡献可信度评分。

## 批判阅读引用网络字段

- `analysis.citationGraph` 是可选真实引用网络字段；没有真实 citation graph 时必须返回 `null`。
- 前端不得用固定 demo network、模拟节点或模拟边兜底展示“论文领域学术地位”。
- 存在真实图时，`citationGraph.nodes` 中每个节点至少需要稳定 `id`，展示名可用 `name`、`label` 或 `id`。
- 存在真实图时，`citationGraph.links` 中每条边至少需要 `source` 和 `target`。
- `citationGraph` 不改变 Java `/api/critical-reading/{pdfId}` 的请求方式；Java 继续透传 Python 响应到 `analysis`。

## 深度研究 JUDGE 效用评分字段

- `POST /api/research-tasks`、`GET /api/research-tasks/{taskId}` 和 `GET /api/research-tasks/latest` 的外层响应不变，`task.findings[*]` 兼容新增 `judgeScore/coverage/retryReason`。
- `judgeScore` 是 `0-100` 的规则型证据效用分，来自 `verdict`、`confidence`、证据覆盖率、证据数量和来源类型，不代表模型置信概率。
- `coverage.score` 是 `0-1`，前端展示时可转成百分比；`matchedAspects/totalAspects/evidenceCount/sourceTypes` 仅用于解释覆盖情况。
- `retryReason` 仅在该 finding 触发自动 retry 时记录原因；未触发 retry 时为空字符串。
- `GET /api/traces/{traceId}` 的 deep research judge step 可在 `steps[*].meta` 中包含 `decision`，取值为 `stop`、`try_library` 或 `retry`，用于解释为什么停止、补查文献库或重试。
- 旧客户端可忽略这些新增字段；Java 网关继续透传 Python 响应。
