# Pixiu 演示检查清单

本文档用于用固定 PDF 建立全链路真实联调与演示基线。它既是演示脚本，也是每次演示前的记录表。若服务、密钥或模型不可用，必须记录为 `BLOCKED`，不要把未执行链路写成通过。

## 1. 环境准备

- 项目路径：`C:\Users\17660\Desktop\codes\ai_project`
- 固定演示 PDF：`docs/中期答辩/中期考核附件材料/原始格式附件（已填写）/Active RIS-Assisted Integrated Sensing and Communication Systems Joint Receive-Transmit Beamforming and Reflection Design.pdf`
- 前端入口：`http://localhost:5173`
- Java API：`http://localhost:8081/api`
- Python API：`http://localhost:8000/api`
- GROBID：`http://localhost:8070`
- 必需本地条件：
  - Docker Desktop 已启动，并且 `docker ps` 能连接 Docker daemon。
  - 根目录 `.env` 存在，且 `DEEPSEEK_API_KEY` 已配置为可用密钥。
  - 端口 `5173`、`8081`、`8000`、`8070` 未被其他进程占用。

## 2. 启动与检查命令

在项目根目录执行：

```powershell
cd C:\Users\17660\Desktop\codes\ai_project
docker compose up --build
```

常用检查：

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker compose logs --tail=120 ai-service
docker compose logs --tail=80 backend
docker compose logs --tail=80 frontend
```

服务就绪标准：

- `paper_frontend` 暴露 `5173`。
- `backend_java` 暴露 `8081`。
- `ai_service_python` 日志出现 `Application startup complete`。
- `grobid_service` 处于 healthy/running 状态。
- 浏览器可打开 `http://localhost:5173`。

## 3. 当前基线记录

记录日期：`2026-06-07`

本次 P0-3 只对齐文档、版本号和运行说明，不重新声明 Docker/API 全链路 smoke 已通过。演示前仍应按第 2 节启动服务，并用第 4 节逐项记录真实结果。

| 检查项 | 当前基线 | 记录要求 |
| --- | --- | --- |
| 版本号 | `README.md` 与 `frontend/VERSION` 对齐到 `0.1.18`。 | 若继续迭代，版本号应跟随 `CHANGELOG.md` 最新记录。 |
| 模型供应商 | 当前文档与环境变量以 DeepSeek V4 为准。 | 不再把 DashScope 写作当前默认模型。 |
| 深度研究持久化 | Python 使用 SQLite 快照，Docker Compose 通过 `research_task_data` volume 保存 `/app/data/research_tasks.sqlite3`。 | 服务重启后只恢复快照，不恢复运行中的后台任务。 |
| Python reload | Dockerfile 默认不启用 `uvicorn --reload`。 | 修改 Python 代码后需要 `docker restart ai_service_python` 或重建容器。 |
| Compose 命令 | 推荐 `docker compose up --build` 或 `docker compose up -d frontend backend ai-service grobid`。 | 旧式 `docker-compose` 只作为本地兼容命令，不作为主文档命令。 |
| 必需环境 | Docker Desktop、可用端口、根目录 `.env`、有效 `DEEPSEEK_API_KEY`。 | 任一条件缺失时标为 `BLOCKED`，不得写成 PASS。 |
| 测试记录 | 前端 `npm.cmd test` 当前包含 13 个脚本入口；Python 最新历史记录为 `133 passed`。 | 以本次真实运行输出为准；未运行则写 `NOT_RUN`。 |

## 4. 历史联调记录

记录日期：`2026-05-20`

