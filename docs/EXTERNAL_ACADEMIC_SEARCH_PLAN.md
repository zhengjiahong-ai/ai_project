# 外部学术检索安全计划

## 目的与适用范围

本文档定义 Pixiu 在引入任何联网代码前必须遵守的外部学术检索威胁模型。P3-01 只固化安全边界，不启用外部检索，也不授权生产环境访问任何 Provider。

外部学术检索只能补充当前论文和内部文献库仍未覆盖的明确证据缺口。证据顺序固定为：

1. 当前论文。
2. 内部文献库。
3. 经过 JUDGE 确认的明确证据缺口。
4. 受白名单和预算约束的外部学术元数据。

外部证据不能覆盖内部证据、自动解决冲突、提高为可信事实或绕过人工审查。

## Provider 白名单

P3-04 benchmark 的候选 Provider 仅限以下只读学术元数据接口：

| Provider | 允许的 HTTPS API base path | 允许能力 |
| --- | --- | --- |
| Crossref | `https://api.crossref.org/works` | 论文元数据搜索和 DOI 元数据详情 |
| Semantic Scholar Academic Graph | `https://api.semanticscholar.org/graph/v1/paper` | 论文元数据搜索和论文元数据详情 |

白名单只表示 Provider 可以进入后续 benchmark，不表示已经获准在生产环境调用。P3-04 必须先比较候选来源并选定首个正式 Provider，P3-05 才能实现该 Provider 的客户端。

Provider adapter 必须根据代码中的固定 HTTPS host、base path 和结构化参数构造请求。用户输入、论文内容、模型输出和外部响应均不得提供或改变目标 URL、host、协议、端口、Provider、预算或权限。不得跟随到非白名单 host 的重定向。

只允许上述论文元数据搜索和详情能力。明确禁止：

- Semantic Scholar Recommendations API、Datasets API 及其他未列入白名单的服务。
- PDF、TEI XML、附件、数据集或其他全文下载。
- 任意 URL 获取、通用 Web 搜索、网页抓取和内容协商式全文获取。
- 写操作、文件系统访问、Shell、代码执行、包安装和长期运行进程。
- LLM、浏览器、前端、Java 网关、内部检索层或 MCP adapter 直接访问外部 Provider。
- 跟随外部结果中的 DOI、URL、下载地址或重定向继续获取内容。

后续任务不得在未更新本文档并完成安全审查的情况下扩大 Provider、host、base path 或允许能力。

## 信任边界与威胁

论文正文、用户研究问题、检索 query、Provider 响应、元数据字段、摘要、链接和错误消息均为不可信输入。主要威胁包括：

- 论文或外部摘要中的提示注入改变 Provider、host、预算、权限或工具参数。
- 用户或模型通过 URL、重定向、特殊编码或响应字段发起 SSRF。
- 超大响应、畸形 JSON、异常嵌套或恶意文本消耗资源。
- Provider 元数据错误、过期、相互矛盾或与 DOI/URL 不一致。
- API key、认证 header、query 或完整响应经 trace、日志、错误或缓存泄漏。
- Provider 超时、限流或故障放大任务失败和外部调用成本。

未来唯一允许跨越网络信任边界的组件是受控 Provider adapter。adapter 必须执行响应体和字段长度限制、严格结构校验、提示注入防护、来源归一化、脱敏和预算检查，再把统一外部证据交给研究流程。外部内容在进入模型或界面前仍保持“不可信补充证据”标识，并接受人工审查。

## 默认关闭与启用条件

外部学术检索默认关闭。未来实现只有同时满足以下条件才能创建网络客户端或发起请求：

- 显式启用开关为真。
- Provider 已通过 P3-04 benchmark 且仍在本文档白名单内。
- Provider 配置完整，所需凭据存在且只传给对应固定 host。
- 当前任务显式允许外部检索，并具有有效的调用数、结果数和时间预算。
- 内部检索已经执行，JUDGE 仍返回明确证据缺口。

任一条件缺失、非法或无法验证时必须保持禁用，不得静默切换 Provider、扩大范围或尝试通用网络访问。论文内容和模型输出不得开启该能力。

P3-03 已固化配置工厂：`PIXIU_EXTERNAL_SEARCH_ENABLED` 仅在 `1/true/yes/on` 时开启配置路径，其他值直接返回不联网的禁用实现；开启时 `PIXIU_EXTERNAL_SEARCH_PROVIDER` 仅允许 `crossref` 或 `semantic_scholar`。P3-05 只注册 Crossref 客户端，固定访问 `https://api.crossref.org/works` 并限制参数、超时、重定向、结果数、响应体和保留字段；Semantic Scholar 仍返回脱敏的“客户端尚未实现”配置错误。客户端注册不表示用户任务已经获准联网，当前业务链路仍不调用它。

## 数据处理与审计

外部响应只保留后续统一证据模型允许的有界元数据。DOI 和 URL 只是待核验来源标识，不授权系统跟随链接。外部来源必须与当前论文、内部文献库和模型推断保持不同标识。

trace 只允许记录 Provider 名称、调用结果、计数、缓存命中、失败类型、延迟、外部证据数量和脱敏 query 摘要。以下内容不得进入 trace、日志、错误消息、缓存键、持久化快照或模型上下文转储：

- API key、token、认证 header 和包含凭据的 URL。
- 完整 Provider 响应或未裁剪错误体。
- PDF、全文、完整摘要和其他无限长度内容。
- 未脱敏 query、用户敏感数据和内部论文正文。

面向用户的来源展示可保留经过校验的 DOI、URL 和访问时间，但服务端不得自动访问该 URL；缺少或失效的 URL 不得被替换为伪链接。

