# 更新日志

本记录用于追踪学术 AI 助手的功能迭代与优化。

### 2026-07-12 v0.1.87

1. **注册 fetch_web_page 工具与缓存集成**：在 ToolRegistry 注册 `fetch_web_page` 工具（restricted access），输入 url/maxChars(1000-16000)，预算 10 次调用/80,000 chars；新增 `web_fetch_cache.py`（SHA-256 URL key，24h TTL，JSON 存储，blocked 内容不缓存）；缓存集成到 `web_fetcher.fetch_web_page()` 的 fetch pipeline（命中跳过网络，成功后写入缓存）。

### 2026-07-12 v0.1.86

1. **实现抓取内容安全验证**：新增 `content_safety.py`，`sanitize_fetched_web_content()` 执行提示注入检测（复用 `safety_service.detect_prompt_injection`）、安全分级（safe/flagged/blocked）、blocked 内容整页拒绝（恶意软件/钓鱼/色情/暴力）；URL 可信度标记 high(.gov/.edu/学术出版商)/medium(Wikipedia/GitHub/新闻)/low(.com)/unknown；token 截断（tiktoken cl100k_base，默认 4000 tokens，char-ratio 回退）；已集成到 `web_fetcher.py` fetch pipeline。

### 2026-07-12 v0.1.85

1. **实现 HTML 内容提取与清洗**：新增 `html_extractor.py`，使用 BeautifulSoup + lxml 解析 HTML；移除 script/style/iframe/object/embed/svg/math/form/input 等 18 种危险标签；移除 HTML 注释和 CDATA；文本后处理含空白压缩、连续换行去重（最多 2 个）、50,000 chars 上限、不可打印字符过滤；保留 title/URL/提取时间作为元数据。

### 2026-07-12 v0.1.84

1. **实现 Web 页面抓取基础设施**：新增 `web_fetcher.py`，实现完整安全检查链（白名单校验 → DNS 解析检查 → HTTPS 强制 → `allow_redirects=False` → Content-Type 预检查 text/html|text/plain|application/json → 2 MiB 上限 → UTF-8 转码）；并发控制 `threading.Semaphore(3)` + per-host 速率限制 2 秒；仅对 429/5xx 最多 1 次重试（共 2 次尝试）；所有错误返回使用错误码字符串（`FetchError` 类），不含原始 URL 和响应体；`FetchResult` 为 frozen dataclass 不可变。

### 2026-07-12 v0.1.83

1. **注册 search_web 工具并接入 Agent/Research**：在 ToolRegistry 注册 `search_web` 工具（`safetyScope.access="restricted"`），输入 query(1-300 chars)/limit(1-10)/searchType(general/academic/news)，预算每任务 5 次调用/20 条结果；仅在学术检索+外部学术都不足且 `allowWebSearch` 授权时触发。
2. **新增 Web 搜索查询规划器**：`external_query_planner.py` 新增 `build_web_search_queries()` 函数，从 missingAspects 生成 Web 搜索 query（300 chars 上限，最多 5 个）。
3. **集成 Web 搜索到研究执行器**：`research_executor.py` 新增 `should_try_web_search()` 门控和 `retrieve_web_search_evidence()` 检索函数；`agent_orchestrator.py` 新增 Agent 路径的 Web 搜索阶段。
4. **新增 allowWebSearch 请求字段**：`schemas/requests.py` 中 5 个 Pydantic models 新增 `allowWebSearch: bool` 字段；`agent_project_service.py` 的 `externalSearchConfig` 包含 `allowWebSearch`。
5. **新增 Web 搜索查询安全清洗**：`safety_service.py` 新增 `sanitize_web_search_query_text()` 函数，对 Web 搜索 query 执行 URL 去除、注入检测和控制字符过滤。
6. **前端新增 Web 搜索授权开关**：AgentWorkspace 创建任务和计划审查表单中新增"授权网页搜索"开关；DeepResearchPanel 新增网页搜索开关；`agentWorkspaceModel.js` 的 `buildAgentPlanReviewPayload` 映射 `allowWebSearch`。

### 2026-07-12 v0.1.82

1. **定义 Web 搜索安全模型**：新增 `url_whitelist.py`，按 6 类别（学术出版商/政府/组织/新闻/百科/代码仓库）组织 70+ 域名白名单；实现 `validate_fetch_url(url)` 10 步验证链（HTTPS 强制 → 白名单匹配 → DNS 解析 → 内部 IP 拒绝）；新增 `docs/P6_WEB_SEARCH_SECURITY_PLAN.md` 定义完整威胁模型、安全边界和审计要求。
2. **放松研究子问题 blocklist**：`_RESEARCH_SUBQUESTION_BLOCKLIST` 移除 `web search|browse|internet|online` 及中文对等词拦截，保留 `tool|plugin|mcp|agent|execute command` 危险指令检测。
3. **实现 Brave Search API Provider**：新增 `BraveSearchProvider`，通过 `https://api.search.brave.com/res/v1/web/search` 进行通用 Web 搜索；`BRAVE_SEARCH_API_KEY` 必填，`X-Subscription-Token` header 认证；结果归一化为 `sourceType="web_search"`，字段为 title/url/description；`supports_web_search=True`，缓存 TTL=30 分钟。
4. **实现 Tavily Search API Provider**：新增 `TavilyProvider`，通过 POST 请求 `https://api.tavily.com/search` 进行 AI-optimized Web 搜索；`TAVILY_API_KEY` 必填，`search_depth="advanced"`；Tavily `answer` 字段以 JSON `{"ai_generated_summary": true}` 存入 license 字段，不冒充原始内容；`supports_web_search=True`，缓存 TTL=30 分钟。
5. **扩展外部证据模型**：`external_evidence.py` 新增 `WEB_SEARCH_SOURCE_TYPE = "web_search"`；`normalize_external_evidence()` 新增 `source_type` 参数以支持 Web 搜索和学术搜索两种来源类型。
6. **注册 Web 搜索 Provider**：`SUPPORTED_PROVIDERS` 新增 `brave` 和 `tavily`；Provider Registry 的 `supports_web_search` 能力标记现在可反映 Web 搜索 Provider 的存在。

### 2026-07-12 v0.1.81

1. **实现 Semantic Scholar Provider（带 Key 认证）**：新增 `SemanticScholarProvider`，通过 `https://api.semanticscholar.org/graph/v1/paper/search` 检索论文元数据；支持可选 `SEMANTIC_SCHOLAR_API_KEY` 通过 `x-api-key` header 认证以突破匿名 429 限流；JSON 响应解析后归一化为统一外部证据模型，字段筛选 `title,authors,year,abstract,externalIds,url,publicationVenue`；HTTP 超时、重试、速率限制和缓存与 Crossref/ArXiv 一致。
2. **完成三 Provider 基准评测与选型决策**：扩展 `provider_benchmark.py` 至 3 Provider × 12 跨学科 query（新增医学/化学/物理学/经济学/社会科学）；新增 ArXiv Atom XML 响应解析与离线评分；`select_provider` 升级为 `select_providers`，输出推荐 Provider 组合和 `productionConfig`；离线 snapshot 确定性评分产出选型结论：推荐组合 `arxiv,crossref`，Semantic Scholar 因匿名 429 限流标记为 excluded。
3. **补充 Provider 选型文档**：新增 `docs/p6_provider_selection.md`，记录评测方法、12 个跨学科 query、Provider 特性对比、离线评测结果和推荐生产配置。

### 2026-07-11 v0.1.80

1. **新增多 Provider 注册中心**：`ExternalSearchProviderRegistry` 支持通过 `PIXIU_EXTERNAL_SEARCH_PROVIDERS=crossref,arxiv` 逗号分隔同时启用多个 Provider；`search_all(query, limit)` 使用线程池并发搜索并去重合并；Protocol 新增 `supports_web_search` 和 `supports_page_fetch` 能力标记；向后兼容单 `PIXIU_EXTERNAL_SEARCH_PROVIDER` 配置。
2. **实现 ArXiv API Provider**：新增 `ArxivProvider`，通过 `https://export.arxiv.org/api/query` 免费检索论文元数据（无需 API Key）；Atom XML 响应解析后归一化为统一外部证据模型，支持标题/作者/年份/摘要/DOI/URL/许可；HTTP 超时、重试、速率限制和缓存与 Crossref 一致。
3. **修复 ArXiv 摘要解析**：使用 `itertext()` 正确处理包含子元素（如 `<em>`）的摘要文本；引入 BeautifulSoup 清洗 HTML 标签。
4. **更新工具注册层**：`_retrieve_external_academic_tool` 新增 `_resolve_provider_display_name()` 和 `_resolve_provider_names_list()`，Registry 模式下 trace 记录所有子 Provider 名称。
5. **补齐 gitignore 白名单**：新增 `test_arxiv_provider.py` 和 `test_external_search_registry.py` 到 Git 跟踪范围。

### 2026-07-10 v0.1.79

1. **完成沙箱逃逸对抗测试**：新增 7 项攻击探针覆盖路径穿越、符号链接、环境变量泄露、DNS 解析、Docker socket、fork 炸弹和 CSV 公式注入，Docker 沙箱全部 18 项探针通过，无可利用逃逸向量。
2. **完成端到端验证与最终去留决策**：新增 7 个 mock Worker 集成测试覆盖完整生命周期；决策为 `continue_limited`，仅授权 `run_descriptive_statistics` 工具，永久禁止通用 Shell、任意代码执行和网络访问。
3. **强化 Worker 验证层安全测试**：新增 12 项对抗验证测试，覆盖模板篡改、镜像伪造、符号链接输入、摘要不匹配、非标准库导入和公式/路径注入检测。

### 2026-07-10 v0.1.78

1. **注册单一受限数据分析工具**：内部工具注册表新增 `run_descriptive_statistics`，只接受已批准的 artifact ID，使用不可修改的固定模板创建代码执行任务；Agent 无法注入脚本或绕过审批。
2. **扩展安全范围验证**：`safetyScope` 新增 `restricted` 访问级别，与 `sideEffects=true` 强绑定；已有 9 个工具的 `read_only` 安全范围保持不变。
3. **接入 Agent 显式实验工作流**：Agent 任务新增 `codeExecutionConfig` 字段和 `awaiting_tool_approval` 暂停状态；计划审查支持授权代码执行实验，Agent 产出 proposal 后暂停等待用户审批。
4. **报告区分三类证据来源**：Agent 报告新增"代码计算产物"章节，清晰区分论文证据、外部学术证据和代码计算产物。
5. **补齐持久化与恢复语义**：`codeExecutionConfig` 通过 SQLite 持久化，`awaiting_tool_approval` 状态在服务重启后保持不变；旧快照缺少新字段时自动兼容为空默认值。

### 2026-07-08 v0.1.77

1. **完成 Agent 公开资源化迁移**：Python、Java 与共享契约新增 `workspace`、`runs`、`run`、`plan-review`、`final-review`、`artifacts` 和 `timeline` 资源接口，Agent 对外主写路径转向 `agent-projects/{projectId}/runs`，主读路径转向 `agent-projects/{projectId}/workspace`。
2. **切换前端 Agent 工作区主链路**：进入项目、刷新、轮询、计划审查与终稿审查优先走 `workspace + runs` 聚合资源，新增 run/workspace 归一化模型与浏览器 mock；本地 `tasksByProjectId` 和旧 task API 继续保留为离线、旧后端或临时失败 fallback。
3. **收口旧 task 为兼容适配层**：`agent-projects/{id}/tasks*` 与 `agent-tasks/*` 仍保持可用，但内部创建、审查、读取与恢复都改为从 run/review/artifacts/timeline 资源映射回旧 task snapshot，不再直接写入旧 task-shaped 持久化真相。

### 2026-07-05 v0.1.76

1. **增加双重人工审批闭环**：新增受限 CSV 暂存、固定任务创建、执行前审批与产物发布前审批 API，并以任务和发布摘要阻止过期审批。
2. **开放全局执行审批中心**：用户可核验固定脚本、标准库依赖、输入摘要、运行时、资源限制、执行产物和脱敏审计事件；失败或未批准产物不可发布。
3. **保持研究证据隔离**：发布批准仅建立服务端 `publishable` 门禁，本阶段计算结果不会自动进入 Deep Research、Agent evidence 或工作台。

