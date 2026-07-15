# Pixiu 当前接口约束

## API 边界

- 浏览器端统一访问 Java 网关 `/api`，Java 对外接口保持 `/api` 前缀。
- Python 新接口或内部转发目标统一挂在 Python `/api` 下。
- 前端新增后端调用时集中维护在 `frontend/src/services/api.js`。
- 新增或变更接口字段时，同步更新 `API.md`、本文件和相关测试。

## LLM Provider 与 Council benchmark 边界

- Python LLM Provider 统一通过 `LLMRequest -> LLMResult` 调用；结果必须包含 `provider/model/content/usage`，usage 统一为输入、输出、总 token 和是否估算。DeepSeek 与离线 fixture 必须实现同一协议。
- 现有 `_call(...) -> str` 是兼容层，必须委托统一协议并只返回 `content`；默认 DeepSeek 模型、翻译模型、温度、thinking/reasoning 配置和 fixture 默认/翻译分流保持兼容。未知 `PIXIU_LLM_MODE` 必须严格失败。
- Provider HTTP 错误、网络错误和畸形响应统一为脱敏异常，不得包含响应体、认证 header、密钥或完整 prompt。DeepSeek 缺少原生 usage 时允许使用现有 token 估算，但必须标记 `estimated=true`。
- Council 基线只允许在 `ai-service-python/benchmarks/council/` 中通过显式 `--live` 调用当前配置的 LLM。默认命令只能读取已提交的脱敏 snapshot 并离线复算，不得联网。
- Council snapshot 禁止保存 prompt、messages、隐藏推理、headers、Authorization 或 API key。没有真实 Provider 采样时不得手工伪造 snapshot、指标或把 P4-01 标记完成。
- Council Reviewer 不注册独立 `/api`。evidence reviewer 与 contradiction reviewer 必须使用同一 Provider 的两个独立请求，任一请求不得读取或包含另一意见。
- Council 输入最多保留 8 条证据、单条最多 900 字符；Reviewer 输出只能引用本次允许的 `sourceId`。空证据、Provider/解析失败、非法 verdict、未知来源或证据不足必须归一为脱敏 abstention，并保留其他有效意见。
- 强共识必须同时满足两份非弃权意见 verdict 一致且共享至少一个来源。无共同证据不得生成 agreement；冲突和高风险分歧必须绑定双方立场、理由与来源，并返回 `manual_review_required`，聚合器不得多数投票或自动裁决。
- P4-08 对照评测未通过成本门槛后，Council 不得接入 Deep Research 或其他生产路径；不得暴露 `allowCouncil`、`task.council`、`councilReviews` 或 Council public trace 字段。内部 `council_service.py` 与脱敏 benchmark 仅用于离线复算和后续研究。
- Council 对照 benchmark 必须复用固定五类 fixture；四项基线质量不得回退，冲突人工复核率和证据不足升级率必须为 `1.0`，Reviewer 失败率必须为 `0`，平均延迟和 token 倍数均不得超过 `2.5x`。
- P4-05 第二付费 Provider 已因安全决策取消。未来恢复任何第二 Provider 必须另立任务，明确凭据来源、预算与授权，不得复用未知密钥。

## PDF 低文本诊断边界

- `POST /api/upload` 成功响应必须返回机器字段 `parseStatus`，兼容值为 `parsed` 和 `scanned_or_low_text`；Java 网关继续透明透传。
- 诊断同时参考 PDF 文本层和 GROBID TEI 正文的非空白字符数，阈值为 `min(max(200, pageCount * 50), 2000)`；任一来源达到阈值即视为 `parsed`。
- `scanned_or_low_text` 仅表示需要 OCR 或更换文字版 PDF，不自动执行 OCR、不上传外部服务，也不阻止 PDF 在阅读器中打开。
- 低文本状态必须优先于 `ragIndexed=false` 展示，避免把扫描件误报为普通索引异常；旧本地中文状态仍需兼容。

## 受限代码执行安全边界

