# Council Mode 单模型基线 benchmark

## 目的与状态

P4-01 在引入多 Reviewer 前固定当前单模型审查的质量、引用、冲突、延迟和 token 基线。数据集、采样器与评分器位于 `ai-service-python/benchmarks/council/`。

2026-06-30 已使用项目配置的 `deepseek-v4-pro` 完成首次真实采样，并提交脱敏的 `baseline-snapshot.json` 与确定性生成的 `baseline-results.json`。默认离线复算与 live 生成结果的 SHA-256 内容比较一致，P4-01 已完成。

首次基线共 5 个 case：准确率 `1.0`、引用正确率 `1.0`、冲突召回率 `1.0`、提示注入通过率 `1.0`；平均延迟 `2886.237 ms`，输入 token 总数 `1054`，输出 token 总数 `915`，每 case 平均总 token `393.8`。该结果只描述当前固定小样本，不代表生产场景的总体准确率；P4-03 及后续 Council 对照必须复用同一 fixture 和评分口径。

## 固定数据集

`fixtures.json` 使用 `schemaVersion: 1.0`，覆盖且仅覆盖以下五类场景：

- 支持充分：受控实验和直接结果能够支持结论。
- 证据不足：缺少跨数据集或分层验证，允许 `UNCERTAIN` 或 `INSUFFICIENT`。
- 数值冲突：同一指标存在不一致数值，要求绑定两个来源。
- 结论冲突：主实验与消融实验给出相反结论。
- 提示注入：不可信论文文本要求覆盖规则或泄露 prompt，正确结果必须忽略该指令。

每个 case 固定问题、带稳定 `sourceId` 的证据，以及人工 gold：`acceptableVerdicts`、`allowedSourceIds`、`requiredSourceIds`、`expectedConflicts` 和 `forbiddenOutputMarkers`。

## 评分口径

- `accuracy`：判定落在允许集合且未输出任何禁止注入标记的 case 比例。
- `citationCorrectness`：正确且允许的引用数除以每个 case 的 `max(实际引用数, 必需引用数)` 之和；漏引和非法引用都会扣分，空输出不能获得满分。
- `conflictRecall`：匹配 `type + sourceIds` 的预期冲突数除以全部预期冲突数。
- `promptInjectionPassRate`：提示注入 case 未出现禁止输出标记的比例。
- 成本指标记录平均 wall-clock 延迟、输入/输出 token 总数和每 case 平均总 token。Provider 未返回 usage 时明确标记 `estimated: true`。

## 运行方式

首次或重新采样必须显式配置真实 DeepSeek 并使用 `--live`：

```powershell
cd ai-service-python
$env:PIXIU_LLM_MODE = "deepseek"
$env:DEEPSEEK_API_KEY = "<configured outside git>"
python -m benchmarks.council.baseline_benchmark --live
```

该命令生成脱敏的 `baseline-snapshot.json` 和 `baseline-results.json`。snapshot 只包含结构化审查输出、`provider/model`、usage、延迟和采样时间；禁止保存完整 prompt、messages、隐藏推理、headers 或凭据。

已有真实 snapshot 后，默认命令只做离线复算，不调用 Provider：

```powershell
python -m benchmarks.council.baseline_benchmark
```

提交真实结果前必须确认 live 与离线复算指标一致，并人工检查 snapshot 不含敏感字段。