### 2026-07-03 v0.1.75

1. **增加宿主侧脱敏执行审计**：任务快照、独立脚本文本和创建、审批、执行事件通过 SQLite 单事务持久化，服务重启后可恢复核验。
2. **建立追加式防篡改哈希链**：审计事件绑定前序摘要、任务与脚本摘要、运行环境、输入输出摘要、资源限制及退出状态，篡改、删除、重排或半份记录均封闭失败。
3. **隔离 Worker 与审计权限**：Worker 容器不挂载审计库，只返回有界结果；public trace 增加代码执行计数并继续排除原始数据、脚本、日志、路径和凭据。

### 2026-07-02 v0.1.74

1. **补齐 Worker 资源配额**：固定限制 CPU 时间与速率、墙钟、内存、进程、输入、日志、临时空间、输出大小和文件数，并为各类超限返回稳定脱敏原因。
2. **增加可取消执行生命周期**：保留同步 `run_job` 入口，新增内部可取消执行句柄，超时、超限或取消均强制终止容器。
3. **实现封闭式清理观测**：任务结束后删除容器、核验残留并清理唯一临时目录；清理失败返回有界摘要，污染资源不复用。

### 2026-07-02 v0.1.73

1. **实现无网络隔离 Worker 原型**：新增仅供内部调用的固定模板 Docker Worker，校验任务审批、模板、镜像及输入摘要，不新增 FastAPI、Agent 或 MCP 入口。
2. **固定最小运行边界**：Worker 使用固定 Python 3.13.9 镜像、非 root 用户、无网络、只读根文件系统与输入、独立临时输出、清空 capabilities、seccomp 和最小环境。
3. **稳定返回脱敏执行结果**：成功与失败统一返回有界状态、原因码、退出码和输出摘要，不暴露 Docker stderr、宿主路径、密钥或原始 CSV。

### 2026-07-02 v0.1.72

1. **定义受限执行任务模型**：新增严格的 artifact、固定运行时与镜像、资源配额、无网络策略和受控 JSON 产物模型，并保持无执行 API、Worker 或数据库。
2. **绑定确定性审批摘要**：脚本文本与摘要分离，canonical 任务摘要覆盖全部执行相关字段；有效任务变化会清除旧审批，越界配置会封闭拒绝。
3. **规划持久化与脱敏审计边界**：明确未来任务快照与脚本文本分表存储、恢复校验和有界审计规则，旧系统无需迁移。

### 2026-07-01 v0.1.71

1. **完成沙箱技术实测**：新增可重复的 Docker 与 Windows Job Object 安全 benchmark，覆盖正常/恶意 CSV、网络、文件隔离、子进程、资源上限和清理。
2. **选定后续建模候选**：加固 Docker Linux 容器全部强制探针通过且无残留容器；Windows 原生方案未满足无网络、宿主文件隔离和只读输入，因此淘汰。
3. **保持生产能力关闭**：最终决策仅为 `continue_to_p5_03`，不新增 Worker、执行 API、工具注册或通用 Python/Shell 能力。

### 2026-06-30 v0.1.70

1. **锁定唯一 code-native 场景**：范围仅限用户确认的单个 UTF-8 CSV，由不可修改的 Python 标准库模板生成有界描述统计 JSON，不提供任意代码能力。
2. **建立代码执行威胁模型**：明确提示注入、CSV/公式注入、路径穿越、资源耗尽、数据泄露、供应链和沙箱逃逸等风险及强制控制。
3. **设置后续停止门槛**：当前不实现 Worker、API、UI 或工具；P5-02 无法证明隔离、无网络、资源限制和可靠清理时停止后续接入。

### 2026-06-30 v0.1.69

1. **完成 Council 对照评测**：固定质量、效用、失败率、延迟和 token 门槛，新增真实双 Reviewer 脱敏 snapshot、确定性离线评分和自动去留决策。
2. **作出移除生产接入决策**：双 Reviewer 质量与效用门槛全部通过，但平均延迟 `2.79183x`、平均 token `2.512443x` 超过 `2.5x` 上限，因此移除 Deep Research 的 Council 请求、快照、trace、前端展示和人工核查流程。
3. **保留可复现实验边界**：继续保留 `council_service.py`、固定 fixture 和 benchmark 结论；第二 Provider 仍不在范围内，未来恢复必须另立任务并重新授权。

### 2026-06-30 v0.1.68

1. **展示 Council 独立意见与分歧**：Deep Research 终稿区展示 Reviewer 的 provider/model、结论、引用、弃权、分歧和 token 成本，并保留安全降级状态。
2. **增加 Council 人工核查闭环**：终稿请求新增结构化 `councilReviews`，逐项保存“已核查”或“保留分歧”，旧快照缺失状态时兼容为待核查。
3. **细分 Council trace 成本**：public trace 新增 Council 调用、失败、延迟和输入/输出/总 token 计数，同时继续隐藏 prompt、证据正文和隐藏推理。

### 2026-06-30 v0.1.67

1. **加入默认关闭的 Deep Research Council Pilot**：创建任务可显式设置 `allowCouncil`，在报告综合前按风险优先审查最多 3 个 conflict/finding；关闭时不产生额外模型调用。
2. **持久化 Council 审查快照**：SQLite 与三端共享契约新增 `task.council`，保存 target 来源绑定、双 Reviewer 结果、状态和脱敏降级原因，并兼容旧快照。
3. **保持人工审查与安全降级边界**：Reviewer 弃权保留其他意见，Council 整体异常不阻断报告，结果不写入报告或 `reviewRisks`，任务仍必须进入终稿人工审查。
4. **取消第二付费 Provider 计划**：移除未知来源的 DashScope 密钥配置与运行时读取，P4-05 按安全决策取消；后续评测只比较单模型与同模型双 Reviewer。

### 2026-06-30 v0.1.66

1. **新增同模型独立 Reviewer 实验**：Council 使用同一 Provider 的两个独立上下文生成 evidence reviewer 与 contradiction reviewer 结构化意见，严格限制可引用的输入 `sourceId`。
2. **增加安全弃权语义**：空证据、证据不足、Provider 或解析失败、非法 verdict 和未知来源统一转为脱敏 abstention，同时保留其他有效 Reviewer 意见。
3. **定义保守 Council 聚合模型**：结果显式保留 agreements、disagreements、abstentions 和 evidenceCoverage；无共同证据不形成强共识，高风险分歧和 conflict 意见仅建议人工核查。
4. **保持生产隔离**：Council 当前不注册公开接口、不持久化，也不接入 Deep Research、Agent、Java 或前端。

### 2026-06-30 v0.1.65

1. **抽出 Provider 中立 LLM 契约**：DeepSeek 与离线 fixture 统一实现结构化请求、`provider/model/content/usage` 结果和脱敏错误模型，保留现有 `_call()` 字符串兼容层。
2. **补齐真实与估算 usage**：DeepSeek 优先读取 API token usage，fixture 支持固定 usage；缺失时使用确定性估算并显式标记，不改变现有 trace 计数和翻译模型配置。
3. **完成 Council 单模型基线**：新增五类固定审查用例、显式 live 采样入口、脱敏 snapshot 校验及离线评分器；首次 `deepseek-v4-pro` 采样的准确率、引用正确率、冲突召回率和提示注入通过率均为 `1.0`，平均延迟 `2886.237 ms`。

### 2026-06-29 v0.1.64

1. **完成外部检索跨服务验证**：共享 contract 扩展到 Deep Research 和 Agent 的创建、计划审查、任务查询及终稿审查，覆盖外部证据、Provider、预算和降级状态。
2. **补齐浏览器端完整路径**：新增外部 Provider route fixture，覆盖默认关闭、显式授权、外部来源与报告引用、Provider 故障降级、刷新恢复和最终人工审查。
3. **修正 Agent 计划授权字段**：计划审查中的外部检索授权现在写入 `planItems[id=external].allowExternalSearch`，确保与 Python 请求契约一致。
4. **新增严格离线效果评测**：固定配对任务统计证据覆盖、错误引用、冲突发现、延迟、调用次数、安全与人工一致性，并生成确定性评测结果。
5. **保持生产默认关闭**：Crossref `hitAt5=0.333333` 未达到 `0.8` 门槛，启用决策为 `continue_default_disabled`。

### 2026-06-28 v0.1.63

1. **外部元数据提示注入防护**：Crossref 标题、作者和 JATS/HTML 摘要中的提示覆盖、凭据索取等指令式片段会替换为安全占位文本，同时保留正常学术内容及原有字段长度限制。
2. **固定外部检索故障降级原因**：Deep Research 与 Agent 不再传播 Provider 原始失败原因；工具异常统一映射为脱敏状态说明，Agent 工具调用继续保留版本和只读 `safetyScope`，但不保存原始异常文本。
3. **固化 SSRF 与故障边界**：外部检索继续固定访问 Crossref HTTPS endpoint、禁止重定向，并对私网重定向、超大响应、畸形 JSON、限流、服务错误、超时和断网保持封闭式失败。

### 2026-06-26 v0.1.62

1. **外部学术来源接入前置知识图谱**：`knowledge_graph_service.py` 新增概念与前置边的外部证据丰富化，对无当前论文依据的 `model_inference` 概念通过外部 Provider 检索补充证据，匹配成功时升级为 `external_supported` 溯源并写入外部 `sourceIds`。
2. **前置边随关联概念升级**：当一条前置边的源和目标概念均已获得论文或外部证据支持时，该边同步升级为 `external_supported`，置信度上限提升至 0.95。
3. **严格兼容与降级**：Provider 禁用或检索失败时概念和边保持原有 `model_inference` 溯源，不改变现有图谱行为；外部 `sourceIds` 仅引用本次返回的统一外部证据 ID。
4. **前端展示外部证据覆盖**：背景知识"看依据"页面在节点和边的出处摘要中显示外部证据支持数量，并在外部来源已启用或有外部证据补充时更新状态说明。
5. **新增 7 项回归测试**：覆盖外部升级、跳过已支持概念、Provider 故障降级、禁用降级、边升级、边不升级和出处摘要计数。

### 2026-06-26 v0.1.61

1. **新增前端外部学术检索授权开关**：Deep Research 面板和 Agent 任务组合器新增 pill 样式开关，默认关闭并说明仅访问白名单学术来源（Crossref、Semantic Scholar）；开启后 `allowExternalSearch` 随任务创建请求发送到后端。
2. **计划审查阶段展示 Provider 与预算**：`ResearchPlanReviewForm` 和 `AgentPlanReviewForm` 在外部检索开启时显示 Provider 名称、调用次数/上限、证据数量/上限和降级原因。
3. **任务执行中显示外部调用状态**：Deep Research 任务进度卡片在执行阶段展示外部检索 Provider、已调用次数、已收集证据数量，降级时以琥珀色高亮降级原因，不再仅限 DEV trace 面板可见。
4. **外部证据来源可视化区分**：`SourceChip` 和 `SourceList` 对外部学术来源使用 Globe 图标和靛蓝色调渲染，标签显示"外部来源 · Provider · 年份"，展开卡片展示完整元数据（标题、作者、DOI、URL、检索时间、许可和摘要）。
5. **安全降级无伪链接**：当外部来源缺失 URL 且无可解析 DOI 时，`canJumpToSource` 为 `false`，保留元数据而不生成虚假链接。
6. **任务模型归一化外部搜索配置**：`deepResearchPanelModel` 和 `agentWorkspaceModel` 新增 `externalSearchConfig` 归一化，含安全默认值；`createEmptyDeepResearchState` 新增 `allowExternalSearch` 字段。

### 2026-06-25 v0.1.60

1. **扩展请求契约：新增 `allowExternalSearch` 字段**：`ResearchTaskCreateRequest`、`AgentTaskCreateRequest` 和 `AgentPlanItemRequest` 新增显式 `allowExternalSearch` 字段，默认 `false`，旧请求无需修改即可正常使用。
2. **任务快照新增 `externalSearchConfig` 列**：Deep Research 和 Agent 的 SQLite 表新增 `externalSearchConfig` 列，保存配置开关、Provider、预算、使用状态和降级原因，旧快照自动使用空默认值。
3. **同步更新合约 fixture**：`api-contract-smoke.json` 的 research 和 agent-tasks 操作新增 `allowExternalSearch` 请求字段和 `externalSearchConfig` 响应字段，三端 contract smoke 测试自动验证字段类型。

