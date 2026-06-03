# Pixiu Academic Assistant

Pixiu Academic Assistant 是一个面向学术论文阅读的 AI 工作台。它以 PDF 论文为中心，提供论文库管理、真实篇章结构导航、划词解释、对话问答、逐页翻译、背景补课、批判阅读、引导学习、深度研究和本地笔记等能力。

当前版本：`0.1.6`

版本号来源：前端目录 [frontend/VERSION](frontend/VERSION)

---

## 项目状态

当前前端已经从单一展示页重构为三栏式论文工作台：

- 顶部工具栏：论文库、服务状态、上传论文、主题切换、关于弹窗。
- 左侧常驻栏：当前论文、阅读进度、可折叠篇章目录、最近论文入口。
- 中间阅读区：PDF 阅读器、页码状态、划词解释与高亮。
- 右侧功能区：问答、篇章解构、批判阅读、逐页翻译、背景补课、引导学习、深度研究、笔记。
- 论文库弹窗：以大表格方式集中管理已上传论文。
- 深度研究任务会在 Python AI 服务中保存 SQLite 快照；页面刷新后可按当前论文恢复最近任务，服务重启前未结束的任务会恢复为失败状态并提示重新发起。

后端当前支持通过 GROBID 解析真实论文结构，并通过目录抽取层融合 TEI 章节标题、段落级版面标题候选和 PDF 行级标题候选，在新解析结果中返回 `displayTitle`、`rawTitle`、`level`、`parentId`、`headingNumber`、`pageIndex`、`bbox`、`anchorY`、`source` 和 `confidence` 等字段。前端篇章目录会优先使用这些字段生成多级树，并支持页码跳转、当前章节高亮、搜索过滤和折叠展开。

> 已经在旧版本解析过的论文，其浏览器 IndexedDB 缓存里可能没有 `level/parentId`。这类旧数据仍可能显示为一级目录；重新上传或重新解析后，才会得到新的多级结构字段。

---

## 技术栈

| 层级 | 技术 | 说明 |
| --- | --- | --- |
| 前端 | React 19, Vite 7, Tailwind CSS | 学术阅读工作台、PDF 阅读器、右侧 AI 功能面板 |
| PDF 阅读 | `@react-pdf-viewer`, `pdfjs-dist` | PDF 渲染、页码监听、划词高亮、目录跳页 |
| 本地存储 | IndexedDB (`idb`) | PDF、聊天、笔记、解析结果、翻译状态、论文库 |
| Java 网关 | Spring Boot | 对外统一 `/api`，转发到 Python AI 服务 |
| AI 服务 | FastAPI, Uvicorn | PDF 解析、RAG、LLM 调用、翻译、研究任务 |
| PDF 解析 | GROBID 0.7.2 | TEI XML 解析、章节结构、页码与版面信息 |
| LLM | DeepSeek V4 | 默认 `deepseek-v4-pro` / `deepseek-v4-flash` |
| 编排 | Docker Compose | 前端、Java、Python、GROBID、可选 Neo4j |

---

## 服务端口

| 服务 | 容器名 | 本机地址 | 说明 |
| --- | --- | --- | --- |
| 前端 | `paper_frontend` | `http://localhost:5173` | Vite dev server |
| Java 网关 | `backend_java` | `http://localhost:8081/api` | 浏览器默认访问的后端入口 |
| Python AI | `ai_service_python` | `http://localhost:8000/api` | Java 内部转发目标 |
| GROBID | `grobid_service` | `http://localhost:8070` | PDF 结构解析 |
| Neo4j | `pixiu_neo4j` | `http://localhost:7474` | 可选知识图谱持久化 |

Java 容器内部仍监听 `8080`，`docker-compose.yml` 将本机 `8081` 映射到容器 `8080`。前端 API 默认应指向：

```text
http://localhost:8081/api
```

---

## 项目结构

```text
.
├─ frontend/                 # React + Vite 前端
│  ├─ src/
│  │  ├─ components/         # PdfViewer、ChatPanel、LibrarySidebar、各功能面板
│  │  ├─ services/api.js     # 前端 API 封装
│  │  ├─ utils/              # 翻译、页面布局、会话模型等工具
│  │  └─ App.jsx             # 工作台主布局与状态编排
│  ├─ VERSION                   # 前端显示版本号
│  └─ package.json
├─ backend-java/             # Spring Boot API 网关
├─ ai-service-python/        # FastAPI + GROBID + DeepSeek + RAG
│  ├─ core/document_parser.py
│  ├─ services/analysis_service.py
│  ├─ llm/client.py
│  └─ main.py
├─ docs/                     # 设计约束与补充文档
├─ docker-compose.yml
├─ CHANGELOG.md
└─ README.md
```

