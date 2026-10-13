# 持续学习接口（2026-10-04 草案）

实现路径：Python `/adaptive-learning/start`、`/adaptive-learning/action`，由 reading_router 注册。浏览器必须经 Java `/api`，不得直连 Python。旧 `/socratic-session/*` 保留；新链不得借用旧固定五题结束语义。

状态是 JSON，可完整保存为任务的 `activeActivity`。Python 没有进程内会话缓存。Java 必须从服务端已保存活动加载 state，检查任务归属及 expectedRevision，以 CAS 保存响应；不能将未经核验的浏览器 state 当作权威掌握记录。Python 自身只验证所传 state 与 taskId/activityId/revision 一致，不能代替服务端授权和并发锁。

## 开始

`POST /adaptive-learning/start`

```json
{"taskId":"T", "pdfId":"A", "mode":"read", "goal":"理解位置优化的监督信号和假设"}
```

mode 为 read/quiz。使用已有受论文 ID 限制的融合检索与受保护 LLM 生成与论文目标相关的概念问题，概念数由原文决定。没有原文返回 422，没有可用计划返回 422，Provider 故障返回 503，均不伪造成功状态。

响应含 `state, message, question, sources, evaluation, suggestedAction, completionSuggested, unresolvedConceptIds`。state 含 schemaVersion=1、activityId、taskId、pdfId、paperIds=[pdfId]、primaryPaperId=pdfId、mode、goal、status、revision、concepts、currentConceptId、turns、evidenceSnapshot、finishReason。三个论文字段必须一致，动作会拒绝不一致的活动快照。concepts 含 id/label/question/status/missingAspects/attempts，status 为 pending/needs_review/demonstrated/skipped。

## 动作

`POST /adaptive-learning/action`

```json
{"taskId":"T", "activityId":"saved-activity", "expectedRevision":0,
 "action":"answer", "text":"我的解释", "state":"用完整保存的 state 对象替换此占位"}
```

| action | 行为 |
| --- | --- |
| answer | 根据固定 pdfId 原文评价答案。partial/incorrect 保留当前概念，缺口用于下一次检索、提示与补课；demonstrated 才推进其他待检验概念。 |
| hint | 根据当前问题和缺口给针对性提示；不改变概念位置，不新增作答次数。 |
| remediate | 根据缺口讲解前置知识；返回原问题继续作答。 |
| ask | 临时术语或相关问题，text 必填；回答后仍保留活动论文和当前概念。 |
| retry | 保持当前题重新作答；可将 text 设为已保存 concept id，回到此前跳过或其他概念。 |
| skip | 标记 skipped，转下一个 pending/needs_review；跳过始终属于 unresolved。 |
| pause | status=paused，保存当前对象和问题。 |
| resume | 从 paused 恢复为 active。 |
| finish | 用户明确结束；finishReason=user_requested，不把未作答或跳过概念当作掌握。 |

所有成功动作 revision 增加 1，并追加 turns。结束状态拒绝继续修改，暂停时仅支持 resume/finish；对象/版本冲突为 409。任何模型/检索故障不会修改传入状态，调用方可在原 revision 重试。阅读器焦点不能覆盖 state.pdfId；草稿恢复成新任务时必须同时更新 taskId/activityId 并保留 pdfId/currentConceptId，paused 状态可以 resume。

检索质量不足、没有原文、模型评价没有可核验 sourceId+原文逐字 quote，answer 返回 unassessable，不能判用户错。demonstrated/partial/incorrect 由 LLM 判断解释关系和条件，不用答案词数或题数。引用逐字验证只证明来源存在，不等同自动证明语义判断完全正确，真实 Provider 教学质量仍需验收。

所有已规划概念得到 demonstrated 时只设置 completionSuggested=true；活动仍 active，必须 finish 才结束。跳过/保存 AI 回答/提示次数均不形成掌握依据。当前实现的计划覆盖仅限 start 检索证据，不宣称已经评估论文所有内容。

## 验证边界

前端请求超时或返回冲突时，会尝试读取服务端最新任务并核对活动；不会自动重试模型调用。读取失败时明确提示状态待核对，用户可通过“刷新活动”再次读取。该行为不等同于后台中途取消，当前学习生成仍待增加可持久化取消机制。

`tests/test_adaptive_learning.py` 覆盖弱证据不能判错、跨论文过滤、假引用拒绝、缺口进入提示、错答不推进、五次不结束、暂停恢复/临时问答、跳过重答和冲突。属于离线测试，使用 mock 的模型和检索结果；Java 持久恢复、真实 Provider 和浏览器全链需另行验证。
