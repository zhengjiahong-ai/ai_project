# 研究 Agent 实现与演示验收

目标：实现 `research-agent-audit-and-plan.md` 中批次 1–6 的产品主链，并使用 `D:/3dgs/paper` 中的真实论文验证。

## 当前结论

批次 1–6 的产品主链已经实现并通过真实 Java 网关闭环：项目与论文范围、自动研究、Task/Message/Run 分离、连续追问、页码证据、证据约束综合、研究链、刷新与重启恢复、幂等提交、取消和重试均可运行。

## 已实现能力

- 前端只通过项目持久化 Run 接口创建正式研究运行；创建后立即缓存，轮询 fallback 不清空已展示产物。
- `reviewMode=auto` 自动完成计划、项目论文检索、综合与回答；手动审核模式保留兼容。
- Research Task、Message 和 Run 分离并存入 SQLite。任务内追问复用同一 `taskId`，每轮使用不同 `runId`。
- PDF 重新按真实页面正文建立索引，过滤 Front Matter；重新上传会替换旧论文索引。
- 项目内检索按方法与训练、实验与效率、适用场景与局限三个维度执行，并对每篇论文分配均衡证据额度。
- 自动回答只引用实际证据中的完整 `sourceId`；无证据时拒答，模型格式或未知引用异常进入真实失败状态。
- 前端按消息时间显示用户问题和 Agent 回答，每个 Run 的时间线、计划、工具调用、证据与报告可展开。
- 幂等键防止重复创建 Run；运行可取消；失败或取消后可重试，`retryOfRunId` 可追踪。
- 重启恢复会保留 `conversationId`、消息、Run 状态与产物；retry 不重复写入原用户消息。

## 真实双论文样例

论文：

- `D:/3dgs/paper/3DGStream/2403.01444v4.pdf`
- `D:/3dgs/paper/3DGS综述/2401.03890v8.pdf`

干净样例：

- projectId: `324d50ec-764f-4473-85cd-d8063b38cabf`
- taskId: `e92eb533-c74a-47a6-aba3-3dd9571d60a8`
- runId: `1857fc41-894d-45cc-b4b7-e52dda9d50fa`
- 状态：`succeeded`
- 1 个 Research Task，2 条消息，12 步时间线
- 12 条证据覆盖 2 篇论文；缺失页码 0，Front Matter/占位证据 0
- 5 条证据约束结论；报告引用 12 次，未知引用 0

完整响应保存在 `docs/26-9-13/clean-two-paper-demo.json`。

运行控制样例保存在：

- `docs/26-9-13/idempotency-cancel.json`
- `docs/26-9-13/retry-after-restart-created.json`
- `docs/26-9-13/retry-after-restart-final.json`

验证结果：相同幂等键返回同一 Run；取消进入 `cancelled`；服务重启后 retry 仍回到原 Research Task，并最终进入 `succeeded`。

## 自动化验证

- Python Agent/RAG/证据综合定向回归：78 passed。
- Python 最终聚焦回归：63 passed。
- Java Maven 全量测试：37 passed（1 application + 33 controller + 3 contract）。
- 前端：17 个脚本测试通过；10 个 Vitest 文件、78 个用例通过。
- `npm.cmd run typecheck` 通过。
- `npm.cmd run build` 成功；保留的构建警告来自既有依赖与阅读统计模块。
- `git diff --check` 无空白错误。

## 边界

外部学术检索、网页检索、代码执行和辩论属于可选工具能力，仍取决于提供方配置与各自审批策略。项目论文研究主链不依赖这些能力；工具关闭或检索失败时不会生成伪证据。