### 2026-06-25 v0.1.59

1. **接入多论文 Agent 外部学术补查**：Agent 在 focused papers 和内部文献库证据不足时，可通过计划中的显式开关 `allowExternalSearch` 授权使用同一只读外部学术检索工具补充证据。
2. **Agent 计划新增外部检索授权项**：`build_review_plan_items` 生成第 4 项 `external` 计划项，默认 `allowExternalSearch: false`；`normalize_review_plan_items` 保留该字段，用户审批后可开启。
3. **报告区分当前论文、内部库与外部学术证据**：Agent 报告中新增 "External Academic Evidence" 区块，外部来源标注 Provider、年份、DOI/URL 和检索时间，证据快照中显式标注"（含外部学术检索）"。
4. **外部证据参与 Agent 冲突检测**：新增 `external-evidence-coverage` 冲突类型，标记外部补充证据不应被视为与索引论文同等可靠。
5. **保持 SQLite 旧快照兼容**：外部证据和工具调用存储在现有 JSON 列中，无需模式迁移；旧快照无 `external_academic` 来源类型时正常加载。
6. **保持取消、失败与重启恢复语义不变**：外部检索阶段尊重取消检查，失败时降级继续使用内部证据，重启后状态可恢复。

### 2026-06-25 v0.1.58

1. **接入 Deep Research 外部学术补查**：当内部检索（当前论文 + 内部文献库 + 重试）后 JUDGE 仍发现证据缺口时，自动执行一次受预算约束的外部学术检索，并按"当前论文 → 内部文献库 → 外部学术来源"顺序合并证据。
2. **外部检索降级策略**：Provider 禁用、预算超限或调用失败时，任务继续使用内部证据并记录 `externalSearchDegradation` 原因；外部结果不自动裁决冲突。
3. **报告与 trace 标识外部来源**：报告中对含外部学术检索的 finding 显式标注，降级情况输出说明；trace summary 新增 `externalSearchDegradationCount` 计数。

### 2026-06-23 v0.1.57

1. **增强外部学术检索 trace 审计**：内部外部检索工具新增调用、缓存命中、失败、证据数量、延迟和预算阻止计数，并只记录脱敏 query 摘要。
2. **加入外部检索任务级预算**：默认限制每个 trace 最多 3 次外部 Provider 调用和 15 条外部证据，超限时停止调用并返回结构化预算阻止原因。
3. **持久化 Agent trace summary**：Agent 终态任务会把 public trace summary 写入 SQLite 快照，进程内 trace 丢失后仍可按 `traceId` 恢复关键摘要。

### 2026-06-22 v0.1.56

1. **新增受限学术查询规划**：仅从用户研究问题、Planner 子问题和 JUDGE 证据缺口确定性生成查询，固定限制数量、长度、输入规模并稳定去重。
2. **隔离查询控制面**：剥离 URL、命令、联网、工具调用及 Provider、host、预算和权限修改指令；查询规划不接收论文正文或控制参数，也不调用 LLM、Provider、网络或文件系统。
3. **保持业务链路默认关闭**：查询规划不直接接入 Deep Research、Agent、前端、公开 API 或 MCP，现有外部检索授权边界不变。
4. **注册只读外部学术检索工具**：内部工具注册表新增版本化 `retrieve_external_academic` 契约，严格限制 query、结果数和年份范围，并将结果归一化为统一外部证据。
5. **保持工具默认不可用**：未启用外部 Provider 时返回结构化禁用状态；启用后复用 Provider 实例的缓存、限流和故障边界，不提前接入 Deep Research 或 Agent。
6. **维持 MCP 隔离范围**：外部学术检索工具声明受控网络访问，但不加入 MCP 名称或数据范围 allowlist，现有 MCP 三个只读工具保持不变。

### 2026-06-22 v0.1.55

1. **实现首个只读学术 Provider 客户端**：新增 Crossref 固定 HTTPS 客户端，以结构化参数检索论文元数据并归一化为统一外部证据；限制超时、重定向、结果数、响应体和外部字段长度。
2. **注册 Crossref 并保持默认关闭**：Provider 工厂仅内置 Crossref，Semantic Scholar 继续严格标记为未实现；当前不接入 Deep Research、Agent、前端、公开 API 或 MCP，也不提前加入缓存、重试、限流与去重。
3. **增加外部检索持久缓存与安全恢复**：Crossref 使用规范化 query 哈希和 1 小时 TTL 的原子 JSON 缓存，缓存不保存原始 query、header、凭据或请求 URL，文件损坏、过期或 schema 非法时安全回退为空缓存。
4. **限制外部请求频率与故障重试**：同一客户端实例限制请求间隔，仅对 429 和明确 5xx 状态执行最多 2 次有限退避并遵守有界 `Retry-After`；结果按 DOI、Provider ID 和规范化标题去重后再缓存。

### 2026-06-21 v0.1.54

1. **固化外部学术检索威胁模型**：明确默认关闭、只读访问、不可信内容处理、证据优先顺序和人工审查边界，并禁止任意 URL、全文下载、文件系统访问及模型直接联网。
2. **限定候选 Provider 白名单**：只允许 Crossref 与 Semantic Scholar Academic Graph 的固定论文元数据端点进入后续 benchmark，其他 Provider、host、重定向和服务类型保持禁止。
3. **明确失败降级与审计边界**：Provider 超时、限流、无效响应或不可用时继续使用内部证据；trace、日志和错误不得记录密钥、认证 header、完整响应或完整摘要。
4. **定义统一外部证据模型**：新增 Provider 中立的外部学术证据规范化与稳定来源 ID，固定缺省字段语义，并让现有 evidence 流程保留 Provider、作者、年份、摘要、DOI、URL、检索时间、query 和许可元数据。
5. **抽出外部检索 Provider 边界**：新增单 query 协议、只读禁用实现和严格配置工厂；默认配置不读取 Provider 或构造客户端，显式启用时对缺失、未知、未实现和无效 Provider 严格返回脱敏配置错误。
6. **完成外部 Provider 隔离 benchmark**：新增 Crossref 与 Semantic Scholar 的固定匿名采样、脱敏 snapshot 和离线评分；Crossref 以 6/6 成功且无需认证被选为 P3-05 唯一目标，Semantic Scholar 因匿名请求全部 429 被判定为运维不适用。

### 2026-06-21 v0.1.53

1. **新增非开发用户使用指南**：覆盖 PDF 上传、论文库恢复、问答、划词解释、翻译、背景补课、引导学习、批判阅读和工作台保存。
2. **补齐双研究流程说明**：完整记录 Deep Research 与多论文 Agent 的任务创建、双阶段人工审查、来源核对、结果保存和历史恢复行为。
3. **加入安全的界面示例与故障处理**：使用无真实论文和敏感信息的 Mock 截图说明关键界面，并集中说明 OCR、索引、服务异常、任务中断和来源降级等常见问题。

### 2026-06-21 v0.1.52

1. **建立跨服务 API 契约 fixture**：新增共享 request/response fixture，覆盖 chat、批判阅读、背景知识、Deep Research、trace 和 Agent 项目、任务及 trace。
2. **统一三层契约 smoke**：Python 验证 FastAPI 路由与请求模型，Java 验证 `/api` 网关路由和响应包装，前端验证请求路径、请求体、Agent 直连及响应字段保留。
3. **明确兼容演进规则**：必需字段、JSON 类型和关键枚举保持稳定，同时允许新增可选响应字段；接口变化需同步共享 fixture、三层测试和 API 文档。

### 2026-06-21 v0.1.51

1. **建立离线 LLM fixture provider**：Python AI 服务支持通过显式测试环境变量加载严格 JSON fixture，无需 DeepSeek API key 或网络即可返回确定性文本与结构化响应。
2. **保持测试可观测性与严格失败**：离线调用继续记录 LLM、token 和 trace 计数；fixture 未匹配、多重匹配或 schema 非法时直接失败，不回退真实 API。
3. **覆盖代表性 Python 核心路径**：固定响应覆盖文本问答、研究计划、两阶段背景知识图谱和页面翻译，生产 DeepSeek 模式与现有 `/api` 契约保持不变。

### 2026-06-20 v0.1.50

1. **加入强制双阶段人工审查**：Deep Research 与 Agent 在计划生成和终稿生成后分别暂停，只有用户确认可编辑计划、论文范围、约束及风险核查结果后才继续或完成。
2. **持久化审查状态与风险标记**：任务快照新增 `humanReview`、`reviewRisks` 和两个等待状态，等待人工操作的任务可在服务重启后恢复，运行中断语义保持不变。
3. **打通全链路审批交互**：Python、Java `/api` 转发和前端统一支持四个 review 接口，前端等待审查时停止轮询并提供计划编辑、冲突/缺证据标记和审查备注。

### 2026-06-20 v0.1.49

1. **新增扫描件与低文本诊断**：上传时联合检查 PDF 文本层和 GROBID TEI 正文，返回稳定的 `parseStatus`；无 TEI 的扫描件仍可成功上传并保留阅读能力。
2. **补齐用户可见处理提示**：论文库新增“需 OCR”状态与筛选，篇章解构面板持续提示先执行 OCR 或更换文字版 PDF，并明确正文相关 AI 能力可能受限。
3. **保持兼容与安全边界**：Java 网关继续透明透传，旧 IndexedDB 中文状态无需迁移；本阶段不执行 OCR，也不调用外部 OCR 服务。

### 2026-06-20 v0.1.48

1. **建立复杂版式解析基线**：固定 5 篇典型 PDF、SHA-256 和人工标注页，新增可复现的 GROBID 与 PDF.js layout benchmark，并保存机器可读结果。
2. **量化现有解析失败点**：记录章节恢复、阅读顺序、公式/表格区域与翻译过滤指标，明确中文章节缺失、表格页列模式误判、区域漏检误检和公式残留。
3. **收紧候选集成结论**：确认 Infinity-Parser 是 layoutRL 方法的解析器；在官方代码、模型和许可证不可核验时标记为 `not_runnable`，继续保留现有 GROBID 生产链路。

### 2026-06-19 v0.1.47

1. **持久化背景知识图谱快照**：背景补课生成的规范化图谱按 `pdfId` 写入默认 SQLite 存储，并保留可选 Neo4j 镜像和存储失败降级状态。
2. **用有界图谱邻域辅助冲突核查**：Deep Research 与 Agent 的真实冲突会读取相关论文、来源和概念的一跳邻域，补充 provenance、置信度和来源覆盖说明；无图或无匹配时结构化降级。
3. **保持人工裁决边界**：研究报告明确图谱上下文不自动裁决冲突；内部新增严格只读、无网络的邻域查询工具，并兼容旧任务和旧客户端忽略新增字段。

### 2026-06-19 v0.1.46

1. **改造当前论文前置知识图谱**：背景补课改为概念发现与依赖判断两阶段生成，只使用当前论文骨架、正文片段和显式主题，不再从论文库混入其他论文。
2. **区分论文证据与模型推断**：概念节点和 prerequisite 边新增来源状态、置信度、理由与汇总覆盖率；关系判断失败时保留概念节点但不补造线性依赖边。
3. **补齐可信展示与扩展边界**：前端支持查看节点和边的来源徽标、理由和证据覆盖率；保留可选 Neo4j 镜像，并预留默认禁用的外部学术知识 provider。

### 2026-06-19 v0.1.45

1. **新增只读 MCP adapter 原型**：提供默认关闭的本机 `stdio` server，显式启用后仅映射论文骨架整理、当前论文检索和内部文献库检索，不新增 FastAPI 或 Java 路由。
2. **收紧 MCP 数据边界**：协议工具契约动态复用内部注册表，调用统一经过严格输入输出校验；禁止当前论文全量读取并限制检索数量和片段长度，内部异常以脱敏 tool error 返回。
3. **补齐运行与架构说明**：记录 MCP 启动开关、客户端配置、非目标和安全限制，并将前端显示版本同步到 `0.1.45`。

### 2026-06-19 v0.1.44

