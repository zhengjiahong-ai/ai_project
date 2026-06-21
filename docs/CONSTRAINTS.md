# Pixiu 当前接口约束

## API 边界

- 浏览器端统一访问 Java 网关 `/api`，Java 对外接口保持 `/api` 前缀。
- Python 新接口或内部转发目标统一挂在 Python `/api` 下。
- 前端新增后端调用时集中维护在 `frontend/src/services/api.js`。
- 新增或变更接口字段时，同步更新 `API.md`、本文件和相关测试。

## PDF 低文本诊断边界

- `POST /api/upload` 成功响应必须返回机器字段 `parseStatus`，兼容值为 `parsed` 和 `scanned_or_low_text`；Java 网关继续透明透传。
- 诊断同时参考 PDF 文本层和 GROBID TEI 正文的非空白字符数，阈值为 `min(max(200, pageCount * 50), 2000)`；任一来源达到阈值即视为 `parsed`。
- `scanned_or_low_text` 仅表示需要 OCR 或更换文字版 PDF，不自动执行 OCR、不上传外部服务，也不阻止 PDF 在阅读器中打开。
- 低文本状态必须优先于 `ragIndexed=false` 展示，避免把扫描件误报为普通索引异常；旧本地中文状态仍需兼容。

## 背景知识图谱来源边界

- `POST /api/background-knowledge` 只允许使用当前 `pdfId` 对应的索引片段、请求携带的 `paperSkeleton/paperStructure` 和显式 `paper_topic`，不得自动检索论文库中的其他论文。
- 背景知识图谱分为概念发现和 prerequisite 关系判断两个 LLM 阶段；第二阶段失败时可保留概念节点，但不得按列表顺序伪造前置边。
- `graph.nodes[*]` 和 `graph.edges[*]` 的 `provenanceStatus` 兼容值为 `current_paper_supported`、`model_inference`、`external_supported`；本阶段默认不会产生 `external_supported`。
- 模型推断、当前论文支持和外部证据支持的置信度上限分别为 `0.60`、`0.85`、`0.95`。模型参数知识和 `confidenceReason` 不得冒充论文证据。
- 外部学术检索 provider 默认禁用，本阶段不得由论文内容触发联网、工具调用或权限变化。

## 外部学术检索边界

- 完整威胁模型见 [`EXTERNAL_ACADEMIC_SEARCH_PLAN.md`](EXTERNAL_ACADEMIC_SEARCH_PLAN.md)。P3-01 仅固化边界，不授权生产联网。
- Provider 白名单仅包含 Crossref `https://api.crossref.org/works` 和 Semantic Scholar Academic Graph `https://api.semanticscholar.org/graph/v1/paper` 的只读论文元数据搜索与详情能力；两者只是 P3-04 benchmark 候选。
- 外部检索默认关闭。未来只有显式开关、白名单 Provider、完整配置、任务授权和预算均有效，且当前论文与内部文献库检索后仍有明确证据缺口时才允许调用。
- Provider adapter 是未来唯一允许联网的组件。请求 URL 必须由固定 HTTPS host/base path 和结构化参数构造；用户、论文、模型或外部响应不得提供目标 URL，禁止跨 host 重定向。
- 禁止通用 Web 搜索、任意 URL、推荐或数据集 API、PDF/全文下载、写操作、文件系统访问和模型直接联网；不得跟随外部 DOI、URL 或下载地址获取内容。
- 外部内容、链接和 Provider 响应均是不可信输入，必须经过长度限制、结构校验、提示注入防护、来源归一化、脱敏和人工审查。
- 证据顺序固定为“当前论文 → 内部文献库 → 明确证据缺口 → 外部学术元数据”。外部证据不得覆盖内部证据、自动裁决冲突或冒充可信事实；后续实现不得扩大白名单或绕过该顺序。
- 超时、限流、无效响应、越界重定向、Provider 不可用或预算耗尽时必须停止外部调用，保留内部证据并记录脱敏降级原因。
- API key、认证 header、完整响应、全文、完整摘要和未脱敏 query 不得进入 trace、日志、错误、缓存键或模型上下文转储。
- Provider 边界统一由 Python `external_search_provider.py` 管理。`PIXIU_EXTERNAL_SEARCH_ENABLED` 只有 `1/true/yes/on` 启用，其余值和缺省均返回只读禁用实现，且不得读取 Provider 配置或构造客户端。
- 显式启用时 `PIXIU_EXTERNAL_SEARCH_PROVIDER` 必须为 `crossref` 或 `semantic_scholar`。缺失、未知、未注册客户端、builder 失败或返回无效对象必须抛出脱敏配置错误，不得返回空结果伪装成功或切换其他来源。
- P3-03 只提供单 query 协议、禁用实现和严格工厂，不注册任何联网 builder；因此在 P3-05 实现并注册正式客户端前，显式启用合法 Provider 也必须以“客户端尚未实现”失败。
- P3-04 benchmark 结论见 [`external_search_benchmark.md`](external_search_benchmark.md)。2026-06-21 匿名采样中 Crossref 成功 6/6，Semantic Scholar 因 6 次 HTTP 429 被判定为匿名运维不可用；项目不要求配置 Semantic Scholar API key，P3-05 唯一实现目标为 Crossref。
- benchmark 只评估无需凭据的匿名可用性。至少一个候选必须成功完成 5/6 case；对全部 case 均因匿名 429 失败的候选允许标记为运维不适用并排除，但不得把其他超时、畸形响应或部分失败伪装为排除条件。
- benchmark 网络代码仅允许在 `ai-service-python/benchmarks/external_search/` 中显式 `--live` 运行，不得复用为生产客户端。默认离线评分不得联网，失败结果不得通过降低门槛、切换来源或扩大白名单绕过。