- P5-02 沙箱 benchmark 最终决策为 `continue_to_p5_03`：加固 Docker Linux 容器全部强制探针通过；Windows Job Object 未满足无网络、宿主文件隔离和只读输入，因此淘汰。
- benchmark 固定配额为 5 秒墙钟、1 CPU、128 MiB 内存、32 PID、1 MiB stdout、16 MiB tmpfs 和 1 MiB 输入，仅用于复现实验，不授权生产执行。
- P5-07 只开放固定 CSV 描述统计的 artifact 暂存、任务查看、执行审批和发布审批 API/UI；不得注册 Agent/MCP 工具、`run_python`、`run_shell` 或通用代码能力。
- Worker 只运行固定 Python 3.13.9 标准库模板；任务必须已审批，脚本、镜像、输入大小与 SHA-256 必须完全匹配，否则在启动 Docker 前封闭失败。
- 容器必须使用不可变镜像 ID、无网络、非 root、只读根文件系统、只读单文件输入、每任务临时输出目录、清空 capabilities、`no-new-privileges`、固定 seccomp 和最小环境。
- 唯一候选场景是对用户明确确认的一份带唯一表头 UTF-8 CSV，使用不可修改的 Python 3 固定模板和 `csv/statistics/math/json` 生成有界描述统计 JSON。
- 禁止任意代码或表达式、Shell、子进程、动态 import、pandas/numpy、包安装、网络/DNS、宿主文件系统、环境变量、凭据、后台任务和长期进程。
- 输入只能通过已批准 artifact ID 解析为隔离层提供的只读普通文件；不得接受路径、URL、XLSX、压缩包、多文件、符号链接或特殊文件。现有前端研究卡片不自动成为可执行输入。
- CSV 单元格是完全不可信数据，不得解释为提示、公式、路径、URL、代码或配置；输出不得包含原始行、脚本、HTML、图表或任意文件。
- CPU、内存、墙钟、输入、输出和进程参数沿用 P5-02 实测值；CPU 同时设置 Docker rate limit 与 5 秒 hard limit，stdout/stderr 共享 1 MiB 预算，输出只允许一个不超过 1 MiB 的普通 JSON 文件。
- 超限、超时或取消必须强制终止并删除容器、核验无残留、清理每任务唯一临时目录；清理失败返回脱敏 `cleanup_failed` 摘要，污染容器或目录不得复用。
- P5-06 审计库由宿主进程独占写入，默认位于 `ai-service-python/data/code_execution.sqlite3`，可通过 `CODE_EXECUTION_DB_PATH` 覆盖；Worker 容器不得获得数据库挂载、路径或写接口。
- 任务快照、脚本文本和追加式审计事件必须在同一 SQLite 事务内保存。事件以 canonical JSON、序号和前序 digest 构成 SHA-256 哈希链；读取和更新前必须完整验证，篡改、删除、重排、摘要不匹配或半份记录均封闭失败。
- 审计只记录审批人/时间、任务与脚本 digest、运行时/镜像、输入输出 digest、资源限制、退出状态和清理摘要；不得保存 CSV 内容、脚本文本、宿主路径、凭据或 stdout/stderr 内容。该哈希链提供可检测篡改能力，不宣称第三方数字签名意义的法律不可抵赖性。
- 执行审批绑定当前 `taskDigest`；发布审批绑定由任务、终态产物、警告和审计链头计算的 `publicationDigest`。摘要不匹配返回冲突，失败执行不得批准发布。
- 未通过发布审批的产物保持 `publishable=false`，不得进入 Deep Research、Agent evidence 或普通工作台；P5-07 仅建立门禁。
- 不得注册 `run_shell`、`run_python` 或通用代码执行工具；未来任何范围扩展都必须另立任务并重新进行安全评审。

## 背景知识图谱来源边界

