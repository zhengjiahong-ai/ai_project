# MCP 适配可行性文档

> 本文档是未来迁移设计，不代表当前项目已经上线 MCP server、MCP client 或外部 MCP 接入能力。

## 目标与结论

当前 `ai_project` 已经完成模块 11 的内部工具注册层，Python AI 服务内存在稳定的 `tool_registry`，并且 deep research 已优先通过该层调度当前论文检索、文献库检索、论文骨架读取与证据 judge。基于这一现状，项目已经具备“未来做 MCP adapter”的最低工程基础，但**当前阶段不应直接引入 MCP 运行时**。

原因如下：

- 现有三层架构已经有明确边界：React 前端 -> Java `/api` 网关 -> Python `/api` AI 服务。
- 当前内部工具 schema、任务状态、资源暴露粒度和鉴权策略还没有稳定到适合直接对外开放。
- 项目已经明确把论文正文、RAG 片段、论文骨架等内容视为不可信输入；如果过早增加 MCP 暴露面，会放大提示注入、数据越权和预算失控风险。
- 当前最优路径不是“立即 MCP 化”，而是先把内部工具与安全边界稳定，再在 Python 服务侧做受控 adapter 实验。

因此，本文档的结论是：

- 当前阶段继续保留内部 `tool_registry` 作为唯一稳定起点。
- 未来如需接入 MCP，优先在 Python 服务内部或其旁路实现 adapter，不直接改写前端、Java 网关和现有 HTTP 契约。
- 任何 MCP 映射都必须继承现有 `safety_service`、`trace_service`、deep research 预算控制和检索 scope 白名单。

## 当前基线

### 已存在的内部工具

当前 `ai-service-python/services/tool_registry.py` 已注册以下 7 个内部工具：

| 内部工具 | 当前职责 | 当前使用情况 |
|----------|----------|--------------|
| `retrieve_current_paper` | 从当前已索引论文中检索或批量读取证据 | deep research 已调用 |
| `retrieve_library` | 从内部文献库中做混合检索 | deep research 已调用 |
| `read_paper_skeleton` | 把 `paperSkeleton` 归一化为规划上下文 | deep research 已调用 |
| `judge_evidence` | 对证据充分性做结构化判断 | deep research 已调用 |
| `generate_background_graph` | 生成背景补课图谱与学习路径 | 已注册，主链路仍由原服务驱动 |
| `run_critical_analysis` | 生成结构化批判阅读结果 | 已注册，主链路仍由原服务驱动 |
| `translate_page` | 调用既有逐页翻译服务 | 已注册，主链路仍由原服务驱动 |

### 当前约束来源

未来若实现 MCP adapter，必须继续服从以下现有约束：

- `safety_service.py`
  - 论文正文、`paperSkeleton`、`paperStructure`、页内上下文和 `rag_sources` 一律视为不可信输入。
  - 检索 scope 只允许 `current_paper`、`library`。
  - deep research 动作白名单固定为 `plan`、`retrieve_current_paper`、`retrieve_library`、`judge`、`synthesize_report`。
  - deep research 子问题固定 `3-5` 个，自动重试最多 `1` 次，进入模型的上下文预算近似 `8000` tokens。
- `trace_service.py`
  - trace 只保留在 Python 进程内存与日志中。
  - 只能记录截断后的摘要、计数器、步骤状态和错误摘要，不得记录 API Key、完整 prompt、完整论文全文或完整用户全文。
- `research_task_service.py`
  - deep research 当前已通过 `tool_registry` 调用关键能力。
  - 任务状态目前只保存在 Python 进程内存，不具备跨重启恢复能力。

## 未来 MCP 映射建议

### 1. Tools

最适合未来映射为 MCP tools 的对象，是已经进入 `tool_registry` 的 7 个内部工具。建议优先保持“内部工具名 = MCP tool 名”的稳定映射，减少双重命名带来的维护成本。

