# 阶段 0：真实运行基线

日期：2026-10-05。状态：完成阶段 0；不代表整个重构已验收。

## 运行结论

已通过真实浏览器、当前 Java 后端、真实 DeepSeek Provider、GROBID 和持久化 Chroma 跑通一条论文基本链路：创建任务 → 上传真实论文 → 原文阅读 → 当前论文问答 → 保存成果 → 编辑保存 → 刷新恢复 → 来源跳回原文。Java 与 Python 分别重启后，任务正文和论文索引仍保留。

验收论文为仓库现有的 `Active RIS-Assisted Integrated Sensing and Communication Systems Joint Receive-Transmit Beamforming and Reflection Design.pdf`（`docs/中期答辩/中期考核附件材料/原始格式附件（已填写）/`）。正文 5 页，GROBID 解析，索引 28 个片段。没有使用模拟模型响应。

## 实际运行组合

| 服务 | 本轮实际方式 | 状态 |
|---|---|---|
| 前端 | 当前工作区 Vite，localhost:5173 | 已启动、真实浏览器访问 |
| Java | 当前工作区重新打包 jar，本机 JDK25，8081 | 已启动；文件数据库隔离于 target/stage0-data |
| Python | 现有 Compose 镜像，挂载当前工作区源码，8000 | 健康检查通过；已重启验证 |
| GROBID | 现有 lfoppiano/grobid:0.7.2，8070 | 健康检查与实际解析通过 |
| Chroma | Compose 持久化卷，multilingual-e5-small | 同一论文重启前后均 28 片段 |
| Provider | 配置的 DeepSeek，deepseek-v4-pro，thinking enabled/high | 上传生成与真实问答成功 |

Java 编译目标仍为 release21，本轮运行是 JDK25，构建时覆盖 Lombok 为 1.18.42；不声称已验收 JDK21 运行。没有修改 pom 或原有 Java 数据库，也没有删除 Docker 镜像/卷。

默认 `http://localhost:5173/` 仍为旧应用，真实浏览器可见“阅读 IDE / 研究 Agent”。统一任务界面为 `http://localhost:5173/?unified=1`。正式入口切换仍属于阶段 7。

## 可复现启动

先启动 Docker Desktop，再从项目根目录运行：

```powershell
docker compose up -d --no-build grobid ai-service
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8070/api/isalive
```

本轮复用了已有镜像。新机器没有镜像时按照根目录 Compose 构建；Python 需要完整依赖和嵌入模型缓存，`.venv-refactor` 仅是离线测试环境，不能直接充当本轮运行服务。Compose 为 Python 加载根目录 `.env`，凭证无需写入文档或日志。

第二个 PowerShell 窗口构建并启动当前 Java（本轮已验证的 JDK25 路径如下）：

```powershell
Set-Location D:\aiproj\ai_project\backend-java
$env:JAVA_HOME='C:/Users/Lenovo/.jdks/openjdk-25.0.1'
$env:PATH="$env:JAVA_HOME/bin;$env:PATH"
mvn package '-DskipTests' '-Dlombok.version=1.18.42'
& "$env:JAVA_HOME/bin/java.exe" -jar target/backend-java-0.0.1-SNAPSHOT.jar '--server.port=8081' '--spring.datasource.url=jdbc:h2:file:./target/stage0-data/academic_db;DB_CLOSE_ON_EXIT=FALSE'
```

构建成功不是自动测试通过的声明。验收数据库位于构建目录，后续 `mvn clean` 会删除这套隔离验收数据；原数据库不受影响。不要同时启动占用 8081 的 Compose backend。

第三个窗口启动前端：

```powershell
Set-Location D:\aiproj\ai_project\frontend
npm run dev -- --host 127.0.0.1
```

打开统一入口，创建任务后上传上述论文；问“这篇论文优化的目标和约束分别是什么？用三句话回答。”；将回答加入成果，编辑保存并刷新。展开来源选择第 2 页可返回 PDF。

## 验收证据

