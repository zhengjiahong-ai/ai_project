# External academic Provider benchmark

此目录包含 P3-04 Provider 选型和 P3-17 效果/成本/安全评测工具，不是生产联网客户端，也不会注册到 `create_external_search_provider()`。

## 运行

在 `ai-service-python` 目录运行一次受控采样：

```powershell
python -m benchmarks.external_search.provider_benchmark --live
```

默认模式不会联网，只读取已脱敏 snapshot 并重新计算结果：

```powershell
python -m benchmarks.external_search.provider_benchmark
```

`--fixture`、`--snapshot` 和 `--output` 只能更换本地文件路径。CLI 不提供 host、endpoint 或 query 覆盖参数。

P3-17 默认离线比较关闭/开启外部检索的固定配对任务：

```powershell
python -m benchmarks.external_search.effect_benchmark
```

该命令读取 `effect-fixtures.json`、`effect-snapshot.json`、`manual-review.json` 和 P3-04 `benchmark-results.json`，确定性生成 `effect-results.json`。任何严格门槛失败都输出 `continue_default_disabled`；该命令没有联网模式。

## 安全边界

- 请求仅发往固定的 Crossref `/works` 与 Semantic Scholar Academic Graph `/paper/search` endpoint。
- 6 个 query 固定在 `fixtures.json`；单次 live 运行最多 12 次顺序请求，请求间隔 1.1 秒。
- 禁止重定向，连接与读取均有超时，响应体上限为 1 MiB，不自动重试。
- 两个候选都只评估匿名访问，不读取或发送 API key；需要认证才能稳定访问的候选视为运维不适用。
- snapshot 仅保留评测所需元数据、响应大小、耗时和白名单限流 header；不保存认证 header、完整摘要或原始响应。
- 结果中的 URL 只是待核验元数据，benchmark 不会跟随或下载这些 URL。
- P3-17 人工核验文件只保存 DOI、URL、标题、摘要存在性和一致性结论，不保存完整摘要；自动测试不会重新访问 DOI/URL。

## 更新 snapshot

只有在重新核验 Provider 政策并明确执行 `--live` 时才更新 snapshot。更新后必须运行默认离线模式，确认 `benchmark-results.json` 可重复生成，并检查 snapshot 不含认证 header、完整摘要或原始响应。
