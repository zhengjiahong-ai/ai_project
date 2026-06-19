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

## 深度研究跨源冲突字段

- `POST /api/research-tasks`、`GET /api/research-tasks/{taskId}` 和 `GET /api/research-tasks/latest` 的 `task` 兼容新增 `conflicts` 数组。
- `task.conflicts[*]` 可包含 `id/topic/claim/conflictType/severity/summary/sourceIds/sources`。
- `conflictType` 当前只承诺规则型 MVP 值：`numeric_mismatch` 和 `opposing_conclusion`。
- `sources` 复用 evidence item 契约，保留 `sourceId/sourceType/text/pageIndex/sectionId/chunkIndex/pdfId` 等可用来源锚点。
- 冲突检测只标记“需人工核查”，不得自动融合矛盾结论或裁决哪一方正确。
- Java 网关继续透传 Python 响应；旧客户端可忽略 `conflicts`。

## Deep Research trace summary 持久化边界

- `GET /api/traces/{traceId}` 的响应结构保持 `{ "status": "success", "trace": {} }`，Java 网关继续只读透传 Python `/api/traces/{traceId}`。
- Deep Research 终态任务会把脱敏后的 public trace summary 写入 `task.traceSummary` 并随 SQLite 快照保存；服务重启后可按 `traceId` 恢复已完成任务的关键执行轨迹。
- `task.traceSummary` 只保存 public summary 字段，不保存完整 prompt、论文全文、headers、API key 或未裁剪 step 列表。
- 普通聊天、批判阅读、背景补课等短请求 trace 仍为进程内临时摘要；服务重启或内存清空后返回 `404` 是允许行为。
- 旧任务快照没有 `traceSummary` 时按空对象兼容，前端和旧客户端可忽略该字段。

## Agent 项目删除与编号边界

- `DELETE /api/agent-projects/{projectId}` 由 Java `/api` 透传到 Python `/api`，成功响应保持 `{ "status": "success", "projectId": "..." }`。
- 删除 Agent 项目会同步删除该项目关联的 Agent SQLite 任务快照和事件摘要；项目不存在时返回兼容式 `404` 错误体。
- 前端新增 Agent 调用继续集中维护在 `frontend/src/services/api.js`。
- 前端默认项目标题编号由本地 `nextProjectNumber` 单调递增控制；删除项目不得重命名已有项目，也不得回退后续默认编号。

## Agent SQLite 持久化边界

- Agent 项目、任务和事件摘要保存到 Python SQLite，默认位置为 `ai-service-python/data/agent_state.sqlite3`，测试或隔离运行可通过 `AGENT_STATE_DB_PATH` 覆盖。
- `/api/agent-projects*` 和 `/api/agent-tasks*` 的请求/响应字段保持不变；持久化只改变服务重启后的恢复能力。
- 服务重启前已经进入 `succeeded`、`failed` 或 `cancelled` 的任务按快照恢复。
- 服务重启前仍处于 `running` 或 `pending` 的任务恢复为 `failed`、`stage=done`、`progress=1.0`，`error` 固定为 `Agent task was interrupted by service restart.`，并追加 `task_expired` 事件。
- 项目级任务历史列表接口已补齐：`GET /api/agent-projects/{projectId}/tasks` 由 Java `/api` 透传到 Python `/api`。
- 任务历史成功响应保持 `{ "status": "success", "projectId": "...", "tasks": [], "limit": 20 }`，`tasks` 复用完整 Agent task 快照并按 `updatedAt` 倒序返回。
- `limit` 默认 `20`，Python 侧约束到 `1..100`；项目存在但没有任务时返回空数组，项目不存在时返回 `404 Agent project not found.`。
- 前端进入、切换或刷新 Agent 项目时优先读取服务端任务历史；本地 `tasksByProjectId` 只作为旧接口、离线或临时失败 fallback。

## 内部工具契约边界

- Python `tool_registry` 的注册表契约版本固定为 `schemaVersion=1.0`，每个工具必须声明 SemVer `version`、输入/输出 schema 和完整 `safetyScope`。
- 输入 schema 默认禁止未知字段；handler 执行前校验输入、返回后校验输出，失败统一抛出包含工具名、方向和字段路径的 `ToolValidationError`。
- `safetyScope` 必须包含 `access/dataScopes/networkAccess/sideEffects/sensitiveOutput`；当前注册工具只允许 `access=read_only` 且 `sideEffects=false`。
- Agent `toolCalls.version/safetyScope` 是向后兼容的可选字段，旧 SQLite 快照不得因缺少它们而读取失败。
- 当前未暴露 MCP server/client、文件系统、API key、完整论文正文或原始 trace；后续 adapter 必须复用同一工具契约并默认关闭。