## 失败与降级策略

连接或读取超时、限流、断网、非成功响应、响应过大、结构无效、重定向越界、Provider 不可用或预算耗尽时，必须停止或跳过外部检索，继续使用当前论文和内部文献库证据。任务应保留脱敏降级原因，不能因外部失败丢弃已有内部 finding，也不能把证据缺口标记为已解决。

错误响应不得包含凭据、完整请求 URL、完整 query、完整响应体或完整摘要。未知 Provider、配置不完整和白名单不匹配属于严格配置错误，不得静默回退到其他外部来源。

## P3-04 benchmark 状态

实际指标与失败样例见 [`external_search_benchmark.md`](external_search_benchmark.md)。2026-06-21 的受控匿名采样中，Crossref 完成 6/6 case；Semantic Scholar 六次请求均因 HTTP 429 失败，被判定为匿名运维不可用。项目不配置 Semantic Scholar API key，本次结果选择 Crossref，P3-04 已完成。

隔离 benchmark 的 `--live` 网络代码不是 Provider adapter，不得导入生产工厂或服务路径。P3-05 只能实现 Crossref；Semantic Scholar 虽仍在白名单中，但没有新的安全评审和任务授权不得实现或注册。重新采样只能使用相同固定 fixture、endpoint、请求预算、匿名访问和脱敏规则。

## P3-05 客户端状态

Crossref 是当前唯一实现并注册的生产 Provider adapter。客户端匿名、只读，仅向固定 `/works` endpoint 发送 `query.bibliographic` 与 `rows` 结构化参数；连接/读取超时为 `3.05/10` 秒，最多请求 20 条结果，响应体最多 1 MiB，禁止重定向且不会跟随 DOI、URL、许可或其他返回链接。Provider 响应经过字段裁剪、JATS/HTML 摘要清理、结构校验和统一外部证据归一化；错误只暴露有限失败码及可选 HTTP 状态，不包含 query、完整 URL 或响应体。

P3-06 已在 Crossref 客户端内部增加 1 小时 TTL 的版本化 JSON 缓存、实例级 1 秒最小请求间隔、限定状态重试和 Provider 中立去重。缓存 key 只使用 Provider 与规范化 query 的 SHA-256，entry 移除 query 且不保存 header、凭据或请求 URL；写入采用原子替换，文件缺失、过期、损坏或 schema 非法时视为空缓存。相同 query 的缓存结果上限足以满足本次请求时直接切片返回，包括空结果。

客户端仅对 `429/500/502/503/504` 最多重试 2 次，退避为 0.5 秒和 1 秒；合法 `Retry-After` 优先，要求等待超过 30 秒时停止重试而不提前请求。超时、断网、3xx、其他 4xx、畸形 JSON 和超大响应直接失败。结果在缓存前按 DOI、Provider ID 和规范化标题去重并保留首次出现项。本阶段仍不提供任务预算、查询规划、工具注册、公开 API、前端开关或业务链路调用；默认关闭和人工授权边界不变。

## P3-07 查询规划状态

外部查询规划是确定性纯函数，只接受用户研究问题、Planner 子问题和 JUDGE `missingAspects`。只有存在明确 `missingAspects` 时才按“研究问题 + 子问题 + 单个缺失点”生成候选，固定最多 5 条、每条最多 256 字符；输入项、各组成部分长度、输出顺序和规范化去重规则均为代码常量，调用方不能扩大。

查询清洗按独立文本片段剥离 URL、提示覆盖、命令执行、联网、工具调用以及修改 Provider、host、endpoint、预算、权限或安全范围的指令，只保留 Unicode 字母数字、空白和有限学术符号，以保留主题、方法、指标和年份。接口没有论文正文、Provider、host、预算、权限或安全范围参数，也不调用 LLM、Provider、网络或文件系统；因此论文正文和恶意片段不能通过查询规划改变控制面。本阶段仍不注册工具、不接入 Deep Research/Agent，也不授予任何联网能力。

## P3-15 对抗验证状态

固定恶意 fixture 覆盖提示覆盖、凭据索取、Provider/host/预算/权限篡改、私网重定向、超大响应、畸形 JSON、429、5xx、连接与读取超时和断网。测试只使用 mock response，不访问真实 Provider 或 LLM。Crossref 始终只请求代码内固定的 `https://api.crossref.org/works`，禁用重定向，响应中的 `Location`、DOI、URL 和 HTML 链接均不能触发后续网络请求。

Crossref 标题、作者和 JATS/HTML 摘要在统一证据归一化前按不可信文本处理。检测到的提示覆盖、凭据泄漏或命令式片段替换为安全占位文本；同字段的正常学术内容仍被保留，并继续受原字段长度限制。外部 query 仍只能由受限查询规划器生成，任务文本和外部响应不能修改启用开关、Provider、host、预算、工具版本或 `safetyScope`。

Deep Research 和 Agent 仅传播 `success/no_queries/disabled/budget_exceeded/failed` 对应的固定降级说明。Provider 原始 `reason`、异常消息、响应体和凭据不得进入 finding、Agent 工具调用摘要、trace 或 SQLite 快照；外部失败继续保留当前论文和内部文献库证据，不把缺口标记为已解决。

## P3-01 非目标

本任务不实现 Provider 客户端、Provider 工厂、统一外部证据模型、缓存、限流、重试、去重、任务预算、查询规划、工具注册、API、持久化、UI、MCP 暴露或真实网络验证。这些能力必须按 P3-02 至 P3-17 的顺序逐项实现和验证。