| 检查 | 结果与范围 |
|---|---|
| 三栏实际入口 | 真实浏览器可用；导航折叠恢复有效；1440×900 桌面截图 |
| 创建任务与断线提示 | 后端未启动时不误报成功，显示本地草稿未同步；服务启动后创建成功 |
| 上传解析与阅读 | 实际上传成功，原文 5 页显示，论文关联写入服务端任务 |
| 真实问答 | 当前“这篇”问题成功，回答优化目标和五类约束，显示 3 条来源；这是单例链路验证，非教学质量总体验收 |
| 保存与编辑 | 成果 1 条、对话 2 条；最新正文加入验收标记，浏览器刷新后完全一致 |
| 来源跳转 | 成果保留来源，点击 p.2 后阅读页码显示“第 2 / 5 页”；未对所有坐标逐项验收 |
| Java 文件数据库重启 | 完整任务重启前后 JSON 内容与 revision 一致，论文关联/对话/成果最新正文保留 |
| Python 重启 | /health 的 GROBID、RAG 均 ok；同一论文索引仍为 28 个片段 |
| 导出 | 点击下载未收到浏览器 download 事件，也未确认实际文件；保持未验证，不能声称已通过 |

证据目录为 [stage0-evidence](stage0-evidence/)。`restart-check.json` 保存完整任务重启对账，`python-health-after-restart.json` 保存服务重启健康结果，`task-saved.json` 为本轮隔离任务实际内容。截图为 `desktop-task.png`、`paper-chat-source.png`、`saved-artifact.png`，最终链路截图在 `final-baseline.png`。根目录下的 `stage0-task-before-restart.json` / `stage0-task-after-restart.json` 为较早空任务重启检查，仅作补充；完整任务证据优先。

## 本轮启动阻塞与处理

- Docker 初始引擎未运行；启动后报运行时套接字无法访问，先后涉及 `Docker/run/dockerInference`、`docker-secrets-engine/engine.sock`、`Docker/run/userAnalyticsOtlpHttp.sock`。
- Windows 对这些零字节重解析点的改名/移除均失败。停止本轮启动失败的 Docker 进程后，从已有 WSL 对明确的临时文件改名备份，最终 Docker 正常启动。备份名带 `stage0-backup`，没有移动数据库或凭证内容。
- Docker 恢复后原 Python 容器自动运行，但 GROBID 未启动，第一次论文上传返回 500；启动 GROBID 后重试成功。后续启动应先核验依赖健康，不能只看 Python 端口。

## 缺陷与后续阶段

| 编号 | 当前证据 | 处理阶段 |
|---|---|---|
| B01 | 窄屏约 318px 时三栏硬挤，原文区提示逐字换行，对话区几乎不可见 | 阶段 6：窄屏采用可切换主区域 |
| B02 | 点击重命名无效果；浏览器控制台明确 `prompt() is not supported` | 阶段 6：改应用内命名输入 |
| B03 | 上传依赖缺失仅显示英文 `Request failed with status code 500` | 阶段 1/6：结构化错误及中文可操作提示 |
| B04 | 真实目录混入 `11 Let introduce the Lagrange multiplier`、`17 The optimal solution` 和公式文本 | 阶段 6：改善目录抽取和过滤 |
| B05 | 上传同步等待全文摘要、结构提取和索引；源码确认必经两次全文模型生成，用户只能看到“上传中” | 阶段 1/2：阅读就绪与可选分析分离、持久化解析状态 |
| B06 | 回答“来源 3”，成果显示“材料来源（12）”；后者含检索片段，缺少直观的论文/证据区分 | 阶段 2/4：收束来源、明确证据层次 |
| B07 | “加入工作台”旧术语仍出现在回答保存操作 | 阶段 2/6：统一任务与成果术语 |
| B08 | 导出没有可确认的文件证据；仅点击成功不足以认定导出可用 | 阶段 5：在支持下载的运行环境核验文件与正文 |
| B09 | 创建任务失败时提示草稿已保留，但刷新后空任务导航未提供该草稿找回入口 | 阶段 1：完善未成功创建任务的草稿发现与恢复 |
| B10 | 论文文件及解析展示缓存仍依赖本浏览器 IndexedDB；本轮没有证明新客户端可阅读同一文件 | 阶段 1/5：材料持久化边界与跨客户端恢复 |

阶段 0 的基本链路、Provider 和服务重启门槛已满足。六能力全量验收、学习质量、复杂研究恢复、所有引用坐标、扫描论文、旧数据完整迁移、跨客户端、移动端、正式默认入口均未在本轮宣称通过，继续按阶段计划推进。
