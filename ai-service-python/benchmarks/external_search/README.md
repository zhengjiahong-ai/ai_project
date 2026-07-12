# External academic Provider benchmark

此目录包含 P6-04 Provider 选型评测工具（扩展自 P3-04），不是生产联网客户端，也不会注册到 `create_external_search_provider()`。

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

## 评测范围

- **3 个候选 Provider**: Crossref、Semantic Scholar、ArXiv
- **12 个跨学科 query**: 涵盖 CS/AI(7)、医学(1)、化学(1)、物理学(1)、经济学(1)、社会科学(1)
- **评测指标**: 成功率、DOI 覆盖率、摘要覆盖率、Hit@5、MRR、延迟(P50/P95)、质量评分
- **选型输出**: 推荐 Provider 组合 (`recommendedCombination`) 和生产配置 (`productionConfig`)

## 安全边界

- 请求仅发往固定的 Crossref `/works`、Semantic Scholar `/graph/v1/paper/search`、ArXiv `/query` endpoint。
- 12 个 query 固定在 `fixtures.json`；单次 live 运行最多 36 次顺序请求，请求间隔 1.1 秒。
- 禁止重定向，连接与读取均有超时，响应体上限为 1 MiB，不自动重试。
- 所有候选都只评估匿名访问，不读取或发送 API key；需要认证才能稳定访问的候选标记为"需要 API Key"。
- snapshot 仅保留评测所需元数据、响应大小、耗时和白名单限流 header；不保存认证 header、完整摘要或原始响应。
- 结果中的 URL 只是待核验元数据，benchmark 不会跟随或下载这些 URL。

## 选型逻辑

1. **门禁**: 每个 Provider 必须成功完成 ≥ ceil(caseCount × 0.8) 个 case
2. **排除**: 匿名访问 100% 429 限流的 Provider 标记为 excluded
3. **排序**: 通过门禁的 Provider 按 qualityScore 降序排列
4. **组合**: 所有通过门禁的 Provider 构成推荐组合
5. **生产配置**: `productionConfig` 字段给出推荐的 `PIXIU_EXTERNAL_SEARCH_PROVIDERS` 值

质量评分公式: `0.35 × hitAt5 + 0.25 × MRR + 0.20 × abstractCoverage + 0.20 × doiCoverage`

## 更新 snapshot

只有在重新核验 Provider 政策并明确执行 `--live` 时才更新 snapshot。更新后必须运行默认离线模式，确认 `benchmark-results.json` 可重复生成，并检查 snapshot 不含认证 header、完整摘要或原始响应。
