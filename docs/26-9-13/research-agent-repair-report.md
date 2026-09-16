# 研究 Agent 返修交付

日期：2026-09-13

## 返修结论

批次 1 的接口统一问题已完成返修，后续批次 2–6 也已接入产品主链。最终验证不是只看单元测试：两篇真实 PDF 经 Java `/api/upload` 进入页码索引，再通过 Java `/api/agent-*` 接口创建项目、自动执行研究、读取消息/时间线/证据/报告，并完成取消、重启和重试。

## 本轮评审发现并修复的问题

1. 单次宽泛检索每篇只取 3 条，中文问题配合英文嵌入模型容易命中参考文献页。改为三维度英文检索，每篇最多 6 条且跨论文均衡。
2. DeepSeek 在 JSON 外附带说明文字时，原解析器把有效回答判为失败。改为从响应中解析首个完整 JSON 对象，同时继续执行严格字段和 sourceId 校验。
3. 服务重启后还原 Run 快照遗漏 `conversationId`，导致 retry 错建 Research Task。还原时从持久化 Run 的 `taskId` 恢复会话归属，并增加“重载后重试”测试。
4. retry 会把原用户问题再次写入消息表。retry 现在只更新 Research Task 的 `latestRunId`，不重复创建用户消息。
5. 清理两个前端文件的尾部空行，使 `git diff --check` 通过。

## 干净双论文样例

输入论文：3DGStream 与 A Survey on 3D Gaussian Splatting。

| 项目 | 结果 |
|---|---|
| projectId | `324d50ec-764f-4473-85cd-d8063b38cabf` |
| taskId | `e92eb533-c74a-47a6-aba3-3dd9571d60a8` |
| runId | `1857fc41-894d-45cc-b4b7-e52dda9d50fa` |
| 状态 | `succeeded` |
| Research Task / Message | 1 / 2（user, assistant） |
| 研究链 | 12 步 |
| 证据 | 12 条，覆盖 2 篇论文 |
| 页码 | 12/12 可定位 |
| 伪证据 | 0 |
| 综合结论 | 5 条 |
| 报告引用 | 12 次，未知引用 0 |

完整结果：[clean-two-paper-demo.json](./clean-two-paper-demo.json)

## 运行控制样例

- 幂等：同一任务、同一幂等键的两次 POST 返回同一 `runId`，第二次响应 `deduplicated=true`。
- 取消：运行进入 `cancelled`。
- 重启恢复：Python 服务重启后，retry 返回新的 `runId`，`taskId` 保持为原研究任务。
- 重试完成：retry Run 最终进入 `succeeded`，证据仍覆盖两篇论文且页码完整。

## 验证命令

```text
docker compose exec -T ai-service pytest -q tests/test_agent_orchestrator.py tests/test_agent_project_service.py tests/test_agent_grounded_answer.py tests/test_pdf_evidence_pages.py tests/test_rag_service.py tests/test_evidence_credibility.py
# 78 passed

docker run --rm -v "D:\aiproj\ai_project:/workspace" -w /workspace/backend-java maven:3.9.6-eclipse-temurin-21 mvn -q test
# 37 passed

cd frontend
npm.cmd test
# 17 scripts passed; 10 files / 78 Vitest tests passed

npm.cmd run typecheck
# passed

npm.cmd run build
# built successfully
```

## 主要产物

- 上传结果：`upload-3dgstream.json`、`upload-survey.json`
- 干净样例：`clean-demo-project.json`、`clean-demo-run-created.json`、`clean-two-paper-demo.json`
- 多轮与证据验证：`turn3-artifacts.json`、`turn3-messages.json`、`turn3-timeline.json`
- 运行控制：`idempotency-cancel.json`、`retry-after-restart-created.json`、`retry-after-restart-final.json`