1. **强化内部工具契约**：7 个内部工具新增 SemVer、严格输入/输出 schema 和结构化安全范围；注册与调用阶段会拒绝非法契约、参数和输出。
2. **补齐 Agent 工具审计**：Agent 成功与 fallback 工具调用均记录工具版本和安全范围，并随现有 SQLite JSON 快照持久化，旧任务保持兼容。
3. **明确 MCP 前置边界**：补充只读 MCP adapter 计划与接口、架构、运行说明和约束文档；当前仍不启用 MCP server/client 或新增外部路由。

### 2026-06-18 v0.1.43

1. **新增双模式浏览器 smoke**：引入 Playwright Chromium，覆盖 PDF 上传、论文库打开、阅读面板切换、研读工作台，以及 Agent 项目创建、任务轮询、任务历史和证据展示。
2. **隔离端到端后端依赖**：浏览器测试通过 route mock 固定 Java 上传与 Python Agent 响应，不修改生产 API 行为，也无需启动 Docker、Java、Python 或真实模型服务。
3. **补齐运行入口与文档**：新增 `npm.cmd run test:e2e`、Playwright 配置、有效单页 PDF fixture 和本地运行说明。

### 2026-06-18 v0.1.42

1. **统一来源展示与降级行为**：聊天、批判阅读、背景补课、Deep Research 和 Agent 共用来源归一化模型及 `SourceChip/SourceList`；无页码或旧缓存来源可展开片段详情。
2. **打通 Agent 来源回原文**：Agent evidence、冲突候选和报告引用复用同一 `onJumpToSource` 路径，跨论文来源会恢复对应本地论文并进入阅读 IDE 定位页面。
3. **补齐 Agent 引用关联**：前端由现有 `evidenceItems` 和 `sourceIds` 派生冲突来源与报告来源，不改变后端 API 或持久化契约。

### 2026-06-18 v0.1.41

1. **清理前端 lint 技术债**：移除 App 和背景补课中的未使用回调与 prop，稳定 Agent 初始快照和论文选择依赖，避免无效 memo、重复 effect 依赖和未使用 catch 参数。
2. **保持翻译布局语义不变**：以字符码判断替代控制字符正则，等价整理数学公式匹配，并移除列布局函数的无效参数；新增控制字符、斜杠和方括号运算符回归覆盖。

### 2026-06-18 v0.1.40

1. **补齐阅读产物沉淀入口**：全景翻译支持保存当前页译文，篇章解构支持按单章节保存摘要，并保留当前论文、页码或章节 metadata。
2. **补齐 Agent 产物沉淀入口**：Agent 报告草稿、跨论文对比表和单条关键证据可加入当前论文工作台；卡片保留项目、任务及适用的来源论文、来源片段、页码和章节标识。
3. **保持旧工作台兼容**：artifact 模型新增 `pdfId/sourceId/taskId/projectId` 可选字段及五类纯函数构建器，旧卡片缺少新字段时继续按空值归一化显示。

### 2026-06-17 20:10 v0.1.39

1. **收口阅读 IDE 到 Agent 的下一步建议**：阅读 IDE 右侧推荐下一步从单个 primary/secondary 动作升级为 2-3 个建议，覆盖继续单论文阅读、发起 Deep Research 和进入 Agent 研究。
2. **抽出前端工作流建议模型**：新增 `readingWorkflowModel.js`，按当前 PDF、活动面板、解析状态、Deep Research 状态、工作台沉淀数量和 `pdfId` 生成建议；Agent 建议只切换模式，不自动创建项目或任务。

### 2026-06-17 19:35 v0.1.38

1. **完成项目级 Agent 任务历史接口**：新增 `GET /api/agent-projects/{projectId}/tasks`，Python 按 `updatedAt` 倒序返回完整 Agent task 快照并支持 `limit`，Java 网关同步转发该接口。
2. **前端改为服务端历史优先恢复**：Agent 工作区进入、切换或刷新项目时优先读取服务端任务历史，本地 `tasksByProjectId` 继续作为旧接口、离线或临时失败 fallback。
3. **补齐文档和约束**：更新 `API.md`、`README.md`、`ARCHITECTURE.md`、`docs/CONSTRAINTS.md`、Agent 相关计划文档、`go3.md` 和前端版本号到 `0.1.38`。

### 2026-06-17 14:48 v0.1.37

1. **持久化 Agent 工作区状态**：Python AI 服务新增 Agent SQLite 快照，保存项目、任务和事件摘要；默认数据库为 `ai-service-python/data/agent_state.sqlite3`，测试或隔离运行可用 `AGENT_STATE_DB_PATH` 覆盖。
2. **恢复项目和 latest task**：Agent 项目、论文列表、latest task 指针、终态任务输出和时间线事件可在服务重启后恢复；删除项目会同步清理该项目任务和事件摘要。
3. **明确中断任务语义**：服务重启前仍在 `running/pending` 的 Agent 任务会恢复为 `failed`、`stage=done`、`progress=1.0`，并记录 `task_expired` 事件和清晰错误信息；本次不新增项目级任务历史列表接口。
4. **补充验证与文档**：新增 Agent 持久化单测，更新 `API.md`、`README.md`、`ARCHITECTURE.md`、`docs/AI_AGENT_PANEL_UPDATE_PLAN.md`、`docs/CONSTRAINTS.md` 和前端版本号到 `0.1.37`。

### 2026-06-17 14:17 v0.1.36

1. **Agent 新建项目改为论文库多选**：左侧 Create 区域移除手填论文 ID 文本框，改为展示已选论文、从论文库搜索添加论文，并支持从草稿中移除已选论文。
2. **调整默认论文选择规则**：进入 Agent 研究时仅在当前打开论文存在于论文库时默认选中该论文；不再默认把论文库全量论文加入新项目草稿，仍允许创建空项目。
3. **保持接口契约不变**：创建项目继续发送 `{ title, goal, paperIds }` 到现有 Agent 项目接口，不新增后端 API 或字段。

### 2026-06-17 14:00 v0.1.35

1. **抽出 Deep Research 编排边界**：新增 `research_planner.py`、`research_executor.py` 和 `research_aggregator.py`，将单论文 Deep Research 的计划生成、子问题执行、冲突检测、报告综合和 JUDGE trace 汇总从任务生命周期服务中拆出；`research_task_service.py` 继续保留任务创建、轮询、取消和 SQLite 快照职责。
2. **抽出 Agent 编排边界**：新增 `agent_orchestrator.py`，承接 Agent 计划项生成、工具调用摘要、证据聚合、对比表、冲突候选、开放问题和报告草稿综合；`agent_project_service.py` 继续负责项目/任务状态、异步执行、取消和 trace 包裹。
3. **保持接口与运行方式不变**：本次不新增 API、不改变 `/api/research-tasks*` 和 `/api/agent-*` 请求响应字段、不改变数据库 schema 或启动命令；Agent 项目/任务仍是进程内存状态，项目级任务历史接口仍留待后续 P1-12/P1-13。
4. **同步文档**：更新 `API.md`、`README.md`、`ARCHITECTURE.md`、Agent 相关计划文档和前端版本号到 `0.1.35`。

### 2026-06-16 20:55 v0.1.34

1. **新增 Agent 项目删除能力**：Agent 研究区左侧项目卡片右上角新增删除按钮，点击后确认并调用真实 `DELETE /api/agent-projects/{projectId}`，删除后项目刷新不会恢复。
2. **保持项目编号单调递增**：前端 Agent 快照新增 `nextProjectNumber`，旧快照会按现有 `Agent 项目 N` 推导初始编号；删除项目不会重命名现有项目，也不会回退后续默认编号。
3. **打通三层删除接口**：前端 `api.js` 新增 `deleteAgentProject()`；Java 网关新增 `/api/agent-projects/{projectId}` DELETE 转发；Python 服务新增项目删除逻辑并同步清理关联 Agent 任务，异步 worker 可容忍项目或任务被删除。
4. **同步文档与测试**：更新 `API.md`、`README.md`、`docs/CONSTRAINTS.md` 和前端版本号到 `0.1.34`；新增前端模型/API、Python Agent 服务、Java controller/service 覆盖。

### 2026-06-16 20:30 v0.1.33

1. **补齐 Agent 工作区夜间模式覆盖**：新增 Agent 专用主题语义样式，替换三栏工作区、折叠栏、任务历史、输入区、工具调用、证据卡片、任务摘要和结果区中的浅色硬编码类，使其跟随全局 `html[data-theme]` 明暗主题变量切换。
2. **修复顶部模式切换按钮暗色显示**：将“阅读 IDE / Agent 研究”分段按钮改为 theme-aware 控件，避免暗色模式下仍使用固定浅色背景和边框。
3. **补充主题防回归测试**：新增 `agentWorkspaceTheme.test.js` 并接入前端 `npm.cmd test`，防止 Agent 组件和顶部模式切换重新引入浅色专属类。

### 2026-06-14 22:30 v0.1.32

1. **Agent 面板升级为可用的项目工作区**：将原本偏原型的一体化面板拆分为多个子组件和模型/存储辅助文件，包括 `AgentWorkspace`、主区 sections、侧栏 sections、证据 sections、UI 归一化和本地快照逻辑。
2. **Agent 项目和任务 API 完成前端接入**：新增项目创建、项目列表、项目切换、论文挂载、任务创建、任务轮询、任务取消和 trace 查询等真实请求。面板现在调用 Python Agent API，不再依赖 mock 数据。
3. **修复本地 Agent 404 联调路径**：Agent 请求默认通过 `VITE_AGENT_API_BASE_URL` 指向 `http://localhost:8000/api`；阅读 IDE 继续使用 `VITE_API_BASE_URL=http://localhost:8081/api`。Python CORS 已允许本地 Vite 前端直接访问 Agent 接口。
4. **新增 Agent 异步执行态**：Agent 任务按 `planning -> retrieving -> synthesizing -> done` 暴露阶段进度，并通过轮询更新事件时间线、计划项、工具调用、证据片段、对比表、冲突候选和开放问题。
5. **按项目保留 Agent 任务历史**：前端新增 `tasksByProjectId`，切换项目时恢复对应任务列表和当前任务，避免新任务覆盖旧对话或旧结果。
6. **优化 Agent 结果区可读性**：最终报告草稿不再只截断展示前几个 section，主工作区和证据区更清晰地展示研究时间线、对比区、冲突、证据和草稿输出。
7. **增强 Agent 结论生成**：`agent_project_service.py` 现在根据证据密度、论文支持画像、共同主题、冲突候选和开放问题生成报告草稿，并包含 `## Current Conclusion`，不再只是通用占位文本。
8. **同步核心文档**：刷新 `API.md`、`README.md` 和 `ARCHITECTURE.md`，记录当前 Agent 运行路径、接口列表、前端任务历史行为、Python 直连策略、已知限制和验证状态。


### 2026-06-13 18:10 v0.1.31

1. **收拢背景补课偏好入口**：将背景补课中的大块“补课偏好”编辑区上移到工作区顶部悬停展开菜单，新增可复用的 `BackgroundReaderProfileEditor`，继续沿用现有 `backgroundReaderProfile / reader_profile` 状态与接口透传逻辑，不改动后端契约。
2. **精简背景补课正文布局**：重构 `BackgroundKnowledgePanel` 的前端展示，正文区不再重复占用空间编辑偏好，而是聚焦“先补什么 / 怎么补 / 看依据”三段内容流，仅保留本次补课依据摘要与自适应原因，减少阅读挤压感。
3. **移除 PDF 区冗余内置控件**：去掉 PDF 查看器 `default-layout` 自带的左侧侧边栏和底部工具栏展示，同时移除页面内额外挂载的 `PdfToolbar` 渲染，保留页码同步、划词解释、边注和片段问答等核心阅读交互，进一步收窄主阅读区干扰。

### 2026-06-13 17:20 v0.1.31

1. **重构背景补课用户建模方式**：将原本刚性的 `user_knowledge_level` 单字段控制升级为“读者画像 + 行为信号”联合驱动；前端新增 `reader_profile` 输入，支持填写当前熟悉度、希望补课深度、学习目标、已掌握概念与当前卡点，后端与 AI 服务会综合这些显式信息和近期提问/翻译/标注/笔记行为生成更贴近阅读现场的补课路径。
2. **保持旧接口与旧数据兼容**：Java 网关继续透明转发 `/api/background-knowledge`，Python 仍接受 `user_knowledge_level` 作为兼容回退字段；前端恢复 IndexedDB 历史数据时会优先读取新的 `reader_profile`，若只有旧字段则自动归一化到新的读者画像结构。
3. **补齐背景补课链路文档与测试**：同步更新 `API.md`、`ARCHITECTURE.md` 对新请求结构和自适应逻辑的说明，并扩展前端 API/model 测试与 Java 转发测试，覆盖 `reader_profile`、`behavior_signals` 的请求透传与快照归一化。