| 检查项 | 状态 | 实际结果 | 下一步 |
| --- | --- | --- | --- |
| Docker CLI | PASS | `docker --version` 可用，版本为 Docker 29.4.0。 | 无 |
| Docker daemon | PASS | `docker compose ps` 可连接 Docker daemon。 | 无 |
| Compose 启动 | PASS_WITH_NOTE | `docker compose up -d --build` 超过 10 分钟未返回；随后执行 `docker compose up -d --no-build --force-recreate backend frontend` 成功，并应用当前 `8081:8080` 端口映射。 | 演示前如需全量重建，预留更长时间；普通演示可使用 no-build 启动已有镜像。 |
| 服务端口 | PASS | `paper_frontend=5173`、`backend_java=8081->8080`、`ai_service_python=8000`、`grobid_service=8070`。 | 无 |
| DeepSeek Key | PASS | 问答、解释、翻译、批判阅读、背景补课、苏格拉底学习和 deep research 均成功调用模型链路。 | 无 |
| 固定 PDF 上传 | PASS | 上传成功，`pdfId=active_ris-assisted_integrated_sensing_and_communication_systems_joint_receive-transmit_beamforming_and_reflection_design.pdf`，`ragIndexed=true`，`ragChunkCount=32`，章节数 `12`，耗时约 `145s`。 | 无 |
| 全功能演示链路 | PASS | 通过 Java `http://localhost:8081/api` 完成上传、问答、划词解释、翻译、批判阅读、背景补课、苏格拉底学习和 deep research API smoke。 | 浏览器演示仍建议按第 4 节现场走 UI，并准备第 5 节截图。 |

## 5. 演示步骤与记录表

每次演示前复制本节表格，填入实际输入、输出摘要、状态和耗时。状态只允许使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

| 步骤 | 演示动作 | 固定输入 | 期望输出 | 实际输出摘要 | 状态 | 耗时 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1. 上传与解析 | 点击“上传论文”，选择固定 PDF。 | 固定演示 PDF | 返回 `pdfId`，论文入库，目录/篇章结构出现，`ragIndexed` 为 true 或给出明确索引状态。 | API 上传成功，标题为 `Active RIS-Assisted Integrated Sensing and Communication Systems: Joint Receive-Transmit Beamforming and Reflection Design`，`ragIndexed=true`，`ragChunkCount=32`，章节数 `12`。 | PASS | 约 145s | 通过 Java `/api/upload` 验证。 |
| 2. 篇章目录 | 在左侧目录展开章节，并跳转到第 1 或第 2 页。 | 上传后的当前论文 | 目录树可展开，页码跳转正常。 | 上传响应返回 `paper_structure.sections=12`，可供前端目录渲染。 | PASS | 包含在上传耗时内 | 本轮未用浏览器点击验证跳页，演示时现场确认 UI。 |
| 3. 问答 | 在问答面板提问。 | `这篇论文的核心问题和主要方法是什么？` | 返回中文回答，并展示或携带 `rag_sources` / 证据来源。 | 返回中文回答，概括联合优化收发波束赋形与 RIS 反射设计；`rag_sources=12`，`traceId=9485ba2d-3d9c-444a-a8e8-8216413e0f4c`。 | PASS | 约 50s | 通过 Java `/api/chat` 验证。 |
| 4. 划词解释 | 在 PDF 中选中核心术语并点击 AI 解释。 | `RIS-assisted integrated sensing and communication` | 返回短解释，可同步到问答流，失败时显示可读错误。 | 返回中文解释，说明主动 RIS 辅助通感一体化；`rag_sources=5`，`traceId=8f8a00cd-85cd-43d9-b223-239c3d2128ef`。 | PASS | 约 32s | 通过 Java `/api/explain` 验证。 |
| 5. 逐页翻译 | 切到逐页翻译面板，翻译第 1 或第 2 页。 | 当前页文本、`pdfId`、`paperSkeleton`、页面布局 | 返回中文译文；结构化翻译失败时明确回退或提示超时。 | 返回中文译文，`renderMode=plain`，`blocks=1`。 | PASS | 约 1.5s | 使用第 1 页标题/摘要片段验证 `/api/translate-page`。 |
| 6. 批判阅读 | 打开批判阅读面板并生成分析。 | 当前 `pdfId` | 返回贡献、方法、实验、局限、薄弱点和证据引用；索引异常时显示结构化错误。 | 返回结构化分析，`contributions=1`，`weaknesses=4`，`overclaimRisks=2`，`missingEvidence=4`，`rag_sources=10`，`traceId=b0f76d5e-bd12-4408-9235-43519ab6e7ca`。 | PASS | 约 175s | 通过 Java `/api/critical-reading/{pdfId}` 验证。 |
| 7. 背景补课 | 打开背景补课，知识水平选择“入门”。 | `user_knowledge_level=入门` | 返回学习路径、前置概念、知识图谱、证据覆盖信息。 | 返回 `nodes=8`，`edges=1`，`learning_path_sections=4`，`background_knowledge=8`，`rag_sources=5`，`traceId=09118acf-d58e-465f-8e8c-d9a24fd94aae`。 | PASS | 约 178s | 通过 Java `/api/background-knowledge` 验证。 |
| 8. 苏格拉底学习 | 启动引导学习并回答第 1 题。 | 回答示例：`我理解这篇论文主要关注 RIS 辅助的通信与感知联合优化。` | 返回下一题或评估，包含掌握度、缺失点或提示。 | 启动成功，首题为“这篇论文试图解决的核心研究问题是什么”；提交一次回答后接口返回 `status=success`。 | PASS | 启动约 7.4s；回答约 12.5s | 通过 Java `/api/socratic-session/start` 与 `/api/socratic-session/answer` 验证。 |
| 9. 深度研究 | 创建 deep research 任务并轮询到终态。 | `这篇论文的关键贡献是否有充分实验支撑？` | 返回 `taskId`、可选 `traceId`、阶段、进度、结构化 findings 和报告，或明确失败原因。 | 任务成功，`taskId=fbbbb293-e708-4c7b-bb0c-306a48a24dbf`，`traceId=1798c88b-90ec-4aee-beb9-54bed4d40218`，`status=succeeded`，`stage=done`，`planItems=5`，`findings=5`，有报告。 | PASS | 约 120s | 轮询 15 次到终态。 |

