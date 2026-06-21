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

P3-03 已固化配置工厂：`PIXIU_EXTERNAL_SEARCH_ENABLED` 仅在 `1/true/yes/on` 时开启配置路径，其他值直接返回不联网的禁用实现；开启时 `PIXIU_EXTERNAL_SEARCH_PROVIDER` 仅允许 `crossref` 或 `semantic_scholar`。当前未注册联网 builder，因此显式开启任一合法 Provider 也会返回脱敏的“客户端尚未实现”配置错误。该工厂边界不表示外部检索已经可用。

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

实际指标与失败样例见 [`external_search_benchmark.md`](external_search_benchmark.md)。2026-06-21 的受控匿名采样中，Crossref 完成 6/6 case，Semantic Scholar 六次请求均因 HTTP 429 失败。由于选型规则要求每个候选 Provider 至少成功 5/6 case，本次结果为 `insufficient_data`，不选择 Provider，P3-04 不标记完成。

隔离 benchmark 的 `--live` 网络代码不是 Provider adapter，不得导入生产工厂或服务路径。重新采样只能使用相同固定 fixture、endpoint、请求预算和脱敏规则；在满足门槛并完成人工审查前，P3-05 不得实现或注册生产联网客户端。

## P3-01 非目标

本任务不实现 Provider 客户端、Provider 工厂、统一外部证据模型、缓存、限流、重试、去重、任务预算、查询规划、工具注册、API、持久化、UI、MCP 暴露或真实网络验证。这些能力必须按 P3-02 至 P3-17 的顺序逐项实现和验证。
