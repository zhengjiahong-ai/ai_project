# 外部学术 Provider benchmark

核验日期：2026-06-21。

## 范围与方法

P3-04 使用 6 个固定论文检索 case，对 Crossref 与 Semantic Scholar Academic Graph 各执行一次受控匿名采样。评测代码、脱敏 snapshot 与离线结果位于 `ai-service-python/benchmarks/external_search/`。该代码只用于隔离 benchmark，不注册生产 Provider 客户端，也不改变外部检索默认关闭状态。

相关政策核验来源：

- [Crossref 认证与限流](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
- [Crossref 元数据与许可说明](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/graphs)
- [Semantic Scholar API 许可协议](https://www.semanticscholar.org/product/api/license)

## 实际结果

| 指标 | Crossref | Semantic Scholar |
| --- | ---: | ---: |
| 成功 case | 6/6 | 0/6 |
| `successRate` | 1.000000 | 0.000000 |
| `doiCoverage` | 1.000000 | 0.000000 |
| `abstractCoverage` | 0.100000 | 0.000000 |
| `hitAt5` | 0.333333 | 0.000000 |
| `meanReciprocalRank` | 0.250000 | 0.000000 |
| `medianLatencyMs` | 552 | 无成功样本 |
| `p95LatencyMs` | 2079 | 无成功样本 |
| 429 | 0 | 6 |
| 质量分 | 0.399167 | 0.000000 |

Crossref 六次请求均成功，但固定 bibliographic query 只在 2/6 case 的 top-5 中找到相关论文；摘要覆盖率为 10%。主要未命中样例包括 Attention Is All You Need、BERT、RAG 与 AlphaFold，说明仅以该查询策略作为外部证据补充时召回质量有限。

Semantic Scholar 的匿名共享访问在六个 case 上均返回 HTTP 429，snapshot 未保存响应正文或任何认证信息。项目不要求开发者或部署环境配置 Semantic Scholar API key；需要凭据才能稳定访问的候选视为运维不适用。

## 结论

本次 benchmark 状态为 `complete`，选择 `crossref` 作为 P3-05 唯一实现目标。Crossref 达到 6/6 请求成功门槛且无需认证；Semantic Scholar 因匿名访问六次全部 429 被判定为运维不适用并排除。

该调整不把 Semantic Scholar 的失败计为质量分劣势，也不授权降级到任意网络来源。P3-05 只实现 Crossref；Semantic Scholar 保留在威胁模型白名单中，但没有新的安全评审和任务授权不得实现或注册。

## 安全与可复现性

`provider-snapshot.json` 只保留状态、耗时、响应大小、白名单限流 header 和 top-5 有界元数据。完整摘要被转换为 `hasAbstract/abstractChars`，认证 header 与原始响应均不落盘。结果中的 DOI/URL 只是待核验元数据，评测器不会跟随这些 URL。

默认离线模式从 snapshot 重算 `benchmark-results.json`，不会发起网络请求。本次离线重算与 live 生成结果的 SHA-256 内容比较一致。

## P3-17 效果、成本与安全评测

核验日期：2026-06-29。`effect-fixtures.json` 固定四类任务：证据缺口补查、外部冲突发现、内部证据充足时跳过外部检索、Provider 故障降级。`effect-snapshot.json` 保存关闭/开启模式的配对结果；`manual-review.json` 保存两条 Crossref 来源的 DOI、URL、标题、摘要存在性与一致性结论，不保存完整摘要。

默认离线命令如下，不访问 Provider 或 LLM：

```powershell
cd ai-service-python
python -m benchmarks.external_search.effect_benchmark
```

| 指标 | 关闭 | 开启 | 严格门槛 |
| --- | ---: | ---: | ---: |
| 证据覆盖率 | 0.750000 | 1.000000 | 开启至少 0.8，提升至少 0.15 |
| 冲突发现率 | 0.000000 | 1.000000 | 开启至少 0.8，且不得回退 |
| 错误引用率 | 0.000000 | 0.000000 | 必须为 0 |
| 平均外部调用次数 | 0 | 0.750000 | 不超过 3 |
| 平均外部耗时 | 0 ms | 1090 ms | 不超过 3000 ms |
| 安全检查通过率 | - | 1.000000 | 必须为 1.0 |
| 人工一致性通过率 | - | 1.000000 | 必须为 1.0 |
| Crossref `hitAt5` | - | 0.333333 | 至少 0.8 |

人工抽查使用官方 Crossref `/works/{doi}` 元数据核对 `10.2196/preprints.40992` 和 `10.3390/app12188972`。两条记录的 DOI、URL、标题和摘要存在性与保存的有界元数据一致；完整摘要未落盘，自动测试不会重新访问 DOI 或 URL。

## P3-17 启用结论

效果、成本、安全与人工一致性门槛通过，但 Crossref `hitAt5=0.333333` 未达到 `0.8` 的严格相关性门槛。`effect-results.json` 因此输出 `continue_default_disabled`。生产默认开关保持关闭，不进入有限灰度或正式启用；后续只有在相同固定任务、相同安全边界和相同门槛下重新评测全部通过，才允许重新讨论启用。
