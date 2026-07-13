# P6 多源深度研究 — 验收报告

## 概述

本报告总结 P6（Pixiu → Deep Research）第五阶段"综合报告与跨源验证升级"的全部验收结果。覆盖安全验收、功能集成验收、性能基准和回退验证。

验收日期：2026-07-13

---

## 1. 安全验收

| 验收项 | 状态 | 验证方式 | 备注 |
|--------|:----:|----------|------|
| URL 白名单 100% 覆盖 | ✅ 通过 | `test_p6_security_boundary.py` — 所有 category 正确分类，白名单外域名拒绝 | `test_url_whitelist.py` 已有完整覆盖 |
| 内网 IP 拒绝 | ✅ 通过 | `test_p6_security_boundary.py` — 127.0.0.1/10.x/172.16.x/192.168.x/IPv6 loopback 均拒绝 | `test_web_fetcher.py` DNS 解析层验证 |
| 重定向防护 | ✅ 通过 | `test_p6_security_boundary.py` — 301/302 重定向拒绝；`allow_redirects=False` | `test_web_fetcher.py` 已有 `test_fetch_redirect_detected` |
| 注入清洗 | ✅ 通过 | `test_p6_security_boundary.py` — 提示注入文本被标记/拒绝 | `test_content_safety.py` + `test_safety_service.py` 已有完整覆盖 |
| API Key 不泄露 | ✅ 通过 | `test_p6_security_boundary.py` — 错误消息不含 API 密钥/Token | 各 Provider 测试均有覆盖 |
| 预算耗尽降级 | ✅ 通过 | `test_p6_security_boundary.py` — budget_exceeded 返回空 items | `test_tool_registry.py` 已有 budget 测试 |

---

## 2. 功能集成验收

| 验收项 | 状态 | 验证方式 |
|--------|:----:|----------|
| Deep Research + Web 搜索全链路 | ✅ 通过 | `test_web_search_e2e.py` — search_web 工具注册且可调用 |
| Agent + 迭代搜索全链路 | ✅ 通过 | `test_web_search_e2e.py` — agentic search loop 证据含 provenance |
| 多 Provider 并发去重 | ✅ 通过 | `test_web_search_e2e.py` — DOI 去重验证 |
| 证据溯源 (P6-19) | ✅ 通过 | `test_web_search_e2e.py` — evidence items 含 provenance 字段 |
| 评分升级 (P6-20) | ✅ 通过 | `test_web_search_e2e.py` — coverage 含 diversity/trust/agreement |
| 报告升级 (P6-21) | ✅ 通过 | `test_web_search_e2e.py` — 报告含全部必需章节 |
| 交叉验证 (P6-18) | ✅ 通过 | `test_web_search_e2e.py` — cross validator 产生有效 claims |
| 空结果优雅降级 | ✅ 通过 | `test_web_search_e2e.py` — judge handles empty evidence |
| Web 搜索禁用行为一致 | ✅ 通过 | `test_p6_security_boundary.py` — 禁用时返回 disabled，items 为空 |
| 学术搜索不受 Web 状态影响 | ✅ 通过 | `test_p6_security_boundary.py` — `retrieve_external_academic` 独立工作 |

---

## 3. 性能基准

| 指标 | 目标 | 结果 | 状态 |
|------|------|------|:----:|
| Brave/Tavily 成功率 | ≥90% | 离线 snapshot 评估 | ⚠ 离线数据有限，需 `--live` 验证 |
| 页面抓取成功率 | ≥80% | 离线 counters 评估 | ⚠ 离线数据有限，需 `--live` 验证 |
| 迭代额外时延 | ≤15s | 离线 trace 评估 | ⚠ 离线数据有限 |
| 额外 token | ≤2.0x | 估计比率 | ⚠ 离线估计，需真实调用确认 |

> **注**：离线 snapshot 数据有限，基准结果标记为"待真实 API 验证"。运行 `python -m benchmarks.external_search.web_search_benchmark --live` 可获得实际结果。

---

## 4. 回退安全验证

| 验证项 | 状态 | 说明 |
|--------|:----:|------|
| Web 搜索禁用时 search_web 返回 disabled | ✅ | `test_p6_security_boundary.py` |
| Web 搜索禁用时 fetch_web_page 返回 disabled | ✅ | `test_p6_security_boundary.py` |
| Web 搜索禁用时学术搜索不受影响 | ✅ | `test_p6_security_boundary.py` |
| 禁用时行为与 P5 基线一致 | ✅ | 关闭 Web 搜索时仅内部+学术检索路径工作，不触发 Web 路径 |

---

## 5. 已知风险

| 风险 | 缓解 | 严重度 |
|------|------|:------:|
| Web 内容质量不可控 | URL 白名单仅限可信域 + 跨源交叉验证 + 可信度降权 | 中 |
| 迭代搜索成本失控 | 硬限制 3 轮 + budget 双重门禁 | 低 |
| Provider API 变更或下线 | 多 Provider 冗余（P6-01），自动切换备选 | 低 |
| 实时基准数据不足 | 离线 snapshot；`--live` 模式支持实时 API 调用 | 低 |
| Token 开销估计不精确 | 使用 trace counters 估计；实际成本取决于 LLM 定价 | 低 |

---

## 6. 测试覆盖总览

| 测试文件 | 测试数 | 覆盖范围 |
|----------|:------:|----------|
| `test_url_whitelist.py` | 35+ | URL 白名单、IP 拒绝、输入校验 |
| `test_web_fetcher.py` | 20+ | 抓取安全、并发、错误处理 |
| `test_content_safety.py` | 15+ | 内容安全、注入检测、URL 信任度 |
| `test_safety_service.py` | 20+ | 查询清洗、注入拦截 |
| `test_p6_security_boundary.py` | 17 | 安全边界综合验收 |
| `test_web_search_e2e.py` | 12 | 端到端集成验收 |
| `test_agentic_search_loop.py` | 20 | 迭代搜索循环 |
| `test_research_aggregator.py` | 16 | 报告生成 |
| `test_retrieval_judge_service.py` | 17 | 评分系统 |
| `test_evidence_cross_validator.py` | 10+ | 交叉验证 |
| **总计** | **170+** | **全链路覆盖** |

---

## 7. 验收结论

P6 第五阶段全部 5 个任务（P6-18 ~ P6-22）已完成验收：

- ✅ 安全边界 100% 覆盖
- ✅ 功能集成全链路验证
- ✅ 性能基准框架就绪（离线模式可用，`--live` 可触发实时 API）
- ✅ 回退安全 Web 搜索禁用时行为与旧版一致
- ✅ 170+ 测试用例全通过

**验收结果：通过。** 离线 snapshot 数据不足以验证实时基准目标，建议在有 API Key 配置的环境中运行 `--live` 基准获取精确指标。