- `POST /api/background-knowledge` 默认只允许使用当前 `pdfId` 对应的索引片段、请求携带的 `paperSkeleton/paperStructure` 和显式 `paper_topic`，不得自动检索论文库中的其他论文。
- 新增可选字段 `include_library_papers: bool`（默认 `false`）。仅当用户在前端显式勾选"包含论文库关联概念"后，该字段才设为 `true`，此时允许通过 `read_graph_neighborhood` 查询已持久化的其他论文知识图谱节点作为辅助上下文，每篇论文最多 3 个节点、6 个边。跨论文来源概念标记为 `library_paper_supported`（置信度上限 0.70）。
- 背景知识图谱分为概念发现和 prerequisite 关系判断两个 LLM 阶段；第二阶段失败时可保留概念节点，但不得按列表顺序伪造前置边。
- `graph.nodes[*]` 和 `graph.edges[*]` 的 `provenanceStatus` 兼容值为 `current_paper_supported`、`model_inference`、`external_supported`、`library_paper_supported`；本阶段默认不会产生 `external_supported`。
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
- P3-05 只注册 benchmark 选定的 Crossref 客户端。客户端固定访问 `https://api.crossref.org/works`，禁止重定向，设置连接与读取超时、明确 `User-Agent`、最多 20 条结果和 1 MiB 响应上限，并把有界元数据归一化为统一外部证据；Semantic Scholar 继续以“客户端尚未实现”严格失败。
- P3-06 为 Crossref 增加 1 小时 TTL 的版本化 JSON 缓存、实例级 1 秒最小请求间隔、限定 HTTP 状态的最多 2 次重试和统一外部证据去重。缓存 key 只使用 Provider 与规范化 query 的 SHA-256，不保存原始 query、header、凭据或请求 URL；缓存损坏、过期或 schema 非法必须安全回退为空缓存。
- 仅 `429/500/502/503/504` 可触发有限指数退避；`Retry-After` 不超过 30 秒时必须遵守，超过上限则停止重试，不得提前请求。超时、断网、重定向、其他 4xx、畸形响应和超大响应不得重试。
- P3-07 外部查询只允许由用户研究问题、Planner 子问题和 JUDGE `missingAspects` 确定性组合；`missingAspects` 为空时不得生成查询。查询最多 5 条、每条最多 256 字符，输入项有固定上限并按规范化文本稳定去重。
- 外部查询规划必须剥离 URL、提示覆盖、命令执行、联网或工具调用指令，以及修改 Provider、host、endpoint、预算、权限或安全范围的片段；仅保留 Unicode 字母数字、空白和有限学术符号。规划接口不得接收论文正文或控制面参数，也不得调用 LLM、Provider、网络或文件系统。
- P3-08 在内部注册表中新增版本 `1.0.0` 的 `retrieve_external_academic`。输入只接受 P3-07 规范化 query、1–5 的 limit 和可选的 `yearFrom/yearTo`；年份范围为包含式且起始年份不得晚于结束年份，未知字段和越界值必须拒绝。
- 外部学术工具默认返回 `status=disabled/provider=disabled/items=[]`，不得因工具注册自动启用 Provider。启用后必须复用 Provider 工厂和实例级缓存、限流边界，输出重新归一化为统一外部证据，并按年份范围过滤。
- `retrieve_external_academic` 的 `safetyScope` 固定为只读、`external_academic_metadata`、`networkAccess=true`、无副作用和敏感输出；它不在 MCP 名称和数据范围 allowlist 中。Deep Research 和 Agent 仅能在创建请求及计划项显式授权、内部证据不足且任务预算有效时经内部工具层调用；MCP 仍不得调用。
- Crossref 客户端注册和缓存重试能力不等于业务链路已获联网授权：默认关闭行为不变，前端开关和 Agent 计划审查默认 `false`，论文、模型和外部响应都不能自行开启。
- P3-09 为内部外部检索工具增加任务级审计与预算计数。public trace summary 必须包含 `externalSearchCalls/externalSearchCacheHits/externalSearchFailures/externalEvidenceCount/externalSearchLatencyMs/externalSearchBudgetBlocks`；外部检索 step 只允许记录 Provider、预算状态、结果数量和 `queryHash/queryLength/tokenCount`，不得记录完整 query、完整摘要、完整响应、headers 或密钥。
- 外部检索默认任务预算为最多 3 次 Provider 调用和最多 15 条外部证据结果。预算耗尽时必须在调用 Provider 前停止，返回 `budget_exceeded` 与脱敏原因，并计入 `externalSearchBudgetBlocks`；Provider 失败必须返回 `failed` 与脱敏原因并计入 `externalSearchFailures`。
- P3-15 固化对抗边界：Crossref 标题、作者和 HTML/JATS 摘要中的提示覆盖、凭据索取等指令式片段必须替换为安全占位文本，同时保留同字段中的正常学术内容和既有长度上限。
- 外部检索失败只允许向 Deep Research、Agent、trace 和持久化快照传播状态白名单对应的固定降级原因；Provider 原始异常、响应体、query 和凭据不得进入工具调用摘要。工具版本、预算和 `safetyScope` 不得由失败响应修改。
- SSRF 与故障边界必须由离线 fixture 持续验证：请求目标固定为 Crossref HTTPS endpoint 且 `allow_redirects=false`，私网或非白名单 `Location` 不得产生第二次请求；超大响应、畸形 JSON、429、5xx、超时和断网均按既有有界策略封闭失败。
- P3-04 benchmark 结论见 [`external_search_benchmark.md`](external_search_benchmark.md)。2026-06-21 匿名采样中 Crossref 成功 6/6，Semantic Scholar 因 6 次 HTTP 429 被判定为匿名运维不可用；项目不要求配置 Semantic Scholar API key，P3-05 唯一实现目标为 Crossref。
- benchmark 只评估无需凭据的匿名可用性。至少一个候选必须成功完成 5/6 case；对全部 case 均因匿名 429 失败的候选允许标记为运维不适用并排除，但不得把其他超时、畸形响应或部分失败伪装为排除条件。
- benchmark 网络代码仅允许在 `ai-service-python/benchmarks/external_search/` 中显式 `--live` 运行，不得复用为生产客户端。默认离线评分不得联网，失败结果不得通过降低门槛、切换来源或扩大白名单绕过。
- P3-16 跨服务 contract 必须覆盖创建、计划审查、任务查询和最终审查；Playwright route fixture 必须离线验证默认关闭、显式授权、外部来源、Provider 降级、刷新恢复与人工审查。
- P3-17 严格门槛固定为：错误引用率 `0`，安全与人工一致性 `100%`，开启后证据覆盖率至少 `0.8` 且提升至少 `0.15`，冲突发现率至少 `0.8` 且不回退，平均调用不超过 `3`，平均外部延迟不超过 `3000ms`，Provider `hitAt5` 至少 `0.8`。任一门槛失败必须保持默认关闭。

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
- Agent 终态任务会把脱敏 public trace summary 写入 `task.traceSummary` 并随 SQLite 快照保存；进程内 trace 丢失或服务重启后，`GET /api/agent-traces/{traceId}` 可按 `traceId` 从任务快照恢复。旧快照没有 `traceSummary` 时按空对象兼容。
- `GET /api/agent-projects/{projectId}/workspace` 与 `agent-runs/*` 是新的公开主资源；`/api/agent-projects*` 与 `/api/agent-tasks*` 兼容路径必须继续可用，但不得再作为新的内部写入真相。
- 服务重启前已经进入 `succeeded`、`failed` 或 `cancelled` 的任务按快照恢复。
- 服务重启前仍处于 `running` 或 `pending` 的任务恢复为 `failed`、`stage=done`、`progress=1.0`，`error` 固定为 `Agent task was interrupted by service restart.`，并追加 `task_expired` 事件。
- 项目级任务历史列表接口已补齐：`GET /api/agent-projects/{projectId}/tasks` 由 Java `/api` 透传到 Python `/api`。
- 任务历史成功响应保持 `{ "status": "success", "projectId": "...", "tasks": [], "limit": 20 }`，`tasks` 复用完整 Agent task 快照并按 `updatedAt` 倒序返回。
- `limit` 默认 `20`，Python 侧约束到 `1..100`；项目存在但没有任务时返回空数组，项目不存在时返回 `404 Agent project not found.`。
- 前端进入、切换、刷新或轮询 Agent 项目时优先读取 `workspace` 聚合视图；本地 `tasksByProjectId` 只作为旧接口、离线或临时失败 fallback。

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