---

## 环境变量

根目录 `.env` 用于 Docker Compose 和 Python AI 服务。不要提交真实密钥。

```env
DEEPSEEK_API_KEY=填入你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_TRANSLATION_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING_TYPE=enabled
DEEPSEEK_REASONING_EFFORT=high

# 可选：Neo4j 持久化
NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=
NEO4J_AUTH=neo4j/pixiu_neo4j_password

# 可选：深度研究任务快照数据库路径
RESEARCH_TASK_DB_PATH=ai-service-python/data/research_tasks.sqlite3
```

前端可选环境变量：

```env
VITE_API_BASE_URL=http://localhost:8081/api
VITE_MODEL_NAME=DeepSeek V4
```

如果没有设置 `VITE_MODEL_NAME`，前端关于弹窗默认显示 `DeepSeek V4`。

---

## 快速启动

推荐使用 Docker Compose：

```bash
docker compose up --build
```

如果 Docker Hub 拉取基础镜像失败，且本地已经存在项目镜像，可以先跳过构建恢复后端服务：

```bash
docker compose up -d --no-build grobid ai-service backend
```

如果只需要重新启动已经存在的服务：

```bash
docker compose up -d frontend backend ai-service grobid
```

常用检查命令：

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

访问：

```text
http://localhost:5173
```

---

## 本地开发

前端：

```bash
cd frontend
npm install
npm run dev
```

Java 网关：

```bash
cd backend-java
./mvnw spring-boot:run
```

Python AI 服务：