| 候选 MCP Tool | 对应内部工具 | 建议输入 | 主要限制 |
|---------------|--------------|----------|----------|
| `retrieve_current_paper` | `retrieve_current_paper` | `pdfId`、`query`、`topK`、`limit` 等 | 必须要求 `pdfId`；不得绕过当前论文边界读取原始文件 |
| `retrieve_library` | `retrieve_library` | `query`、`excludePdfId`、`topK`、`limit` 等 | 只允许内部文献库，不扩展到外部 Web 搜索 |
| `read_paper_skeleton` | `read_paper_skeleton` | `paperSkeleton`、`maxSections`、`maxCharsPerSection` | 只做结构化摘要归一化，不读取 PDF 原始文件 |
| `judge_evidence` | `judge_evidence` | `question`、`evidenceItems`、`keywords` | 只返回结构化 verdict，不暴露长链路内部推理 |
| `generate_background_graph` | `generate_background_graph` | `paper_topic`、`user_knowledge_level`、`pdfId`、`paperSkeleton`、`paperStructure` | 结果必须继续受证据来源约束 |
| `run_critical_analysis` | `run_critical_analysis` | `paper_content` 或 `pdf_id` | 继续保持证据不足时显式说明，不得编造 |
| `translate_page` | `translate_page` | `pageIndex`、`pageText`、`paperSkeleton`、`pageLayout` | 只处理传入页内容，不扩展到任意文件访问 |

工具映射时需要保留的限制：

- 检索 scope 仍只允许 `current_paper`、`library`。
- deep research 仍固定 `3-5` 个子问题、最多 `1` 次自动重试。
- 工具必须继续通过安全包装处理不可信论文内容，不能把检索片段视为可执行指令。
- 工具不得隐式扩展成文件访问、联网搜索、命令执行、插件调用或权限提升入口。

### 2. Resources

未来如果需要暴露 MCP resources，应该优先暴露“逻辑资源”，而不是文件系统、数据库或原始全文。

推荐优先级如下：

| 资源主题 | 推荐内容 | 推荐标识 |
|----------|----------|----------|
| 当前论文骨架/摘要 | `paperSkeleton` 的只读结构化视图 | 基于 `pdfId` |
| 当前论文证据片段 | 已归一化的 `rag_sources` / evidence items | 基于 `pdfId` + `sourceId` |
| 背景补课图谱结果 | `graph`、`learning_path_sections`、`sourceCoverage`、`confidence` | 基于 `pdfId` |
| 深度研究任务快照 | `taskId`、`status`、`stage`、`progress`、`plan`、`findings`、`report` | 基于 `taskId` |
| trace 摘要 | 脱敏后的阶段、计数器、错误摘要 | 基于 `traceId` |

不建议暴露为 MCP resources 的内容：

- 原始文件系统路径、任意目录遍历、PDF 二进制文件。
- 完整论文全文或未裁剪的当前论文 chunks。
- API Key、环境变量、系统提示词、未脱敏 trace、原始日志。
- Neo4j 底层写入入口、Chroma 数据目录或任何数据库内部文件。

### 3. Prompts

未来如果需要暴露 MCP prompts，建议只沉淀“边界清晰、输入输出结构稳定”的任务模板，而不是开放式聊天主循环。

推荐候选：

- 深度研究规划 prompt
  - 输入：研究问题、论文骨架、当前论文证据摘要
  - 输出：brief + `3-5` 个子问题
- 结构化批判阅读 prompt
  - 输入：四个分析轴的证据与 judge 结果
  - 输出：结构化 JSON 报告
- 背景补课图谱生成 prompt
  - 输入：论文主题、论文结构、RAG 片段、用户知识水平
  - 输出：图谱节点、学习路径、来源绑定
- 逐页翻译 prompt
  - 输入：页文本或布局块、论文骨架摘要
  - 输出：逐块或整页翻译
- 术语解释 prompt
  - 输入：选中文本、页上下文、证据片段
  - 输出：短解释

不建议直接定义为稳定 MCP prompt 的部分：

- 开放式 `/api/chat` 主循环。它依赖历史对话、查询规划、检索、judge、必要时重试和回答综合编排，不适合作为单一稳定 prompt 直接对外承诺。
- GROBID PDF 解析主链路。它更接近服务流水线，不是纯 prompt 能力。

## 当前不适合直接 MCP 化的部分

以下能力当前不适合直接映射为 MCP：

- 现有 React 前端、Java 网关对外 HTTP 接口。
- 开放式 chat orchestration 与完整 `/api/chat` 运行链路。
- GROBID 上传、解析、索引整条链路。
- 原始 trace store 与服务日志。
- Neo4j 持久化写入逻辑。
- 任意文件读写、命令执行、联网搜索、插件调用、权限提升能力。

原因并不是这些能力永远不能做，而是它们当前：