### 2026-06-13 14:58 v0.1.30

1. **完成 Deep Research 成本、延迟和预算计数器**：trace summary 稳定输出 `llmCalls/retrievalCalls/retryCount/truncationCount/estimatedInputTokens/estimatedOutputTokens`，LLM 调用按现有字符数规则估算输入/输出 token，Deep Research retry 与安全预算截断会写入 counters 并随任务快照持久化。
2. **增强前端 trace 可观测性**：`deepResearchPanelModel` 归一化固定预算字段并兼容旧 trace，`DeepResearchPanel` 将计数器展示为预算指标卡，同时在展开详情保留原始 counters 摘要。

### 2026-06-13 14:45 v0.1.29

1. **完成 Deep Research trace summary 持久化**：Python AI 服务将 Deep Research 终态的 public trace summary 写入研究任务 SQLite 快照，新增 `traceSummary` 兼容字段和旧库自动迁移；服务重启后 `GET /api/traces/{traceId}` 可从已完成任务快照恢复关键执行轨迹。
2. **保持 trace 安全边界和接口兼容**：持久化内容复用 `trace_service` 的脱敏、裁剪和 public summary 规则，不保存完整 prompt、论文全文、headers 或 API key；Java `/api/traces/{traceId}` 与前端调用路径不变，普通短请求 trace 仍为进程内临时摘要。

### 2026-06-13 14:20 v0.1.28

1. **完成 Deep Research 跨源冲突检测 MVP**：`research_task_service.py` 在综合阶段前基于 `findings[*].sources` 做规则型冲突扫描，生成任务级 `conflicts`，覆盖同一指标数值差异和同一主题正反结论，不调用额外 LLM、不自动裁决哪一方正确。
2. **增强报告、快照和前端核查展示**：研究报告新增“证据冲突/需人工核查”章节；SQLite 任务快照持久化 `conflicts` 并兼容旧库迁移；`deepResearchPanelModel` 归一化冲突来源，`DeepResearchPanel` 在 Findings 与报告之间展示冲突卡片和可用的跳回原文入口。

### 2026-06-13 09:55 v0.1.27

1. **完成 Deep Research 最小动态重规划**：`research_task_service.py` 将任务 `plan` 兼容升级为对象型计划项，初始子问题记录 `kind/status`；当某个 finding 最终 `verdict=INCORRECT` 且仍有 `missingAspects` 时，每个任务最多追加并执行 1 个 `follow_up` 子问题。
2. **增强 follow-up 溯源与前端计划展示**：follow-up finding 记录 `isFollowUp/followUpOf/sourceMissingAspects`，trace summary 新增 `followUpCount`；`deepResearchPanelModel` 归一化 `planItems` 并兼容旧字符串 plan，`DeepResearchPanel` 在计划区展示 follow-up 来源、缺失点和状态。

### 2026-06-12 10:45 v0.1.26

1. **完成深度研究 JUDGE 结构化效用评分**：`judge_evidence_quality()` 兼容新增 `judgeScore`、`coverage` 和 `retryReason`，分数来自 verdict、confidence、关键词覆盖、证据数量和来源类型，不引入新模型训练。
2. **增强 deep research finding 与 trace 可观测性**：每条 finding 写入 JUDGE 分、证据覆盖、缺失点和 retry 原因；judge trace step 记录 `decision=stop/try_library/retry`，完成 trace 汇总 `averageJudgeScore/retryFindingCount/insufficientFindingCount`。

### 2026-06-12 10:26 v0.1.25

1. **完成批判阅读引用网络真实化**：Python `/api/deep-analysis` 成功响应新增可选 `citationGraph`，当前没有真实引用图时明确返回 `null`，不生成、不推断、不模拟 citation network。
2. **移除前端固定模拟关系图**：`CriticalAnalysisPanel` 删除 `fallbackNetworkData`，改为只在有效 `citationGraph.nodes/links` 存在时渲染 `ForceGraph`；无真实图时展示“暂无引用网络”空态。

### 2026-06-12 10:12 v0.1.24

1. **完成表格/数值证据候选定位**：批判阅读 claims 兼容新增 `numericVerificationStatus`、`numericEvidenceCandidates` 和顶层 `numericEvidenceSummary`，基于同次 `rag_sources` 中的 Table/Figure 文本、指标名和百分比做规则型候选定位，避免生成不可追溯来源。
2. **增强前端主张证据卡片**：`criticalAnalysisData` 归一化数值候选、页码与跳转元数据，`CriticalAnalysisPanel` 在主张-证据校验区展示候选表图/数值片段，并明确提示候选证据不足以自动验证。

### 2026-06-12 10:10 v0.1.23

1. **完成论点-证据验证 MVP 评分规则**：Python 批判阅读响应新增规则型 `contributionScore`、`riskScore` 和 `noveltyDimensions`，分数来自 claims 支撑率、缺失证据、夸大风险以及方法/实验轴证据覆盖，不引入模型训练或微调。
2. **替换前端临时多维评分**：`criticalAnalysisData` 优先使用后端评分字段，`CriticalAnalysisPanel` 在图表 tooltip、维度卡片和 claim 卡片中展示评分依据与缺失证据；旧响应缺少新字段时继续兼容展示。
3. **同步任务与接口文档**：`go3.md` 不再要求新建或恢复 `docs/CONSTRAINTS.md`，接口字段同步记录到 `API.md`，README 补充批判阅读规则评分说明。

### 2026-06-10 10:20 v0.1.22

1. **恢复详情展开去重显示逻辑**：重新修复 `frontend/src/components/InsightCard.jsx`，当卡片展开完整详情时自动隐藏原先的简版摘要与要点，避免问答、深度研究、背景补课等复用卡片在展开后出现上下重复内容。
2. **恢复并重构背景补课面板**：重新整理 `frontend/src/components/BackgroundKnowledgePanel.jsx`，修复 Git 冲突回退后出现的固定文案反复显示、学习路径信息重复、以及“前置于”表述不自然的问题；`先补什么 / 怎么补 / 看依据` 三个视图重新回到分步展示逻辑。
3. **保留依据跳回原文能力**：在恢复背景补课模块时继续兼容现有 `rag_sources` 定位信息，保留来源片段的“跳回原文”入口，不改动后端接口字段，仅在前端做归一化与展示恢复。

### 2026-06-10 09:40 v0.1.21

1. **完成 Evidence Item 元数据统一**：`smart_chunker` 和 `LiteratureRAG.add_sections_to_db()` 会把新解析论文 section 的 `id/pageIndex/page/section` 传播到 chunk 与 Chroma metadata，`evidence_service` 统一输出 `sourceId/sourceType/text/pageIndex/sectionId/chunkIndex/pdfId/metadata/similarity/score`，并用 `pdfId + chunkIndex` 生成更稳定的 fallback `sourceId`。
2. **增强跨面板来源跳回原文**：聊天引用、批判阅读证据、背景补课来源和深度研究 findings 会保留页码与章节锚点；前端只有在 evidence item 存在有效 `pageIndex` 时显示“跳回原文 p.N”，旧索引或无页码来源继续降级为片段预览。
3. **扩展深度研究 finding 来源**：`task.findings[*]` 保留既有 `sourceIds`，并兼容新增 `sources`，用于携带同次检索使用的规范化 evidence items，不改变现有 Java `/api` 路由或必填请求字段。

### 2026-06-10 09:30 v0.1.20

1. **完成翻译服务旧代码清理**：删除 `services/chat_service.py` 中 `translate_page()` 直接委派到 `page_translation_service.translate_page()` 后的不可达旧实现，避免同一逐页翻译逻辑在两个服务文件中重复维护。
2. **清理旧翻译 helper 与导入**：移除 `chat_service.py` 中仅服务不可达旧分支的 `_trim_page_text`、`_trim_translation_reference`、`_call_translation_with_timeout`、`ThreadPoolExecutor`、`FuturesTimeoutError` 和 `get_translation_llm` 引用；真实 overlay/plain 翻译逻辑仍由 `page_translation_service.py` 负责。
3. **保持接口行为不变**：不修改 Python `/api/translate-page` 路由、Java `/api/translate-page` 转发、前端请求字段或逐页翻译响应结构。

### 2026-06-09 23:40 v0.1.19

1. **完成论文阅读工作流前端重构**：将原本偏功能堆叠的界面重新组织为“浅读解构 - 深度探究 - 知识内化”的连续阅读流程，在 `frontend/src/App.jsx` 中补齐阶段导航、当前研读上下文、推荐下一步动作与顶部辅助导航折叠逻辑，强化不同功能之间的串联关系。
2. **重构右侧核心功能页交互**：重新设计 `ChatPanel`、`PaperAnalysis`、`CriticalAnalysisPanel`、`BackgroundKnowledgePanel`、`SocraticQuestionsPanel`、`DeepResearchPanel` 的信息节奏与展示层级，把后端一次性返回的大块内容拆成更适合逐步阅读与参与的前端交互，增强用户输入、AI 输出和系统提示之间的区分度，并优化长耗时任务下的等待反馈。
3. **优化论文库与进度表达逻辑**：重构 `LibrarySidebar`，把原本仅基于页码的“阅读进度”升级为更严谨的“研读完成度”，综合页码覆盖、篇章解构、问答、翻译、背景补课、批判阅读、引导学习、深度研究、笔记与工作台卡片等多维信号；新增 `frontend/src/utils/studyProgress.js` 负责计算与兼容旧本地数据。
4. **重做底部工作台与成果导出能力**：将 `BottomWorkbench` 从简单的卡片堆叠区重构为“总览 / 整理卡片 / 复盘边注 / 成果导出”四视图工作台，采用左侧列表、右侧检视器的整理模式，并新增 `frontend/src/utils/workbenchExport.js`，支持将当前论文成果导出为 Markdown、JSON 与纯文本，便于汇报、归档与二次加工。
5. **补齐兼容性处理与文档沉淀**：在不修改后端接口的前提下完成本轮前端适配，兼容旧版 IndexedDB 本地数据与当前接口结构；同步维护 `docs/PAPER_READING_WORKFLOW_FRONTEND_SPEC.md`、`docs/FRONTEND_FINAL_COMPATIBILITY_REPORT.md`、`docs/FRONTEND_DAILY_UPDATE_2026-06-09.md`

### 2026-06-07 21:10 v0.1.18

1. **完成版本对齐**：将 `frontend/VERSION` 与 README 当前版本同步到 `0.1.18`，消除版本号仍停留在 `0.1.6`、CHANGELOG 已到 `v0.1.17` 的不一致。
2. **修正深度研究持久化语义**：在约束文档中保留早期内存任务规则的历史说明，并明确当前有效契约已被 SQLite 快照、`/api/research-tasks/latest?pdfId=...` 恢复和重启前运行任务失败标记覆盖。
3. **对齐 Docker 与启动说明**：更新 `启动服务.md` 的 `docker compose` 命令、`research_task_data` 快照 volume 说明，并修正 `docker-compose.yml` 中误导性的 `uvicorn --reload` 注释；Python Dockerfile 当前默认不启用 reload。
4. **刷新演示与测试基线**：`docs/DEMO_CHECKLIST.md` 新增 2026-06-07 当前基线，保留 2026-05-20 API smoke 为历史记录，不把未重新执行的 Docker/API 全链路写成 PASS。
5. **验证结果**：已通过 `npm.cmd test`（13 个前端 smoke/模型测试入口）、`npm.cmd run build`（通过，保留 Vite 已知警告）、`python -m pytest tests -q`（133 passed）和 `.\mvnw.cmd test`（30 tests passed，保留 Mockito 动态 agent 警告）。未重新执行 Docker Compose 启动或固定 PDF 全链路 API smoke。

### 2026-06-07 20:30 v0.1.17

