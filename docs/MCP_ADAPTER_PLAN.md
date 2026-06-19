# MCP Adapter 计划

## 当前状态

项目尚未实现或启用 MCP server/client，也没有新增对外 MCP 路由。Python 内部 `tool_registry` 已提供 `schemaVersion=1.0` 的可序列化工具契约，每个工具包含 `name/version/description/inputSchema/outputSchema/safetyScope`，并在执行前后校验输入与输出。

## P2-2 只读原型边界

- 默认关闭，仅在显式配置后启动。
- 首批只允许列举工具、读取论文骨架和只读检索。
- adapter 直接复用 `list_tools()` 返回的契约，不维护第二套 schema。
- 仅暴露 `access=read_only`、`sideEffects=false` 且数据范围在 allowlist 中的工具。
- 不暴露完整论文正文、文件系统、API key、完整 prompt、原始 trace 或任意代码执行能力。
- `sensitiveOutput=true` 的结果必须继续经过现有截断、证据归一化和 trace 脱敏边界。

## 后续验收

- adapter 默认关闭时不改变现有 FastAPI、Deep Research 和 Agent 行为。
- MCP `list_tools` 与内部注册表的名称、版本、输入/输出 schema 和安全范围完全一致。
- 非法参数沿用 `ToolValidationError` 的工具名、输入/输出方向和字段路径，不绕过注册层直接调用 handler。
