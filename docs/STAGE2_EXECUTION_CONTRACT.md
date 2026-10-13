# 阶段 2：统一能力执行与恢复契约

状态：阶段 2 已验收，见 `STAGE2_ACCEPTANCE.md`。与阶段 1 契约一起使用；能力内容质量按阶段 3、4 继续验收。

## 统一入口

浏览器向 Java `POST /api/task-workspaces/{taskId}/operations` 提交 `{requestId,kind,input}`。

| kind | 用途 | 关键参数 |
| --- | --- | --- |
| conversation.execute | 问答、补课、批判、比较、有限组合 | capability、message、allowedPaperIds、primaryPaperId、strictScope、expectedTaskRevision；compose 另有 steps |
| learning.start | 精读、自测 | pdfId、mode(read/quiz)、goal、expectedTaskRevision |
| learning.action | 回答、提示、补课、跳过、暂停、继续、结束 | activityId、expectedRevision、action、text、expectedTaskRevision |
| research.start | 创建研究计划 | question、allowedPaperIds、pdfId、expectedTaskRevision；外部检索关闭 |

Java 以当前任务材料、活动和已确认对话重新构造调用快照。浏览器不能上传内部活动 state 或伪造历史。请求 ID 与原参数一起去重；原材料快照不会随任务后续编辑扩大。

六个命令和自然语言共用这些路径。综合组合仅允许二至三个不同的 chat/background/critique/compare 步骤；研究有独立的计划确认与执行生命周期，不能隐式混入组合。歧义选择在提交前完成。

## 公共结果

新结果满足 `contracts/capability-result.schema.json`：resultVersion=1、status、capability、message、sources、sentenceSourceMap、materialScope、steps、artifact。原专业能力的 state/question/evaluation/task 等继续作为兼容附加字段。

message 用于对话中的可用短结果；artifact.text 保存完整正文，paperIds/sources 与结果快照一致。来源的 pdfId 归一到原任务材料 ID。材料级来源清单不自动成为句级证明；缺少句级映射时不能声称每句话已验证。长学习解释和对话成果在 Java 事务中与消息一起保存，重复轮询不重复发布。

研究状态通过 `/research/{researchId}` 和 plan-review/final-review/resume/cancel 读取或操作。响应保留原研究 task，另返回公共能力字段和已确认 workspace。succeeded 的终稿由 Java 原子发布；前端只采用 workspace，不自行追加整份报告。对话短结论关联 artifactId；完整报告在中栏编辑。重复查询不会覆盖用户修改。

## 停止、重试和冲突恢复

公开收据见 `contracts/task-operation.schema.json`。unknown 是浏览器的未确认状态，不能解释成服务端未执行。GET 原请求身份用于确认；停止 POST `/operations/{requestId}/cancel`，可附 `{kind,input}`，允许原执行提交尚未到达时预留取消记录。刷新保留 cancelRequested，不能重发为普通执行。

POST `/operations/{requestId}/retry` 只允许 failed/interrupted/cancelled。服务端生成固定重试身份，重复提交同一原请求只形成一次重试，保留原材料和活动问题版本，并重新检查当前权限。公开 request 仅包含用户意图白名单，排除 Provider 输入、history 和内部 state。

conflicted 表示结果已生成，但不能采用到当前任务。中栏可以查看原结果，禁止付费重跑。POST `/operations/{requestId}/recover-result` 从服务端原收据恢复 conversation.execute/learning.* 的文字成果，不接受浏览器提供的正文或状态。原材料必须仍属于任务，来源必须属于原快照；缺材料返回 409，不产生部分消息或成果。显式恢复保留当前学习位置，不将旧 state 应用到新活动；重复恢复和后续轮询均不重复保存。research.start 是计划创建记录，其最终报告采用研究发布路径。

## 验证范围

逐项证据与限制见 `STAGE2_ACCEPTANCE.md`，批次历史见 `STAGE2_EXECUTION_PLAN.md`。公共适配、停止预留、恢复去重和原子发布有自动测试；真实 HTTP 和浏览器已验证上传分离、失败重试及批判冲突结果查看/恢复。四种材料范围、六能力公共协议、不同论文比较、研究终稿发布与两步组合均有真实记录，运行容器也已加载新摘要逻辑。入口和持久化成功不等于教学、分析与研究内容质量达标，相关质量门槛仍属于阶段 3、4。
