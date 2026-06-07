# 更新日志 (CHANGELOG)

本记录用于追踪学术 AI 助手的功能迭代与优化。

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
