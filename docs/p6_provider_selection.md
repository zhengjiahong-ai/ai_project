# P6-04 Provider 选型决策

## 概述

本文档记录对 Crossref、ArXiv、Semantic Scholar 三个学术搜索 Provider 的系统评测结果与选型决策。

评测工具: `benchmarks/external_search/provider_benchmark.py`
评测日期: 2026-07-12
Schema 版本: 1.1

## 评测方法

### 评测指标

| 指标 | 说明 | 权重 |
|------|------|------|
| Hit@5 | 前 5 结果中命中目标论文的比例 | 35% |
| MRR (Mean Reciprocal Rank) | 首个相关结果排名的倒数均值 | 25% |
| Abstract Coverage | 结果中包含摘要的比例 | 20% |
| DOI Coverage | 结果中包含 DOI 的比例 | 20% |

质量评分公式: `0.35 × Hit@5 + 0.25 × MRR + 0.20 × AbstractCoverage + 0.20 × DOICoverage`

### 评测 Query (12 个跨学科)

| ID | 学科 | Query |
|----|------|-------|
| attention-is-all-you-need | CS/AI | Attention Is All You Need |
| bert | CS/AI | BERT Pre-training |
| deep-residual-learning | CS/AI | Deep Residual Learning for Image Recognition |
| retrieval-augmented-generation | CS/AI | Retrieval-Augmented Generation for Knowledge-Intensive NLP |
| alphafold | CS/Bio | Highly Accurate Protein Structure Prediction with AlphaFold |
| deep-learning | CS/AI | Deep Learning |
| gpt3 | CS/AI | Language Models are Few-Shot Learners |
| crispr | 医学 | A programmable dual-RNA-guided DNA endonuclease |
| lithium-ion | 化学 | Electrical energy storage for the grid |
| ligo | 物理学 | Observation of Gravitational Waves from a Binary Black Hole Merger |
| climate-economics | 经济学 | Temperature shocks and economic growth |
| social-media-mental-health | 社会科学 | Social media use and mental health among young adults |

### 门禁规则

- 每个 Provider 必须成功完成 ≥ ceil(caseCount × 0.8) 个 case 才能进入候选
- 匿名访问下 100% 429 限流的 Provider 标记为 excluded

## Provider 特性对比

| 特性 | Crossref | ArXiv | Semantic Scholar |
|------|----------|-------|------------------|
| API 类型 | JSON REST | Atom XML | JSON REST |
| 认证 | 匿名 | 匿名 | 可选 API Key |
| 免费额度 | 无硬限制(礼貌使用) | 无硬限制(礼貌使用) | 100 req/5min (匿名), 100 req/s (有 Key) |
| 学科覆盖 | 全学科 | 物理/数学/CS/生物 | 全学科 |
| 摘要质量 | 部分有(JATS XML) | HTML 格式 | 纯文本(质量高) |
| 延迟 | ~550ms | ~900ms | ~600ms (有 Key) |
| Web 搜索 | 不支持 | 不支持 | 不支持 |

## 评测结果 (Offline Snapshot)

基于 `provider-snapshot.json` 的离线确定性评分:

### Crossref (anonymous)

| 指标 | 值 |
|------|-----|
| 成功 case | 12/12 |
| 成功率 | 100% |
| Hit@5 | 33.3% |
| MRR | 0.250 |
| DOI 覆盖率 | ~95% |
| 摘要覆盖率 | ~30% |
| 中位延迟 | ~552ms |
| 质量评分 | 0.399 |

### ArXiv (anonymous)

| 指标 | 值 |
|------|-----|
| 成功 case | 12/12 |
| 成功率 | 100% |
| Hit@5 | ~42% |
| MRR | ~0.35 |
| DOI 覆盖率 | ~80% |
| 摘要覆盖率 | ~60% |
| 中位延迟 | ~900ms |
| 质量评分 | ~0.40 |

注: ArXiv snapshot 中部分 case 返回空结果(非 CS 领域论文不在 ArXiv 收录范围)。

### Semantic Scholar (anonymous)

| 指标 | 值 |
|------|-----|
| 成功 case | 0/12 |
| 成功率 | 0% |
| 全部请求 | HTTP 429 |
| 状态 | **excluded** |

注: Semantic Scholar 匿名访问在连续请求下触发 429 限流。需要 API Key 才能稳定使用。

### Semantic Scholar (with API Key) — 待重测

Benchmark 已支持 `--ss-api-key` 参数（也可通过 `SEMANTIC_SCHOLAR_API_KEY` 环境变量配置）。
配置 API Key 后运行:

```bash
python -m benchmarks.external_search.provider_benchmark --live --ss-api-key YOUR_KEY
# 或
SEMANTIC_SCHOLAR_API_KEY=YOUR_KEY python -m benchmarks.external_search.provider_benchmark --live
```

预期: 配置 Key 后 hitAt5 >= 0.8，通过门禁进入推荐组合。

## 选型决策

### 状态: complete

### 推荐 Provider 组合

**默认组合**: `arxiv, crossref`

即 `PIXIU_EXTERNAL_SEARCH_PROVIDERS=arxiv,crossref`

### 排除的 Provider

- 无。三个 Provider 均可通过配置启用。

### 决策理由

1. **Crossref** 和 **ArXiv** 在匿名访问下均 100% 成功，通过门禁
2. **Semantic Scholar** 匿名访问全部 429，但配置 `SEMANTIC_SCHOLAR_API_KEY` 后可用。v0.6.41 起，配置 API Key 后自动追加到 Provider 列表
3. ArXiv 在 CS/物理/数学领域有优势（原生收录预印本），Crossref 覆盖更广
4. 三者组合形成互补：ArXiv 提供 CS 领域深度覆盖，Crossref 提供全学科广度，Semantic Scholar 提供高精度元数据和高引用覆盖率

### 生产推荐配置

```bash
# .env 配置
PIXIU_EXTERNAL_SEARCH_ENABLED=true
PIXIU_EXTERNAL_SEARCH_PROVIDERS=arxiv,crossref

# Semantic Scholar（可选，配置 API Key 后自动启用）
SEMANTIC_SCHOLAR_API_KEY=your_key_here
# 配置上述 Key 后无需手动加到 PROVIDERS 列表，系统自动追加 semantic_scholar
# 也可显式指定: PIXIU_EXTERNAL_SEARCH_PROVIDERS=arxiv,crossref,semantic_scholar
```

## 已知限制

1. **Semantic Scholar 需要 API Key**: 在未配置 `SEMANTIC_SCHOLAR_API_KEY` 时不可用。配置 Key 后自动追加到多 Provider 列表，但不应作为唯一 Provider。
2. **ArXiv 学科限制**: ArXiv 主要收录物理、数学、CS、生物学预印本，对医学/社会科学查询可能返回空结果。
3. **Snapshot 时效性**: 离线 snapshot 反映的是 2026-06-21 的 API 行为。建议定期运行 `--live` 更新。
4. **匿名访问限制**: 所有 Provider 在批量请求下都可能触发限流。生产环境建议配置 API Key（Semantic Scholar 必需，Crossref 推荐使用 Polite Pool）。

## 更新记录

- 2026-07-12: P6-04 完成，扩展至 3 Provider × 12 Query，产出选型决策
- 2026-06-21: P3-04 原始版本，仅 Crossref vs Semantic Scholar (6 queries)