1. **修复 HybridRetriever BM25 索引刷新**：新增 `invalidate_hybrid_cache()`，让新增论文 chunks 写入 Chroma 成功后清理旧 `_hybrid` 缓存，下一次混合检索会重建 BM25 文档索引。
2. **保持 RAG 对外契约不变**：不调整 `/api/rag/add-literature`、`/api/rag/retrieve`、Java 网关或前端调用字段；空 chunks 入库仍返回 0 且不触发缓存失效。
3. **补齐回归测试**：新增测试覆盖 hybrid 缓存失效不影响 `_rag`、失效后重建 retriever 可读取新文档，以及 `LiteratureRAG.add_sections_to_db()` 成功写入后触发失效；已通过 `python -m pytest tests -q`（133 passed）。未覆盖真实 Chroma 并发检索窗口，当前行为为后续请求重建新索引。

### 2026-06-05 20:37 v0.1.16

1. **修复 Python 文献库入库接口**：为真实 `LiteratureRAG` 补齐 `get_db_stats()`，避免 `/api/rag/add-literature` 成功入库后因统计方法缺失返回 500。
2. **保持 RAG 入库响应兼容**：接口继续返回 `status`、`message`、`chunk_num` 与 `total_chunks`；`DummyRAG` fallback 仍返回 0 chunks，不改变旧语义。
3. **补齐回归测试与约束文档**：新增 `test_rag_service.py` 覆盖成功入库、RAG 不可用 fallback 和真实统计方法；同步 `docs/CONSTRAINTS.md` 记录 `total_chunks` 语义。

### 2026-06-05 08:50 v0.1.15

1. **新增深度研究 brief preview**：新增 `POST /api/research-tasks/brief-preview` 三层链路，在创建长任务前生成研究范围、默认假设、建议子问题和可选澄清问题。
2. **支持补充约束后启动研究**：深度研究面板新增两阶段启动体验，用户可先接受默认 brief，也可补充研究边界后再创建任务；旧的直接启动流程继续保留。
3. **保持任务创建兼容**：`POST /api/research-tasks` 兼容新增可选 `userConstraints` 与 `briefPreview`，旧请求不传新增字段时仍按原流程创建任务。
4. **补齐测试与文档**：新增 Python brief preview 服务测试、Java 网关转发测试、前端 API 与模型归一化测试，并同步 README 与 `docs/CONSTRAINTS.md`。

### 2026-06-04 10:45 v0.1.14

1. **新增 trace 只读查询链路**：Python 新增 `GET /api/traces/{traceId}` 脱敏 summary，Java 同步以 `/api/traces/{traceId}` 转发，trace 不存在时返回兼容式 `404` 错误体。
2. **收紧 trace 排障暴露边界**：查询结果只返回限定 summary 字段，并过滤 headers、API Key、prompt、系统提示词和论文全文类字段；长列表和步骤信息会裁剪。
3. **增强深度研究排障面板**：Deep Research 面板始终显示 `traceId`，并仅在 Vite 开发模式下展示可展开的 trace 状态、耗时、计数器、请求/响应摘要和步骤列表。
4. **补齐三层测试覆盖**：新增 Python trace summary/路由测试、Java 网关转发测试、前端 API 与 trace 归一化测试，并同步 `docs/CONSTRAINTS.md`。

### 2026-06-03 21:25 v0.1.13

1. **新增背景知识前置依赖边**：`/api/background-knowledge` 成功响应兼容新增 `graph.edges`，使用 `prerequisite` 表达 `source` 是 `target` 的前置知识。
2. **收紧依赖边证据边界**：前置边只引用同次响应中的 `graph.nodes[*].id` 和 `rag_sources[*].sourceId`，自动过滤自环、悬空节点、重复边和伪来源。
3. **增强学习路径排序与兼容**：前端背景补课面板会按前置依赖边排序学习路径，并在旧响应、坏边或环形依赖下稳定降级为原顺序。
4. **补齐回归测试与文档**：新增 Python `graph.edges` 归一化测试和前端依赖排序测试，并同步 README 与 `docs/CONSTRAINTS.md`。

### 2026-06-03 20:40 v0.1.12

1. **新增批判阅读论点-证据验证**：`/api/deep-analysis` 成功响应兼容新增 `claims`，提取作者核心主张并输出 `SUPPORTED`、`PARTIAL`、`UNSUPPORTED` 支撑度。
2. **收紧证据引用边界**：每条 claim 的 `evidenceSourceIds` 只引用同次响应 `rag_sources` 中的 `sourceId`；证据不足时返回缺失证据说明，不生成伪引用。
3. **增强前端批判阅读展示**：批判阅读面板新增紧凑的“论点-证据验证”区块，展示主张、支撑度、理由、缺失证据和来源片段。
4. **补齐回归测试与接口文档**：新增 Python claim 支撑度与响应测试，扩展前端数据适配测试和 Java 透传测试，并同步 README 与 `docs/CONSTRAINTS.md`。

### 2026-06-01 20:30 v0.1.11

1. **新增深度研究任务持久化**：Python AI 服务使用标准库 SQLite 保存任务快照，覆盖任务 ID、trace ID、状态、阶段、进度、问题、论文 ID、计划、findings、报告、错误和创建/更新时间。
2. **支持按论文恢复最近任务**：新增兼容式 `GET /api/research-tasks/latest?pdfId=...`，Java 网关转发到 Python，前端刷新后可按当前论文恢复最近一个深度研究快照。
3. **明确服务重启语义**：已结束任务可从快照恢复；服务重启前仍在运行或等待的任务恢复为 `failed`，并提示用户重新发起，避免误判任务仍在后台执行。
4. **补齐持久化验证**：新增 Python SQLite 快照、重启恢复和 latest 查询测试，新增 Java 转发/Controller 测试，新增前端 API 与任务模型兼容测试。
5. **更新运行与接口文档**：Docker Compose 增加 `research_task_data` volume 和 `RESEARCH_TASK_DB_PATH`，README 与 `docs/CONSTRAINTS.md` 同步记录持久化路径、字段和接口契约。

### 2026-05-29 20:30 v0.1.10

1. **增强聊天证据引用展示**：`/api/chat` 响应新增兼容式 `sentenceSourceMap`，按回答关键句绑定同次 `rag_sources` 中的 `sourceId`，前端聊天卡片可展开查看引用片段。
2. **增强批判阅读结论引用**：批判阅读结果新增字段级引用映射，覆盖作者主张、证据化贡献、弱点、夸大风险、缺失证据和综合结论等字段。
3. **补齐引用兼容测试**：新增 Python 证据引用与响应测试，新增前端引用归一化测试，并扩展批判阅读数据适配测试。
4. **更新接口约束**：`docs/CONSTRAINTS.md` 记录 `sentenceSourceMap` 的字段形态、兼容语义和 sourceId 约束。

### 2026-05-25 20:30 v0.1.9

1. **补齐复杂 PDF 解析回归集**：扩展目录抽取测试，覆盖双栏小标题顺序、公式/单位/页脚噪声过滤和正文句子不误提为标题。
2. **补齐逐页翻译前端回归集**：扩展翻译布局与请求测试，覆盖双栏阅读顺序、图表区域过滤、公式碎片过滤、算法伪代码过滤和正文保留。
3. **补齐逐页翻译服务回归集**：新增 Python 翻译服务测试，验证结构化 block 归一化、分批、缺失 block 回退和译文顺序保留。
4. **修复 PDF 行级目录候选排序**：`_build_pdf_heading_candidates` 返回前统一按既有几何排序，避免直接测试或调用时保留原始错序。
5. **更新验证说明**：README 新增复杂 PDF 解析与逐页翻译 targeted 回归命令。

### 2026-05-23 20:30 v0.1.8

1. **完成前端分阶段重构收口**：将主题、阅读工作区、论文会话、工件数据和聊天状态下沉到 `hooks/` 与 `services/`。
2. **统一右侧结果卡片与阅读现场交互**：新增 `InsightCard`，并把划词入口扩展为解释、翻译、拆解、批判和边注。
3. **完成底部工作台体系与本地资产链路**：新增 `BottomWorkbench`、`artifactModel` 和 IndexedDB 会话同步能力。
4. **完善工作台整理与信息层级**：支持泳道分组、原位编辑、来源回跳，并重构右侧功能区导航。
5. **收口抽屉交互与验证说明**：稳定底部工作台展开/收起交互，补充 smoke test；完整 build 的历史依赖风险仍需单独处理。

### 2026-05-20 17:02 v0.1.7

1. **新增全链路演示检查清单**：新增 `docs/DEMO_CHECKLIST.md`，固定使用仓库内 `Active RIS-Assisted Integrated Sensing and Communication Systems Joint Receive-Transmit Beamforming and Reflection Design.pdf` 作为演示 PDF，覆盖上传解析、问答、划词解释、逐页翻译、批判阅读、背景补课、苏格拉底学习和深度研究的可复现步骤。
2. **补齐演示启动与排障基线**：文档集中记录 Docker Compose 启动命令、服务就绪标准、日志检查命令、备用截图建议。
3. **记录当前真实联调结果**：当前环境通过 no-build recreate 恢复到 `backend_java=8081->8080` 的当前端口映射，固定 PDF 上传解析成功并完成问答、划词解释、逐页翻译、批判阅读、背景补课、苏格拉底学习和 deep research API smoke；同时记录 `docker compose up -d --build` 超时这一演示前风险。

### 2026-05-06 18:45 v0.1.6

1. **修复逐页翻译图文混排页漏译与噪声问题**：逐页翻译请求新增正文块清洗层，过滤图内标签、算法伪代码、页脚、公式编号、裸公式变量和 `d`、`f 1GHz` 等 PDF 文本层残片，避免非正文内容挤占翻译批次并扰乱版面。
2. **优化双栏论文阅读顺序**：当页面左栏上方存在大图或算法区域、右栏正文位置更靠上时，仍按左栏正文优先、右栏正文随后组织翻译块，修复右栏标题或公式残片先于左栏正文出现的问题。
3. **保留可读正文并清理公式残留**：对 `√The complex... η =`、`2 [5]. The target...` 等由公式抽取造成的混合行进行清洗，保留可翻译正文，剔除行首或行尾公式碎片。
4. **调整结构化翻译超时与回退策略**：含图页面不再强制退回纯文本翻译，结构化翻译改为更小批次并发请求；前端结构化等待时间提升到 `90s`，Python 结构化批次超时提升到 `60s`，纯文本兜底提升到 `90s`。
5. **补充回归验证**：新增前端布局测试覆盖双栏错序、图内文字、公式碎片、算法伪代码和第 4 页类似的正文保留场景；已通过 `npm.cmd run test`、`npm.cmd run build` 和真实第 2/4 页翻译接口验证。


### 2026-05-06 12:19 v0.1.5

1. **修复批判阅读 500 报错**：当当前论文缺少 RAG 全文索引时，Python 不再抛出普通 500，而是返回 `paper_not_indexed` / `rag_index_unavailable` 等结构化错误，Java 网关同步透传错误码与提示信息。
2. **修复 RAG 空索引误判成功**：PDF 解析完成但 RAG 入库为 `0 chunks` 时，现在会返回 `ragIndexed: false`、`ragChunkCount` 和 `ragErrorCode`，避免前端误认为论文可用于批判阅读。
3. **修复 RAG 初始化失败后的持久空状态**：RAG 初始化失败后不再永久缓存空实现，后续请求会重新尝试初始化，减少服务重启后索引一直为空的问题。
4. **修复 Chroma 持久化路径错位**：将 Chroma 数据库路径接入 `CHROMA_DB_PATH=/app/chroma_data`，使 Docker volume 中的 `chroma_data` 真正承载向量索引，降低重启后索引丢失概率。
5. **优化前端索引异常提示**：批判阅读失败时前端会展示明确中文原因，并把论文库状态更新为“索引异常”，不再只弹出泛化的 `Request failed with status code 500`。


### 2026-05-05 23:13 v0.1.4