## 6. 备用截图建议

演示前建议准备以下截图，避免现场网络、Docker 或模型问题影响展示：

- 上传完成后的论文库记录，包含标题、页数、章节数或解析状态。
- 左侧真实篇章目录展开状态。
- 问答面板回答及 `rag_sources` / 证据区域。
- 划词解释弹窗或同步到问答流的解释消息。
- 第 1 或第 2 页逐页翻译结果。
- 批判阅读结果，重点展示贡献、方法、实验、局限和证据。
- 背景补课学习路径与图谱区域。
- 苏格拉底学习首题和一次回答评估。
- 深度研究任务成功终态，包含计划、findings 和报告。


## 7. 回归验证命令

前端：

```powershell
cd C:\Users\17660\Desktop\codes\ai_project\frontend
npm.cmd test
npm.cmd run build
```

Python：

```powershell
cd C:\Users\17660\Desktop\codes\ai_project\ai-service-python
python -m pytest tests -q
```

Java：

```powershell
cd C:\Users\17660\Desktop\codes\ai_project\backend-java
.\mvnw.cmd test
```

验证记录：

| 命令 | 状态 | 结果摘要 |
| --- | --- | --- |
| `npm.cmd test` | PASS | 13 个前端 smoke/模型测试脚本入口全部通过。 |
| `npm.cmd run build` | PASS_WITH_WARNINGS | Vite build 成功；保留已知警告：`react-resizable-panels` 的 `"use client"`、`pdfjs-dist` eval 风险、chunk 超过 500 kB。 |
| `python -m pytest tests -q` | PASS | `133 passed in 7.48s`。 |
| `.\mvnw.cmd test` | PASS_WITH_WARNINGS | `30` 个 Java 测试通过；保留 Mockito 动态 agent 未来兼容性警告。 |