```bash
cd ai-service-python
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

本地直接运行 Python 服务时，深度研究任务快照默认写入 `ai-service-python/data/research_tasks.sqlite3`。Docker Compose 会将 `RESEARCH_TASK_DB_PATH` 设置为 `/app/data/research_tasks.sqlite3`，并通过 `research_task_data` volume 保留快照。

GROBID 建议继续使用 Docker：

```bash
docker compose up -d grobid
```

注意：当前 Dockerfile 中的 Python AI 服务默认没有开启 `uvicorn --reload`。如果修改了 `ai-service-python` 的后端代码，需要重启容器：

```bash
docker restart ai_service_python
```

---

## 主要功能

### 论文库

- 上传 PDF 后自动解析并入库。
- 表格弹窗展示论文标题、作者、解析状态、章节数、阅读进度、页码、更新时间。
- 支持切换论文、删除论文，并隔离每篇论文的聊天、笔记、翻译、解析和学习记录。

### 篇章目录

- 优先读取后端返回的真实论文结构。
- 支持 `displayTitle`、`rawTitle`、`level`、`parentId`、`headingNumber`、`pageIndex`、`bbox` 和 `anchorY`。
- 支持多级树、折叠展开、搜索过滤、当前页高亮和页码跳转。
- 支持来源标记：`PDF结构`、`版面补全`、`PDF行补全`、`PDF+版面`、`AI解析`、`AI目录`、`待解析`。
- 旧缓存论文缺少层级字段时，会降级为标题编号推断。

### PDF 阅读与划词解释

- 中间区域展示 PDF。
- 支持划词后触发 AI 解释。
- 解释结果可同步到右侧问答流。
- 支持高亮与笔记持久化。

### 问答

- 基于当前论文上下文和 RAG 证据回答问题。
- 支持历史对话恢复。
- 返回结构化 `rag_sources`、可选 `queryPlan` 和 `retrievalJudge`。

### 篇章解构

- 上传论文后触发 GROBID + LLM 解析。
- 生成 `paper_skeleton` 与 `paper_structure`。
- `paper_structure.sections` 会尽量保留真实章节层级、数字序号、页码、页内锚点、来源和预览片段；结构版本 `1.4` 会额外从 PDF 行级坐标中补回同页连续小标题，按双栏阅读顺序重排 IEEE 风格小节，并过滤编号贡献句、公式碎片、纯数字标题和页脚等异常候选。
- 篇章解构面板会优先展示真实篇章结构树，并保留 `paper_skeleton` 作为宏观总结。

### 批判阅读

- 通过 Java `/api/critical-reading/{pdfId}` 转发到 Python `/api/deep-analysis`。
- 围绕贡献、方法、实验、局限进行证据化分析。
- 支持展示薄弱点、过度主张风险、缺失证据、论点-证据验证和引用片段。
- 论点-证据验证会提取作者核心主张，并按当前论文证据标记 `SUPPORTED`、`PARTIAL`、`UNSUPPORTED`；该功能不做外部论文对比或真实新颖性评分。

### 逐页翻译

- 按当前 PDF 页提取文本。
- 缓存已翻译页面。
- 优先使用结构化正文块翻译，保留双栏阅读顺序，并以 overlay 方式回填译文。
- 过滤图、表、公式、算法伪代码、页脚和 PDF 文本层中的零碎公式残片，避免把图内标签、公式变量、伪代码步骤误送入正文翻译。
- 对含图页面不再强制退回纯文本翻译；图表区域会在结构化翻译请求中被排除，减少正文段落被遗漏的概率。
- 结构化翻译采用小批次并发请求，前端和 Python 端都放宽超时阈值；结构化结果不足时仍可回退到纯文本翻译。

### 背景补课

- 根据当前论文主题生成前置概念、学习路径、补课清单和知识图谱。
- 支持 `入门`、`一般`、`进阶` 三种知识水平。
- Neo4j 是可选增强；未配置时仍返回 JSON 图谱。

### 引导学习

- 固定 5 题苏格拉底式学习流程。
- 每题优先参考当前论文证据。
- 支持回答评估、掌握度、缺失点、最终回读建议。

### 深度研究

- 支持创建、轮询、取消研究任务。
- 任务围绕当前论文和用户研究问题展开。
- 返回阶段、进度、计划、结构化 `findings` 和 Markdown 报告。
- 当前任务状态保存在 Python 进程内存和浏览器会话内存中，服务重启后不保证恢复。

---

## API 链路

浏览器只直接访问 Java 网关：

```text
Browser -> http://localhost:8081/api -> backend-java -> http://ai-service:8000/api -> ai-service-python
```

PDF 解析链路：

```text
ai-service-python -> http://grobid:8070 -> GROBID TEI XML -> document_parser -> paper_structure.sections
```

---

## 运行边界

- 浏览器侧论文数据、聊天记录、笔记、翻译状态和阅读进度主要保存在 IndexedDB 中；清理浏览器站点数据会影响这些本地记录。
- 已上传且已解析过的旧论文可能仍使用旧缓存结构；如果目录没有多级层级、缺少数字序号或没有 `outlineVersion`，优先重新上传或重新解析论文。
- Deep research 任务状态当前保存在 Python 进程内存和浏览器会话内存中；后端重启或页面刷新后不保证恢复。
- Python AI 服务会为聊天、划词解释、批判阅读、背景补课和深度研究生成轻量 trace；trace 用于排障阶段、耗时、检索次数和 LLM 调用次数，不记录 API Key、完整 prompt、完整论文全文或完整用户全文。
- 论文正文、`paperSkeleton`、`paperStructure`、页内上下文和 RAG 片段都被视为不可信资料；其中出现的越权指令、密钥索取、system prompt 泄露、联网搜索或工具调用要求只会被当作待分析文本，不会被执行。
- 当前仓库没有对外 MCP server 或 MCP client，也没有引入 MCP SDK；后续适配路线见 [docs/MCP_ADAPTER_PLAN.md](docs/MCP_ADAPTER_PLAN.md)。

---

## 验证命令

前端：

```bash
cd frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Python AI 服务容器内语法检查：

```bash
docker exec ai_service_python python -m py_compile /app/core/document_parser.py /app/core/outline_extractor.py /app/services/analysis_service.py
docker exec ai_service_python python -m unittest tests.test_outline_extractor -v
```

复杂 PDF 解析与逐页翻译回归：

```bash
cd frontend
node src/utils/pdfTranslationLayout.test.js
node src/utils/pageTranslationRequest.test.js

cd ../ai-service-python
python -m pytest tests/test_outline_extractor.py tests/test_page_translation_service.py -q
```

Docker 服务状态：

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

已知构建警告：

- `react-resizable-panels` 的 `"use client"` 指令在 Vite 打包时会被忽略。
- `pdfjs-dist` 会提示 `eval` 风险。
- 主包体积可能超过 Vite 默认 chunk warning 阈值。

这些是当前已知非阻塞警告。

---

## 版本与变更记录

- 前端显示版本号：[frontend/VERSION](frontend/VERSION)
- 变更记录：[CHANGELOG.md](CHANGELOG.md)
- 从 `2026-05-05 19:09 v0.1.0` 开始，CHANGELOG 统一采用 `时间 + 版本号` 的标题格式。

---

## 相关文档

- [启动服务.md](启动服务.md)
- [docs/CONSTRAINTS.md](docs/CONSTRAINTS.md)
- [docs/MCP_ADAPTER_PLAN.md](docs/MCP_ADAPTER_PLAN.md)
- [frontend/TROUBLESHOOTING.md](frontend/TROUBLESHOOTING.md)