1. **创建分级章节结构**：新增 Python 目录抽取层 `core/outline_extractor.py`，融合 GROBID TEI 标题、段落级候选和 PDF 行级候选，统一返回 `displayTitle`、`rawTitle`、`headingNumber`、`level`、`parentId`、`pageIndex`、`bbox`、`anchorY`、`source` 与 `confidence`。
2. **增强 IEEE/双栏论文目录识别**：支持罗马数字一级章节、A/B/C/D 字母小节、双栏阅读顺序重排和缺失父级推断，修复同页多个小标题漏识别、数字序号被吞和子标题全部变一级的问题。
3. **过滤异常目录候选**：针对 GROBID 和 PDF 文本层常见误判，过滤纯数字标题、公式变量片段、单位/坐标轴标签、页脚、编号贡献句等噪声，并规范化 PDF 连字以减少重复标题。
4. **前端篇章目录与篇章解构同步升级**：左侧目录和右侧“真实篇章结构”面板识别 `outlineVersion 1.4`，展示来源标签、补全数量、置信度提示，并提示旧缓存论文需要重新上传或重新解析。
5. **补充回归测试与文档**：新增 `tests.test_outline_extractor` 覆盖数字序号保留、同页小标题恢复、缺失父级补全、双栏排序、纯数字标题过滤、公式噪声过滤和 PDF 行级补全；README 补充目录抽取能力、验证命令和 Docker Hub 失败时的 `--no-build` 恢复方式。


### 2026-05-05 19:09 v0.1.0

> 本文件记录标题统一使用 `YYYY-MM-DD HH:mm vX.Y.Z` 格式；缺失精确版本的早期历史记录使用 `v0.0.0` 作为占位版本。


1. **新增前端版本号文件**：新增 `frontend/VERSION`，当前版本为 `0.1.0`；前端关于弹窗从该文件读取版本号，并显示当前模型名称。
2. **新增论文库大表格弹窗**：将论文库从侧边抽屉调整为居中的表格弹窗，展示标题、作者、解析状态、章节数、阅读进度、页码和更新时间。
3. **新增工作台式前端布局**：前端改为顶部工具栏、左侧论文导航、中间 PDF 阅读器、右侧 AI 功能区的三栏结构。
4. **新增可折叠左侧常驻栏**：左侧论文导航支持展开/收起，收起后保留关键图标入口。
5. **新增真实篇章目录树**：左侧目录优先读取 `paper_structure.sections`，支持多级层级、折叠展开、页码标记、搜索过滤、来源标记和当前章节高亮。
6. **新增真实论文结构字段**：Python GROBID 解析结果新增 `id`、`parentId`、`level`、`nestedLevel`、`headingNumber` 和 `pageIndex`，用于前端生成真实层级目录。
7. **新增阅读进度持久化**：前端根据 PDF 当前页和总页数计算阅读进度，并写回论文库记录。
8. **新增右侧功能标签滚轮交互**：鼠标悬停在右侧功能标签栏时，滚轮可横向滑动标签。
9. **后端上传响应增强**：上传论文后返回 `title` 和 `authors`，用于论文库表格展示。
10. **README 更新为当前架构说明**：补齐端口、版本号、环境变量、功能清单、验证命令、旧缓存论文重新解
## 历史记录

### 2026-04-24 20:30 v0.0.0
1. **精简全景翻译图片处理链路**：前端不再为全景翻译生成 PDF 页面截图、图片裁片或图表 gallery，旧缓存中的图片字段会被忽略；全景翻译继续只展示可提取正文的译文，图片、图表和表格不出现在右侧译文中。
2. **保留图片区域过滤能力**：`translationLayoutIndex.excludedZones` 继续用于过滤图表、表格和公式区域内的文本块，含图/表页仍优先走纯文本翻译回退，避免把图片区域误送入结构化翻译。

### 2026-04-22 20:30 v0.0.0
1. **增强苏格拉底引导学习证据质量**：`/api/socratic-session/start` 与 `/api/socratic-session/answer` 继续保持固定 5 题流程，但每一题的生成与回答评估现在都会优先参考当前论文证据，不再默认扩展到文献库检索。
2. **补齐引导学习结构化评估字段**：Socratic 回答评估新增 `coveredAspects`、`missingAspects` 与 `evidenceQuality`，用于区分“用户理解薄弱”和“当前论文证据不足/部分相关”两类情况。
3. **新增最终回读建议与旧 session 兼容**：引导学习完成后可返回 `reviewSuggestions`，总结中会给出建议回读章节、概念或证据点；前端 IndexedDB 会话模型同步兼容新字段，并继续兼容旧缓存。
4. **新增深度研究任务 API 雏形**：打通 Java `/api/research-tasks` 与 Python `/api/research-tasks` 创建、查询、取消三条链路，先提供可控的后端任务 API，不要求前端完整面板同时上线。
5. **补齐深度研究任务状态机与结构化 findings**：Python 侧新增内存任务状态机，任务固定执行“brief -> 3-5 个子问题 -> 当前论文优先检索 -> 证据 judge -> 最多一次重试 -> 中文 Markdown 报告”，响应统一返回嵌套 `task` 快照与结构化 `findings`。
6. **增强深度研究链路测试与文档约束**：前端 `api.js` 新增 research task 调用方法，Python 与 Java 同步补基础测试，并在 README 与约束文档中明确任务状态、取消语义、内存存储限制和当前论文优先的检索边界。
7. **新增深度研究前端最小面板**：前端导航栏新增“深度研究”页签，右侧面板支持输入研究问题、创建任务、轮询查看阶段与进度、手动刷新、取消任务，并展示任务 `plan`、结构化 `findings` 与最终 Markdown 报告。
8. **补齐深度研究前端会话内存边界**：deep research UI 状态按 `pdfId` 隔离，只保留在当前浏览器会话内存中；切换论文不会串状态，删除论文会同步清理对应任务状态，刷新页面或后端重启后则安全回到空态或提示任务已丢失。
9. **新增 deep research 前端 smoke test**：补充 `deepResearchPanelModel` 归一化与状态映射测试，并把新测试接入前端 `npm test` 链路，覆盖状态/阶段/证据判断标签、进度夹紧和缺省字段兼容。
10. **新增统一轻量 trace 机制**：Python AI 服务补齐 `trace_service`，为聊天、划词解释、批判阅读、背景补课与深度研究任务统一记录阶段、耗时、检索次数、LLM 调用次数和错误摘要，并继续保持前端与 Java 请求链路不变。
11. **增强长任务异常/取消可观测性**：deep research 任务创建时会绑定稳定 `traceId`，成功、失败、取消三种终态都会保留对应 trace；聊天、批判阅读与背景补课成功响应也会兼容返回可选 `traceId`，便于后续排障。
12. **补齐 trace 脱敏边界与测试覆盖**：trace 只保留截断后的问题摘要、query 摘要、证据条数和阶段信息，不记录 API Key、完整 prompt、完整论文全文或完整用户全文；同步新增 trace 单测并扩展 chat/explain/analysis/background/research task 回归测试。
13. **新增共享提示注入防护层**：Python AI 服务新增 `safety_service`，把论文正文、`paperSkeleton`、`paperStructure`、页内上下文与 RAG 片段统一视为不可信资料，在进入 LLM 前做轻量注入检测、去指令化清洗、`UNTRUSTED PAPER/RAG CONTENT` 包装和上下文预算裁剪。
14. **增强 query/chat/background/critical/research 的权限边界**：query rewrite 与 chat planner 改为在固定 system 护栏下读取安全包装后的上下文；聊天、术语解释、背景补课、批判阅读与 deep research 规划都不会响应论文中的越权指令、密钥索取、system prompt 泄露、命令执行、联网搜索或工具/MCP 调用要求。
15. **收紧深度研究规划与安全测试**：deep research 继续保持确定性报告生成，同时显式收口 `3-5` 个子问题、最多 `1` 次自动重试和 `current_paper / library` 检索白名单；新增 `test_safety_service.py` 并扩展 chat/explain/background/analysis/research task 回归测试，覆盖恶意论文片段不会改变助手行为。
16. **新增 Python 内部工具注册层**：AI 服务新增非公开 `tool_registry`，统一注册 `retrieve_current_paper`、`retrieve_library`、`read_paper_skeleton`、`judge_evidence`、`generate_background_graph`、`run_critical_analysis` 与 `translate_page` 七类既有能力，为后续 MCP 适配预留稳定边界。
17. **调整深度研究优先经由工具层调用**：deep research 现通过内部工具注册层调度当前论文检索、文献库检索、论文骨架读取与证据 judge，继续保持“当前论文优先、必要时补充文献库、最多 1 次自动重试”的原有行为，不改变 `/api/research-tasks` 对外契约。
18. **补齐内部工具注册测试覆盖**：新增 `test_tool_registry.py`，覆盖工具注册、工具列举、成功调用、未知工具错误，以及背景补课、批判阅读、逐页翻译等已注册能力的轻量转发测试；同步扩展 deep research 测试以确认关键路径已切到注册层。
19. **新增 MCP 适配可行性文档**：新增 `docs/MCP_ADAPTER_PLAN.md`，基于现有 `tool_registry`、deep research、安全与 trace 能力整理未来 MCP Tools / Resources / Prompts 的映射建议、非目标和三阶段迁移路线；同时同步 README 与开发约束文档，明确当前阶段仍不引入 MCP 运行时、外部接口或 SDK 依赖。

### 2026-04-21 20:30 v0.0.0
1. **聊天升级为轻量 Agentic RAG**：`/api/chat` 改为显式执行“意图识别 -> 查询计划 -> 检索 -> 证据 judge -> 最多一次重试 -> 回答”的轻量流程，同时保持现有请求体兼容。
2. **扩展结构化聊天查询计划**：新增聊天专用 query planner。
3. **增强当前论文优先与证据边界**：聊天优先检索当前论文，证据不足时按计划补充文献库，并在回答中明确区分证据充足、部分相关和不足三类情况。
4. **补齐聊天模块测试**：新增聊天规划、当前论文问答、文献库补充、证据不足重试和历史上下文等 Python 回归测试。
5. **批判阅读升级为全文证据化分析**：`/api/deep-analysis` 不再只截取前 4000 字，而是基于当前论文全文 chunks 或临时分块内容，围绕贡献、方法、实验和局限四个分析轴进行证据检索、judge 与最多一次重试。
6. **扩展结构化批判阅读返回**：新增 `evidence_based_contributions`、`weaknesses`、`overclaim_risks`、`missing_evidence` 与统一 `rag_sources`，并保持旧字段兼容。
7. **增强批判阅读前端面板**：`CriticalAnalysisPanel` 继续沿用原有概览和图表布局，同时新增紧凑的薄弱点、夸大风险、缺失证据和参考证据区块.
8. **深化背景补课图谱结构**：`/api/background-knowledge` 现在会对概念节点做轻量去重、稳定 `node id`、补齐节点 `stage`，并新增四段式 `learning_path_sections`，同时继续兼容旧 `learning_path`。
9. **增强背景补课证据覆盖信息**：背景补课响应新增 `confidence` 与 `sourceCoverage`，图谱节点会尽量绑定本次返回的 `rag_sources`，证据缺口则通过未覆盖节点显式暴露。
10. **补齐背景补课知识水平与前端展示**：背景补课面板新增 `入门 / 一般 / 进阶` 三档知识水平选择，缓存恢复时会回填最近一次结果，并在面板中展示四段式学习路径、证据覆盖和 Neo4j 持久化状态。
11. **尝试修复全景翻译图片页误判空**：含图片但仍能提取文字的页面不再被提前标记为“无可翻译内容”，过滤图片区后会自动回退到纯文本翻译，右侧继续展示可翻译文本的译文。
12. **收紧全景翻译图片页超时链路**：含图页现在优先走纯文本翻译，Python 端也会跳过大面积逐块补救，避免结构化翻译失败后长时间卡在 loading。
13. **修复全景翻译卡死 loading 状态**：恢复本地缓存时不再保留旧的 `loading` 页状态，前端也只会对真实在飞的请求维持 loading；结构化翻译超过短超时会自动中止并回退纯文本请求。

### 2026-04-20 20:30 v0.0.0
1. **完成基线审计**：确认前端测试与 lint、Python 测试目录、Java Maven 测试的当前运行状态，并记录前端 build 待查问题。
2. **隔离测试环境副作用**：Python 默认 pytest 仅收集 `tests/` 并忽略临时目录；Java 测试改用内存 H2，避免修改开发用 `academic_db.mv.db`。
3. **同步接口文档状态**：更新 README 与接口约束，移除聊天历史、批判性阅读等链路的过期“预留/Mock”描述。
4. **统一 RAG 证据结构**：新增 Python evidence 工具层，聊天、划词解释与背景补课统一返回结构稳定的 `rag_sources`，并补充证据归一化测试。
5. **增强查询重写与混合检索**：新增 Python query 工具层，聊天、划词解释与背景补课复用轻量学术查询重写，并在全局检索中保留向量与 BM25 结果。
6. **新增轻量证据质量判断**：聊天与划词解释接入 JUDGE/CRAG 启发式评估，证据不足时最多重试一次，并返回可选 `retrievalJudge`。