- 状态性太强，依赖现有服务上下文；
- 安全边界更复杂；
- 一旦直接暴露，会显著增加越权面和运维复杂度；
- 还没有形成足够稳定的 schema 和审计策略。

## 安全边界

未来 MCP adapter 必须继续复用现有安全与观测规则，至少满足以下要求：

- 所有论文正文、论文骨架、页内上下文和 RAG 片段仍视为不可信输入。
- adapter 在调用模型前，必须继续复用 `safety_service` 的注入检测、`wrap_untrusted_context` 包装与上下文预算裁剪。
- adapter 不得因论文中的文本出现“忽略之前指令”“泄露密钥”“执行命令”“联网搜索”“调用工具/MCP”等内容而改变执行边界。
- adapter 只允许暴露已经注册并经过 schema 约束的内部工具，不得绕过 `tool_registry` 直接暴露底层 LLM、RAG、Neo4j、trace 或文件系统对象。
- adapter 输出的 trace 只能是脱敏摘要，不能返回完整 prompt、完整论文全文、API Key 或系统提示词。
- adapter 如需外部接入，必须补充鉴权、调用审计、速率限制和租户隔离；在这些机制缺失前，不应对外提供可用 MCP 入口。

## 为什么当前不直接引入 MCP

当前阶段直接引入 MCP 的收益有限，复杂度偏高，主要体现在：

- 现有三层 HTTP 链路已经稳定，直接追加 MCP 会形成第二套外部接入面。
- 当前内部工具虽然已经成型，但还缺少版本化、兼容策略和长期稳定承诺。
- 当前任务状态、trace、背景图谱等对象多数仍是进程内或非持久化实现，直接开放为外部协议能力会让“实验性内部实现”被误当成“稳定平台能力”。
- 项目当前优先级仍是保证 RAG、批判阅读、背景补课、deep research 的可靠性，而不是扩展新的外部协议面。

因此，当前最合理的策略是：**先把内部边界稳定下来，再在 Python 侧做最小、受控的 adapter 实验。**

## 三阶段迁移路线

### 阶段一：内部工具 schema 稳定化

目标：把 `tool_registry` 里的 name、input schema、错误语义和响应结构进一步固定。

建议动作：

- 稳定 7 个内部工具的输入字段、默认值和错误格式。
- 明确哪些字段是长期承诺，哪些仍是内部实现细节。
- 为 evidence、task snapshot、trace summary 形成更稳定的只读数据模型。

### 阶段二：Python 内部或旁路 MCP adapter 实验

目标：在不改变前端和 Java 契约的前提下，做本地或内网可控的 MCP 实验。

建议动作：

- adapter 位置优先选在 Python 服务内部或旁路 sidecar，直接复用 `tool_registry`、`safety_service`、`trace_service`。
- 只开放经过审查的 tools、只读 resources、结构稳定的 prompts。
- 默认不开放文件系统、外网搜索、任意命令执行。
- 先服务于内部调试、受控客户端或研究实验，不对外宣传为稳定公共接口。

### 阶段三：外部客户端接入与鉴权审计

目标：在 schema、安全和运维边界成熟后，再考虑外部 MCP client 的正式接入。

建议动作：

- 补齐鉴权、调用审计、速率限制、租户隔离和错误监控。
- 明确哪些 tools/resources/prompts 是公开能力，哪些只保留内部。
- 对资源粒度、任务生命周期、trace 可见性和版本兼容性做正式承诺。

## 落地前检查清单

未来真正实现 MCP adapter 前，至少应再次确认：

- `tool_registry` 中的工具名和 schema 已稳定，不再频繁改动。
- deep research 的任务状态是否需要持久化，避免外部客户端读取到易失状态。
- trace 摘要是否已经完全脱敏，并且不会暴露内部提示词或密钥。
- 背景补课、批判阅读、翻译等输出是否已经形成可长期维护的数据契约。
- Java 和前端现有 `/api` 契约是否需要与 MCP 能力并存，以及是否需要额外文档说明两者职责边界。

## 非目标

本文档明确不包含以下内容：

- 不新增 MCP SDK 依赖。
- 不新增 MCP server 或 MCP client 运行时代码。
- 不新增任何 HTTP 接口、前端入口或 Java 转发链路。
- 不把所有内部服务直接改造成 MCP server。
- 不引入外部 Web 搜索、文件系统浏览或命令执行能力。

当前模块的目标仅是把未来适配路径写清楚，避免后续实现时从不稳定边界直接起步。