## 统一外部证据模型

- Python 内部统一外部证据必须包含 `sourceId/sourceType/provider/providerId/title/authors/year/abstract/doi/url/retrievedAt/query/license`；`sourceType` 固定为 `external_academic`。
- 缺省字符串字段为 `""`、`authors` 为 `[]`、`year` 为 `null`；不得虚构作者、年份、许可或访问时间。`provider` 必须非空，缺少 DOI、Provider ID、URL 和标题的记录必须拒绝。
- `sourceId` 身份优先级固定为 DOI、Provider ID、规范化 URL、Provider/标题/年份指纹；身份键使用 SHA-256 生成 `external-{kind}-{24 位摘要}`，传入的任意 `sourceId` 不得覆盖该规则。
- DOI 统一移除 `doi:` 和 `doi.org` URL 前缀并转为小写，因此相同 DOI 跨 Provider 生成相同 ID；Provider ID 必须与规范化 Provider 名称组合，避免跨 Provider 碰撞。
- URL 身份只接受 HTTP(S)，移除 fragment、统一 scheme/host 大小写并排序 query 参数。统一模型只保存 URL 元数据，不授权服务端访问或跟随该 URL。
- 现有 evidence 归一化和 compact response 必须保留上述外部字段；当前论文、内部文献库和旧来源的字段与兼容行为保持不变。

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

## GraphRAG 冲突辅助字段

- Deep Research 与 Agent 的真实 `conflicts[*]` 可兼容新增 `graphContext`；`no-major-conflict` 等无冲突占位项不得触发图谱查询。
- `graphContext` 包含 `status/paperIds/seedTerms/nodes/edges/sourceIds/provenanceSummary/contextNote`；`status` 兼容值为 `available`、`partial`、`unavailable`。
- 邻域只读取用户此前通过背景补课生成并保存的图谱快照，限制为一跳、最多 8 个节点和 12 条边；不得因冲突自动调用 LLM、联网或生成新图。
- 图谱节点和边的 `confidence/provenanceStatus` 仅用于解释来源覆盖，不代表论文权威度或结论真伪概率。
- GraphRAG 上下文不得修改已有冲突类型、严重度或人工核查标记，也不得自动融合矛盾结论或裁决哪一方正确。
- 背景图谱默认保存到 `ai-service-python/data/knowledge_graph.sqlite3`，可通过 `KNOWLEDGE_GRAPH_DB_PATH` 覆盖；SQLite 或可选 Neo4j 不可用时不得阻断研究任务。
- `POST /api/background-knowledge` 可兼容新增 `sqlite.enabled/status/message` 存储状态；旧客户端可忽略，`status=error` 不代表图谱生成失败。

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

## 人机审查边界

- 新建 Deep Research 和 Agent 任务必须经过 `awaiting_plan_review` 与 `awaiting_final_review`，不得由前端绕过 gate 直接标记完成。
- Plan review 必须提交完整替换计划；Agent 的 `focusedPaperIds` 只能来自所属项目，批准后的计划和约束必须真实进入检索与综合输入。
- `reviewRisks[*].riskId` 必须稳定关联已有冲突、finding 缺口或开放问题；`reviewStatus` 仅允许 `reviewed`、`needs_follow_up`。
- 等待审查状态必须跨 SQLite 重启恢复；运行中的任务仍按既有中断失败语义处理。
- 四个新增接口均保持 `/api` 前缀，前端调用集中在 `frontend/src/services/api.js`，Java 只做透明转发。

## 内部工具契约边界

- Python `tool_registry` 的注册表契约版本固定为 `schemaVersion=1.0`，每个工具必须声明 SemVer `version`、输入/输出 schema 和完整 `safetyScope`。
- 输入 schema 默认禁止未知字段；handler 执行前校验输入、返回后校验输出，失败统一抛出包含工具名、方向和字段路径的 `ToolValidationError`。
- `safetyScope` 必须包含 `access/dataScopes/networkAccess/sideEffects/sensitiveOutput`；当前注册工具只允许 `access=read_only` 且 `sideEffects=false`。
- Agent `toolCalls.version/safetyScope` 是向后兼容的可选字段，旧 SQLite 快照不得因缺少它们而读取失败。
- 只读 MCP adapter 默认关闭，仅允许在本机以 `PIXIU_MCP_ENABLED=true python -m mcp_adapter` 启动 `stdio` server；不得挂载到 FastAPI、Java `/api` 或公网端口。
- MCP `tools/list` 只能从注册表动态筛选 `read_paper_skeleton`、`retrieve_current_paper`、`retrieve_library`，并复用原始输入/输出 schema；调用必须经过 `ToolRegistry.invoke()`。
- MCP 当前论文检索禁止 `includeAll=true`，并对 `topK/limit/maxTextChars` 使用独立的更小运行时预算；不得暴露文件系统、API key、完整论文正文、完整 prompt、原始 trace、模型网络工具或写操作。