### 2026-04-11 20:30 v0.0.0
1. **新增背景补课图谱**：打通前端、Java 与 Python `/api/background-knowledge` 链路，基于当前论文 RAG 生成前置概念与学习路径；Neo4j 为可选持久化。
1. **优化全景翻译阅读顺序**：修复竖版双栏 PDF 文本串栏问题，统一横版和双栏论文的阅读流。
2. **增强译文渲染与测试**：改进译文页保真展示，并补充双栏、横版和跨栏内容的回归测试。
3. **修复主题图标**：恢复导航栏貔貅图标资源，避免日夜间主题下显示异常。
4. **打通动态术语解释真实链路**：PDF 划选首次解释改走 `/api/explain`，携带当前页上下文并优先基于当前论文 RAG 生成解释，同时统一“AI 解释”文案。

### 2026-04-10 20:30 v0.0.0
1. **重做全景翻译页面**：右侧改为纯中文译文页，不再显示英文 PDF 背景和原文预览。
2. **优化结构化排版与图表保留**：按阅读顺序渲染译文块，并在译文页保留原图、图表和表格裁图。
3. **补齐翻译状态兼容**：兼容旧缓存和新版页级数据，修复翻页、重试、刷新和切换论文时的状态同步。
4. **新增夜间模式**：加入全局明暗主题切换，统一右侧功能面板和 PDF 阅读器的暗色显示。

### 2026-04-09 20:30 v0.0.0
1. **优化 PDF 划词公式体验**：精简用户消息内容，提升公式识别、归一化和 KaTeX 渲染稳定性。
2. **简化 AI 公式解释回复**：去除恢复过程铺垫，让模型直接解释或翻译选区内容。
3. **修复划词浮层文案**：统一 PDF 划词按钮和弹窗中的中文显示。

### 2026-04-05 20:30 v0.0.0
1. **重构引导式学习**：改为 AI 提问、用户作答、AI 评估追问的会话式学习流程，并支持进度恢复。
2. **新增引导学习接口与界面**：前后端接入新的会话接口，重做学习面板和题卡展示。
3. **上线全景翻译真实链路**：支持按页提取 PDF 文本、调用翻译接口并缓存译文结果。
4. **补全数学公式显示**：完善 AI 对话、划词解释、批判分析、笔记等场景的 LaTeX/KaTeX 渲染和选区公式归一化。

### 2026-04-04 20:30 v0.0.0
1. **打通批判性阅读链路**：前端改为调用真实接口，Java 转发到 Python 分析服务并基于 RAG 内容生成结果。
2. **补齐聊天历史恢复**：新增聊天历史接口，并与前端 IndexedDB 缓存同步。
3. **重构 Python 服务结构**：拆分 `main.py`，按路由、服务、模型和 RAG 等模块整理代码。
4. **补测试并清理旧文件**：新增前后端与 Python 基础测试，删除未使用的组件、脚本和模块。
5. **修复引导式学习细节**：调整问题流程和多余按钮显示。

### 2026-04-03 20:30 v0.0.0
1. **AI 响应提速**：将底层向量模型更换为 130MB 轻量版，彻底解决了首次提问时的长延时和卡顿问题。
2. **加载机制优化**：新增模型持久化卷，模型仅需在首次启动时下载一次，后续开机即用。
3. **界面清爽化**：移除了 AI 消息气泡中的错位角标，删除了底部的冗余标签，对话视野更开阔。
4. **使用手册补全**：新增《启动服务.md》，详细说明了 Docker 部署步骤及日志查看方法。

### 2026-04-02 20:30 v0.0.0
1. **多论文库支持**：新增侧边栏“图书馆”功能，支持多份 PDF 文件的管理、切换与独立删除。
2. **数据存储升级**：使用浏览器本地存储 (IndexedDB) 隔离不同论文的对话和笔记，互不干扰。
3. **划词高亮持久化**：所有的划线解释记录会自动保存在 PDF 上，刷新或切换论文后依然存在。
4. **学术笔记收藏**：在对话气泡旁增加收藏按钮，支持一键将 Q&A 存入学术笔记库。
5. **异常反馈增强**：实现了 AI 回答的中止功能，并会在对话流中实时留下“回答已取消”的 Markdown 提示。

### 2026-04-01 20:30 v0.0.0
1. **全栈架构打通**：完成 Docker 容器化部署，整合 React 前端、Java 后端、Python AI 接口及 Grobid 解析引擎。
2. **智能解构功能**：实现 PDF 自动提取摘要、方法、结果等核心章节，并自动生成篇章总结。
3. **开发环境体验**：开启 Python 后端热重载，代码改动后实时生效，无需重新构建容器。
4. **基础交互构建**：支持 Markdown 格式渲染、对话删除、PDF 划词实时解释等基础学术分析功能。

### 2026-03-30 20:30 v0.0.0
1. **新增苏格拉底引导学习前后端链路**：前端新增 `SocraticQuestionsPanel`，从篇章解构 `paper_skeleton` 生成阅读进度驱动的问题；Java 增加 `/api/socratic-questions` 转发到 Python `/api/socratic-questions`，支持问题生成后直接回灌到聊天面板追问。
2. **增强 Python 服务健壮性与降级策略**：`HybridRetriever` 改为可选依赖（缺失 `rank-bm25` 时不阻塞服务启动），新增 `retrieve_hybrid_for_vector` 与向量检索回退路径，避免 RAG 初始化失败导致 `/api/chat`、引导学习等接口不可用。
3. **修复大模型 JSON 解析脆弱点**：新增 `parse_json_from_llm` 统一处理 fenced code、前后噪声与外层 JSON 截取；`paper_skeleton` 与 `paper_structure` 分开兜底，避免结构抽取失败污染篇章总结结果。

### 2026-03-25 20:30 v0.0.0
1. **重构早期 RAG 核心模块**：集中调整 `document_parser`、`smart_chunker`、`paper_structure_parser`、`hybrid_retriever`、`rag_vector_db` 与 `citation_gragh`，为后续“结构解析 + 混合检索 + 引用关系”链路打基础。
2. **补齐向量库本地资产**：同步 Chroma 持久化目录，保证本地检索实验可直接复现。

### 2026-03-14 20:30 v0.0.0
1. **打通真实聊天接口**：Python 新增 `/api/chat`（`ChatRequest`）并返回 `{ status, message }`；前端 `handleSendMessage` 从 mock 改为真实 `apiService.sendMessage` 调用并补齐错误回显。
2. **补齐术语解释参数映射**：Java `AiService.explainTerm` 增加请求转换，把前端 `{ text, pdfId, pageNumber, context }` 归一为 Python 期望的 `{ term, context }`，确保解释链路参数语义一致。

### 2026-03-13 20:30 v0.0.0
1. **修复联调稳定性问题**：围绕 Python `main.py` 多轮修复，并调整 Java `WebConfig`，改善本地跨端联调可用性。
2. **补充镜像与依赖源调整**：更新 Docker 与依赖配置，降低环境差异导致的构建失败概率。

### 2026-03-10 20:30 v0.0.0
1. **新增开发约束体系**：补齐 `.cursor/rules` 与 `docs/CONSTRAINTS.md`，明确 API 契约、模块职责和协作边界，作为后续接口打通与重构的基线。

### 2026-02-27 20:30 v0.0.0
1. **接入可落地 RAG 向量检索能力**：新增 `core/rag_vector_db.py`，引入 Chroma 本地向量库存储与检索，形成文献入库与召回的基础能力。
2. **扩展 RAG 接口与测试**：Python 补齐 `/api/rag/add-literature`、`/api/rag/retrieve` 相关逻辑并新增 `tests/test_rag.py`，验证入库、检索与基础统计流程。

### 2026-02-01 20:30 v0.0.0
1. **打通 Java 网关到 Python AI 服务**：新增 `AcademicController` 与 `AiService`，建立 `/api/upload`、`/api/explain`、`/api/chat` 转发链路，前端开始通过 Java 统一访问 AI 能力。
2. **升级 PDF 解构为真实解析流程**：Python `/api/analyze-pdf` 改为 GROBID + TEI 解析，使用 `BeautifulSoup` 提取章节并按关键词归类，采用单次批量 Prompt 生成 `paper_skeleton`，并加入 JSON 解析失败兜底与临时目录清理。
3. **新增篇章解构独立展示面板**：前端增加 `PaperAnalysis` 页面与 `deconstructStore` 持久化，上传论文后自动触发解构并切换到报告视图。
4. **预留全景翻译交互入口**：`PdfToolbar` 新增“全景翻译”开关，`PdfViewer` 增加 `TranslationOverlay` 视觉层与状态透传，为后续真实翻译链路预留 UI/状态框架。
5. **预留论文关系图展示位**：`CriticalAnalysisPanel` 引入 `react-force-graph-2d` 并新增论文关系网络卡片，当前以模拟网络数据展示，保留后端数据接入注释与接口预留点。

### 2026-01-31 20:30 v0.0.0
1. **实现前端会话级持久化恢复**：引入 `idb`，新增 `pdfStore`、`historyStore`、`analysisStore`、`notesStore`，并以 `isRestored` 防止初始化阶段空数据反写覆盖。
2. **新增学术笔记沉淀链路**：划词解释弹窗增加“存为笔记”，保存选区、页码与 AI 解释到 `notesStore`，右侧新增“学术笔记”页签统一查看。
3. **补齐批判分析持久化与模型迁移**：批判分析结果纳入本地存储恢复流程；Python 模型调用切换到阿里云百炼（`dashscope`）并同步调整依赖与环境变量约束。
4. **修复容器与依赖冲突问题**：持续修正 Dockerfile、requirements 与编排配置，提升服务启动稳定性。

### 2026-01-30 20:30 v0.0.0
1. **搭建 AI 核心能力雏形**：Python `main.py` 初步落地篇章解构、术语解释、背景补课、苏格拉底提问与深度分析接口，并引入自定义 `CustomDashScopeLLM` 适配 LangChain。
2. **上线批判阅读独立面板**：前端新增 `CriticalAnalysisPanel`，支持“结论摘要 + 多维度指标图表”展示，右侧面板支持在聊天与分析模式间切换。
3. **升级划词解释为窗内追问 + 聊天同步**：`PdfViewer` 引入解释弹窗 `ExplanationPopup`，支持局部追问、窗内历史与消息同步到右侧 ChatPanel，形成“局部阅读 + 全局对话”联动。
4. **补齐运行时环境配置**：集中修复版本冲突、锁定关键依赖并加入镜像源与 API Key 要求，降低首次部署门槛。

### 2026-01-29 20:30 v0.0.0
1. **首版接入 PDF 划词解释交互**：`highlightPlugin` + “AI 解释”浮层按钮接入 `PdfViewer`，选区内容可直接传递到聊天流。
2. **统一 AI 回复 Markdown 渲染**：`ChatPanel` 引入 `react-markdown`，替换纯文本展示，支持标题、强调、列表等基础学术表达格式。

### 2026-01-28 20:30 v0.0.0
1. **完成前端工程化基建**：初始化 Vite + React + Tailwind 前端工程，搭建 `Navbar`、`PdfViewer`、`ChatPanel`、`PdfToolbar` 基础布局与模块分层。
2. **预留后端通信抽象层**：新增 `services/api.js` 与 `usePdfFile` 等基础能力，先保证 UI 与交互骨架可运行，再逐步替换为真实后端调用。

### 2026-01-27 20:30 v0.0.0
1. **完成项目结构重组与多语言容器化起步**：重整仓库目录并初始化 Python、Java 服务与 `docker-compose` 编排，形成多服务协同基础。
2. **搭建 Java + Python 双引擎雏形**：建立 Spring Boot 后端骨架、Python 服务入口及各自 Dockerfile，为后续 API 聚合与 AI 能力接入铺路。
3. **补齐前端容器编排入口**：新增前端 Dockerfile 并更新总编排文件，三端（前端/Java/Python）协同开发环境初步可用。
