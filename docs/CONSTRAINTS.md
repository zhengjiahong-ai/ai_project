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
