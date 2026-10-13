# 最终离线验证与恢复

在仓库根目录 `D:\aiproj\ai_project` 的PowerShell执行。以下只运行离线校验，**不是新模型案例授权**。探测脚本拦截DeepSeekLLM Provider边界，使用合成响应，不保存任务或修改索引。

```powershell
Get-Content -Raw -Encoding utf8 docs\stage2-evidence\probe_grounded_reading_v6.py | docker exec -i -w /app ai_service_python python - *> docs\stage2-evidence\stage4-grounded-v6-final-input.log
$LASTEXITCODE

docker exec ai_service_python python -m pytest tests/test_evidence_quotes.py tests/test_grounded_critique.py tests/test_grounded_comparison.py tests/test_conversation_capabilities.py tests/test_comparison_measurements.py tests/test_critical_focus.py tests/test_citation_responses.py tests/test_deep_analysis_errors.py tests/test_research_synthesis.py -q *> docs\stage2-evidence\stage4-grounded-v6-final-tests.log
$LASTEXITCODE
```

两次退出码均应为0。探测的`GROUNDED_READING_V6_JSON=`记录必须核对：两式γ和V_norm及T定义可见，已核对主表/硬件进入输入，范围保持，合成数字校验通过，索引数量662不变。失败时保存原日志，修复后再运行离线检查，不能自动执行真实模型案例。

注意：`stage4-grounded-v6-runtime.json`来自修复前的中间探测，最新判据更强，不可沿用其绿色检查作为最终证明。最新代码已提交bf90fc7；审批恢复后最终验证通过，并在活动生成任务为0时重启加载。

通过后应明确拆分提交代码与验收证据；仅在实际确认生成任务均为空闲后重启AI服务。已有v5失败收据、旧笔记和成果不得覆盖。阶段4整体验收仍要求修复后的真实内容核对，A18独立客户端及A20真实新手观察保持原要求。

2026-10-09恢复结果：上述两条命令均退出0，147测试与17子测试通过，最终探测8项检查通过。实际证据见`stage4-grounded-v6-final-runtime.json`和两份final日志。无新增Provider请求。上述命令保留作为可复核记录，无需重复执行。
