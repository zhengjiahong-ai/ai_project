# 阶段 1 验收：任务数据与执行可靠性

2026-10-05。结论：阶段 1 的四项开发要求、交付物与可靠性门槛通过。完整产品重构继续按阶段 2—7 推进。本报告不代表 A01—A20 全量通过。

## 要求与证据

| 阶段 1 要求 | 实现和实际验证 | 可复核证据 |
| --- | --- | --- |
| 共享任务、材料、活动、成果、来源契约；服务端严格校验材料归属 | 两份 JSON Schema、Python 学习状态 schema；Java 根据服务端任务生成范围和活动快照，普通 PUT 不能替换活动、执行历史或请求应用记录。实际任务及 7 条执行收据通过 Draft202012Validator。任务外材料、主论文超出选定范围、未授权外检均返回 400；任务外文件返回 404 | `contracts/task-workspace.schema.json`、`contracts/task-operation.schema.json`、`ai-service-python/schemas/adaptive_learning.py`；`stage1-evidence/current-contract-payload.json`、`final-runtime.json`、`conflict-runtime.json` |
| 统一请求身份、状态和冲突；创建超时后查询、重提不重复创建 | 浏览器提交前写请求意图；Python SQLite 持久化请求；Java 行锁原子应用状态、消息和 appliedRequestIds。实际断开 HTTP socket、不读取响应，再查询和重提原 ID，只有一次活动转换及一条结果消息。研究重复提交只保留一个子任务及绑定；创建提交窗口的崩溃恢复有测试 | `lost-response-runtime.json`、`learning-start-runtime.json`、`research-cancel-runtime.json`；`test_task_operations.py`、`useTaskLearning.test.jsx`、`useTaskOperations.test.jsx` |
| 学习取消、历史与恢复；研究停止实际等待工作退出 | 真实学习和研究分别观察 cancelling → cancelled；取消学习不改原活动及对话。浏览器暂停、刷新、继续后保留原问题，历史默认折叠。研究未保存计划时恢复返回 409；已保存计划的恢复沿用子任务并跳过完成项。8 个并发计划确认只调度一个工作线程 | `learning-cancel-runtime.json`、`research-cancel-runtime.json`、`final-runtime.json`、`final-browser.jpg`；`test_research_execution_lifecycle.py` |
| 刷新、重启、断网、迟到响应、并发编辑；失败草稿可找回 | 实际 Java/Python 重启后保留任务、文件、活动和收据。另以 127.0.0.1 来源建立独立浏览器缓存恢复 PDF 与活动。Java 停止后保存失败、刷新恢复草稿、重启再保存成功。双客户端编辑时既拒绝过期任务 revision，也阻止后台刷新后旧编辑正文覆盖新正文；完整冲突草稿保留，用户可核对后明确提交 | `restart-runtime.json`、`material-runtime.json`、`independent-client.jpg`、`offline-draft-runtime.json`、`offline-draft.jpg`、`concurrent-editor-runtime.json`、`concurrent-editor.jpg`；`UnifiedTaskApp.test.jsx`、`taskWorkspaceRemoteStore.test.jsx` |

证据文件未另写路径的均在 `docs/stage1-evidence/`。

## 关联验收门槛

- **A05 材料严格约束：** 检索负例测试排除任务外高相似度材料；研究范围及服务端归属的实际拒绝记录见 `final-runtime.json`。六种能力的真实回答范围和教学质量在阶段 2—4 全量验收。
- **A06 阅读焦点与活动对象独立：** 实际浏览器先打开 A，再点击 B 的来源按钮，继续学习后 readerPaperId 为 B、活动及材料快照仍为 A。证据为 `citation-focus-runtime.json`、`focus-runtime.json`。此用例使用同一 PDF 的两个存储身份，引用消息明确标为验收 fixture；证明身份隔离和实际点击链路，不证明多论文语义质量。
- **A07 迟到响应与任务切换：** 浏览器发出继续学习后立即切到空任务，原活动继续、空任务内容不变，见 `switch-runtime.json`。延迟响应、卸载后响应、任务移除及迟到错误的自动测试补足确定性时序；错误按所属任务展示。
- **A12 取消、恢复与重启：** 上表的真实 Provider/HTTP 取消和重启记录；`test_research_process_recovery.py` 使用两个独立 Python 进程与真实 SQLite，第一进程在保存首个结果后以 exit(23) 硬退出，第二进程显式恢复；首个问题只执行一次，剩余问题只执行一次，重复恢复只调度一次。模型输出受控，此证据验证进程恢复，不验证报告质量。恢复新建执行 trace，避免引用已随进程消失的内存 trace。
- **A18 服务端权威与缓存一致：** PDF 文件 SHA-256 与原上传一致；独立来源缓存恢复通过。旧缓存在已有服务端副本时采用权威文件及分析，旧副本在同一事务中备份，标注保留；未能同步时保留可读缓存并提示。
- **A19 文档与兼容边界：** `API.md`、`docs/CONSTRAINTS.md`、`STAGE1_EXECUTION_CONTRACT.md` 与两份共享契约同步；真实研究外检关闭，显式未经授权开启被拒绝。旧记录和旧入口保留，不自动启用外部工具。

## 最终验证

- Python 两组不重叠的阶段相关测试：51 + 37 = **88 通过**，含真实进程崩溃恢复测试；测试命令见下方。
- 前端 `npm test`：脚本 smoke checks 全部通过，Vitest **28 文件、159 测试通过**；`npm run typecheck`、`npm run build` 通过。
- Java 当前 Surefire 报告：TaskWorkspace/TaskLearning/TaskResearch/TaskMaterial/TaskOperation 五类接口 **24 测试通过**。本轮未改 Java；报告时间为 2026-10-05 22:28—22:44，当前运行 jar 来自对应修复后的构建。
- Python 容器已重启使用最新恢复修复，`/health` 的 GROBID、RAG 检查通过。最终浏览器显示服务端保存正文、历史版本、原学习问题和收束的来源，无旧缓存备份失败提示。

```powershell
# 在 ai-service-python 目录运行
..\.venv-refactor\Scripts\python.exe -m pytest tests/test_task_operations.py tests/test_research_task_service.py tests/test_research_execution_lifecycle.py tests/test_research_process_recovery.py tests/test_research_material_scope.py tests/test_chat_scope_resolution.py tests/test_task_scoped_retrieval.py -q
..\.venv-refactor\Scripts\python.exe -m pytest tests/test_chat_exhaustive_retrieval.py tests/test_adaptive_learning.py tests/test_reading_chain_contracts.py tests/test_route_service_contracts.py -q
# 在 frontend 目录运行
npm test
npm run typecheck
npm run build
```

## 后续阶段的剩余产品工作

阶段 0 的 B09 草稿发现和 B10 文件跨客户端恢复已在本阶段处理。同步上传仍等待全文分析；阅读就绪与可选分析分离、上传状态呈现继续在阶段 2 完成。旧提示措辞、窄屏、目录质量属于阶段 6；导出和全量旧数据迁移属于阶段 5。六能力效果、真实不同论文分析、研究报告质量及新手观察仍按原计划验收。本阶段不以这些尚未完成的功能声明完整产品可正式切换。
