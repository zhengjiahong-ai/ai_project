# 阶段 1：持久化执行协议

状态：阶段 1 已验收，逐项证据见 `docs/STAGE1_ACCEPTANCE.md`。JSON 契约见 `contracts/task-operation.schema.json`。

浏览器调用 Java `/api/task-workspaces/{taskId}/operations`，提交 `{requestId,kind,input}`。kind 为 `learning.start`、`learning.action`、`research.start`。input 沿用各能力参数与 expectedTaskRevision。Java 根据服务端任务重新验证材料和活动，把不可变快照提交给 Python；浏览器的学习 state 不作为执行依据。

提交前浏览器按请求 ID 备份意图；网络响应未确认时，刷新沿用同一 ID 查询或提交。同一 ID 和同一参数返回同一记录；不同参数复用同一 ID 返回 409。请求记录独立于浏览器连接保存在 Python 的 `task_operations.sqlite3`，默认与研究数据库同目录，使用 Compose 的研究数据卷。

GET `/operations` 或 `/operations/{requestId}` 返回执行状态；POST `/operations/{requestId}/cancel` 请求停止。queued 可直接停止；running 转为 cancelling，执行器退出后才是 cancelled。Provider 边界检查取消，防止后续调用；已被外部 Provider 接收的单次请求不能宣称已从 Provider 服务器撤回。

服务启动时 unfinished 请求转为 interrupted，保持结果不确定的事实，不自动重复可能已发生的收费调用。succeeded 结果重启后仍可取回。Java 使用行锁合并结果到原任务，同时写学习状态、历史和对话，并记录 appliedRequestIds；重复查询不重复追加。普通笔记更新可与执行结果合并，活动或材料发生冲突时结果留在请求记录，返回 conflicted，可恢复材料后重新查询。

浏览器普通任务更新不能替换服务端 activeActivity、activityHistory、researchRuns 或 appliedRequestIds。导入/恢复副本中的活动只作为导入记录保留，不直接冒充已验证的可执行会话。当前活动可在刷新、Java 重启后继续；历史以折叠区域展示。

研究创建使用服务端生成的 operationKey 定位持久化子任务。若研究已创建、请求记录尚未完成就发生崩溃，重启按同一标识找回研究并绑定，避免丢失关联；若请求原本正在取消，则保留取消意图。恢复创建记录成功只表示创建已确认，研究执行本身可能处于 failed，不表示研究报告已完成。

研究执行中取消先显示 cancelling，工作线程退出后才显示 cancelled。显式 POST `/api/task-workspaces/{taskId}/research/{researchId}/resume` 沿用原研究，跳过已保存完成的问题；重复恢复不重复调度。恢复和计划确认都校验原材料仍属于任务。没有保存计划时返回 409，须显式发起新请求；服务重启不自动调用模型。

2026-10-05 离线验证：Python 操作、研究生命周期和既有研究服务共 38 测试通过；Java 四类任务接口原有 19 测试通过，新增恢复归属/材料用例后的研究接口 6 测试通过；前端相关 7 文件 30 测试通过，typecheck 与 build 通过。覆盖持久化创建窗口、取消中的重启、并发创建去重、真实工作线程取消等待、恢复跳过已完成部分及过期前端轮询。测试使用受控模型替身，不作为真实 Provider/浏览器验收证据。

2026-10-05 后续验证：服务端增加论文文件和解析结果持久化、任务归属读取、内容标识上传去重、旧缓存事务导入。Java 任务/材料接口 23 测试通过；材料缓存、统一界面和材料范围前端 21 测试通过；typecheck 通过。共享任务契约补于 `contracts/task-workspace.schema.json`。

Docker 失效运行时端点已备份为 stage1-backup 后恢复；没有重置或删除数据卷。真实上传、取回的 PDF SHA-256 一致，解析结果完全一致，重复上传 0.031 秒复用原结果。真实学习启动成功，同标识重复提交未追加重复对话；取消经过 cancelling 后到 cancelled，活动与两个任务对话均未改变。Java 与 Python 实际重启后任务、活动、文件校验和请求记录保持一致。证据见 `docs/stage1-evidence/`；重启前任务快照来源为学习成功收据，取消用例另行确认后未改变该快照。上述是真实 Provider/HTTP 证据，不等于浏览器交互验收。

浏览器验收：统一界面恢复论文和学习活动，暂停后刷新保留原问题与继续入口。另以 127.0.0.1 来源打开独立 IndexedDB/localStorage 客户端，成功取回服务端 PDF 和暂停活动，截图为 `docs/stage1-evidence/independent-client.jpg`。这是独立来源缓存，不声称换了浏览器用户配置。实际并发保存旧版本返回 409，已保存笔记和活动保留；任务外文件读取返回 404。Draft202012Validator 验证真实任务和三条执行记录通过。

整体回归：Python 阶段1相关 60 测试通过；前端 npm test 的 28 文件 153 测试通过，构建通过。随后实测两客户端频繁查询耗尽限流，研究创建返回 503：已降低空闲/后台轮询频率，并透传上游 429，未关闭限流。另外修复含冒号、中文任务 ID 的重复 URL 编码。新增 Java 编码/限流与前端轮询频率测试通过；最新修复仍须实际重试研究链路。学习按钮动作的英文记录已改为中文，截图保留修复前状态，不用于证明最新措辞。

最新运行复验：降低轮询频率后，研究创建、取消（cancelling → cancelled）与同标识重提通过，始终只保留一个子研究和任务绑定，外部检索关闭。含冒号、中文的任务经 Java 正确取回 Python 执行记录；该编码用例用无效能力参数确保不调用模型，仅证明路由。证据分别为 research-cancel-runtime.json、encoding-runtime.json。

最终补验：实际引用点击后活动对象保持原论文，任务切换不串响应，断线刷新后草稿恢复，双客户端旧编辑草稿不覆盖最新正文。跨进程研究在保存首个结果后硬退出，重启显式恢复仅执行剩余问题；执行 trace 在恢复时重新建立。另修复有历史收据时请求意图筛选访问未初始化变量的问题，并隔离迟到错误所属任务。阶段相关 Python 88 测试通过；前端 159 测试、类型检查和构建通过。详细证据及限制以阶段验收报告为准。
