# 数值绑定开发记录（未验收）

2026-10-09。上轮条件显示修复仍在工作树，本轮继续实现 v6 原始响应所暴露的数值合同问题。没有执行额外真实模型生成，没有修改已保存译文、笔记或验收收据。

## 实现

新增 `services/grounded_numeric_rendering.py`，提供批判和比较共用的生成指令与发布前核验入口。

- 数值占位符与绑定身份一一对应。实验数字不再由模型在正文和 value 字段重复填写。
- 服务端从已核对表格的结果行、数据集组及指标列计算原值、差值和比值；同源基线、硬件及完整行引用仍由现有数值校验核对。
- 舍入使用同一计算结果；差值的升降方向由带符号结果生成。默认差值保留单元格精度，比值默认两位；不能用低精度把非零变化显示成零。
- 每个实验值带数据集身份，重复的硬件/基线条件合并显示。
- 方法参数和作者文字主张须来自本条选中的连续原文摘录；表格数字不能归入这两类。方法参数要求定义语境，拒绝明显性能指标。作者主张保留原文比较符、范围、单位及同摘录的其他数量条件，不据此生成同条件比较。
- `evidence_quotes.resolve_references` 恢复绑定的 quoteId 和条件引用；`grounded_critique`、`grounded_comparison` 已接入共同入口。
- 历史 measurements JSON 仍经过原有严格校验，不自动改写成成功结果。没有 numericBindings 的占位符拒绝发布。

新增 `tests/test_grounded_numeric_rendering.py`：包含舍入、方向、多数据集、条件合并、绑定身份、错误基线/数据集/论文、未核对表格、方法参数与性能混淆、科学计数法、作者比较符/分辨率遗漏，以及批判和比较实际入口的模型替身测试。模型替身测试不属于真实模型质量验收。

## 当前验证边界

首次六文件回归通过自动审批并实际执行 Docker 命令，但 Docker 引擎命名管道不存在，pytest 没有启动；原始错误见 `stage4-numeric-bindings-v7-tests.log`。本轮不能继续以“审批额度用尽”作为这个实际执行失败的原因。

现有 Docker Desktop 的后台启动已尝试，后续引擎探测仍失败。没有删除或重建容器、镜像、卷、数据库，没有修改 Docker 配置。正在通过官方 `docker desktop start --timeout 60` 核对启动；最终结果须另补记录，不能将获得进程 ID 当作恢复成功。

上述为首次容器尝试的边界。随后使用项目已有 `.venv-refactor` 离线环境运行同六个文件：首次 **3 failed / 118 passed**，其中一项发现未绑定 `999FPS` 漏检，另外两项因该虚拟环境缺少项目已声明的 PyPDF2。修复数值正文漏检，并在此虚拟环境补齐 PyPDF2 3.0.1 后，最终 **121 passed / 1 warning**。警告是 PyPDF2 废弃提示。保存初次与最终日志为 `stage4-numeric-bindings-v7-local-tests.log`、`stage4-numeric-bindings-v7-local-final-tests.log`；最终命令设置 UTF-8 输出，初次 Windows 编码乱码保留原样。

本地测试的现有夹具阻断真实 LLM 网络出口并隔离缓存；结果只证明这些单元/入口测试，不替代容器、真实模型或浏览器质量验收。已拆分提交：`cc4cf56` 条件显示修复、`1af8e18` 数值绑定合同。旧 84 项日志保持中间版本身份。

Docker 日志随后证实相同损坏端点：`initializing Inference manager` 无法移除 `Docker/run/dockerInference`。在核对 Docker 进程已停止后，从现有 Ubuntu-24.04 读取三个明确运行时端点，均为零字节文件；`backup_docker_runtime_endpoints.py --backup` 校验解析目录及文件类型后原地改名备份。记录 `stage7-docker-endpoint-backup.log`。没有删除数据、递归操作或修改 Docker 配置。再次后台启动后的引擎和服务结果须继续独立核对。

## 最终验证与运行状态

- Docker Engine 29.1.3 已恢复；既有 Python/GROBID 容器自动恢复，本轮没有重建镜像/卷或操作其他项目容器。实际容器同六文件先121项通过，随后补PSNR显示dB与批判结果去重，最终 **122 passed / 2 warnings**。警告为既有PyPDF2及python_multipart废弃提示。日志 `stage4-numeric-bindings-v7-container-tests.log` 与 `stage4-numeric-bindings-v7-container-final-tests.log` 保留各自版本身份。
- `verify_numeric_bindings_input.py` 从实际当前索引只读完整行与硬件摘录，用受控合成绑定检查17.38/17.32倍、PSNR下降0.27/0.22 dB，两数据集绑定、条件合并及错误条件拒绝，共8项检查通过。55个LightGaussian片段，版本 `2977684d0da4a8b6`，全库662片段；文档和元数据前后SHA-256相同。最后日志 `stage4-numeric-bindings-v7-index-final-verified.log`。此范围不证明真实模型会产生合格绑定。
- 该检查脚本前两次在片段选择断言处停止，日志 `stage4-numeric-bindings-v7-index-input.log`、`stage4-numeric-bindings-v7-index-input-final.log` 保留失败；随后按可见完整方法/星号基线行选取主表，才取得通过记录。不是篡改表格数字或引用，也不把文件名中的final当成通过证据。首次通过后观察到PSNR显示缺少dB，修复并复跑最终检查；此前输出仍保留。
- `ecd8919` 提交PSNR显示单位与批判去重。通常前三条结论仅显示一次，额外结论折叠，原文依据继续折叠。新单位测试和去重断言均在最终122项回归中执行。
- 本地Java/Vite已在原端口8081/5173后台恢复，Java日志证实继续使用 `backend-java/target/stage0-data/academic_db`。完整阅读任务GET与v6保存快照逐字段相同，revision17、前后哈希一致，记录 `stage7-numeric-v7-task-preservation.log`；不只凭文件存在或版本号证明内容保留。
- 权威生成库检查确认无运行中生成任务后，重启本项目Python加载最终源码；`stage7-numeric-v7-final-health.json`证明Python/GROBID/RAG正常、前端200及原任务revision17。没有新增模型案例。

这一批完成数字合同的离线开发与运行加载验证，尚未完成A11真实质量、A14翻译/新导出、A18独立浏览器、A20真人观察，阶段4–7继续未通过。

```powershell
docker exec -e PYTHONPATH=/app ai_service_python pytest -q tests/test_comparison_measurements.py tests/test_grounded_numeric_rendering.py tests/test_grounded_comparison.py tests/test_grounded_critique.py tests/test_evidence_quotes.py tests/test_pdf_table_columns.py
```

仍需使用真实索引构造有明确边界的离线输入检查；不能把手工转换 v6 旧 JSON 当成真实生成成功。方法参数识别和作者主张语义仍有有限规则边界，真实模型是否遵守新合同尚未验证。翻译语义、实际新 HTML 下载、独立浏览器和真人新手观察不由本轮数值修改完成。A11/A14/A18/A20 及正式入口切换门槛保持未通过。
