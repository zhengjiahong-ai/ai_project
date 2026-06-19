# MCP Adapter 计划

## 当前状态

P2-2 已完成只读 MCP adapter 原型。入口位于 `ai-service-python/mcp_adapter/`，使用 MCP Python SDK 1.9.x 和本机 `stdio` transport；它不挂载 FastAPI、不增加 `/api` 路由，也不修改 Java 或前端链路。

## 只读原型边界

- 默认关闭；仅当进程环境包含 `PIXIU_MCP_ENABLED=true` 时，`python -m mcp_adapter` 才启动，否则以非零状态退出。
- MCP 协议 `tools/list` 只返回 `read_paper_skeleton`、`retrieve_current_paper`、`retrieve_library`，不额外注册名为 `list_tools` 的工具。
- adapter 直接复用 `list_tools()` 返回的契约，不维护第二套 schema。
- 工具版本、注册表 schema version、安全范围和 MCP 预算放在 `_meta.pixiu`；输入/输出 schema 原样复用，annotations 声明只读、非破坏、幂等和封闭世界。
- 仅暴露 `access=read_only`、`sideEffects=false`、`networkAccess=false` 且数据范围在 allowlist 中的工具；所有调用继续经过 `ToolRegistry.invoke()` 的输入和输出校验。
- `retrieve_current_paper` 禁止 `includeAll=true`，最大 `topK/limit/maxTextChars` 为 `8/5/900`；`retrieve_library` 为 `5/4/700`；论文骨架最多 `6` 节、每节 `220` 字符。
- 不暴露完整论文正文、文件系统、API key、完整 prompt、原始 trace 或任意代码执行能力。
- `sensitiveOutput=true` 的结果必须继续经过现有截断、证据归一化和 trace 脱敏边界。

## 已落实的验收边界

- adapter 默认关闭时不改变现有 FastAPI、Deep Research 和 Agent 行为。
- MCP `tools/list` 中获准工具的名称、版本、输入/输出 schema 和安全范围来自同一个内部注册表。
- 非法参数沿用 `ToolValidationError` 的工具名、输入/输出方向和字段路径，不绕过注册层直接调用 handler。
- 工具成功结果同时返回 JSON text content 和 `structuredContent`；业务异常作为 tool error 返回，未知异常只返回脱敏后的固定错误，不包含堆栈和内部路径。

## 非目标

- 不提供 Streamable HTTP、SSE、认证、远程访问、MCP client、resources 或 prompts。
- 不把 adapter 加入 Docker Compose 常驻服务；需要时由本机 MCP 客户端单独拉起进程。
