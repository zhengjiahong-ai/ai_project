# Pixiu Academic Assistant

Pixiu Academic Assistant 是一个面向学术论文阅读的 AI 工作台。它围绕 PDF 论文提供上传解析、篇章解构、对话问答、术语解释、逐页翻译、背景补课、引导学习、批判阅读、深度研究和本地知识沉淀等能力。

当前仓库采用三层架构：

- `frontend/`: React 19 + Vite 7 前端工作台
- `backend-java/`: Spring Boot Java 网关，统一对外暴露 `/api`
- `ai-service-python/`: FastAPI AI 服务，负责论文解析、RAG、LLM 调用与研究任务执行

配套依赖还包括：

- `GROBID 0.7.2`：解析 PDF 为 TEI/XML 并提取结构信息
- `ChromaDB + sentence-transformers`：当前论文和内部文献库检索
- `H2`：Java 网关侧保存论文记录和聊天历史
- `SQLite`：Python 侧保存深度研究任务快照
- `IndexedDB`：浏览器侧保存 PDF、阅读进度、对话、笔记、翻译与工作台资产

## 当前能力

### 论文上传与结构解析

- 浏览器上传 PDF 到 Java `/api/upload`
- Java 转发到 Python `/api/analyze-pdf`
- Python 调用 GROBID 解析正文与版面结构
- Python 生成：
  - `paper_skeleton`：按摘要、引言、方法、结果、讨论、结论的摘要
  - `paper_structure`：研究问题、核心假设、方法框架、主要贡献、实验逻辑、局限性
  - `paper_structure.sections`：真实章节树，尽量包含层级、页码、锚点、来源和置信度
  - `translationLayoutIndex`：逐页翻译需要的版面索引
- 当前论文正文会被切分后写入 RAG 索引，供聊天、术语解释、批判阅读和深度研究使用

### 阅读工作台

前端 `App.jsx` 已经实现三阶段阅读工作流：

- 阶段一 `浅读解构`
  - 问答
  - 篇章解构
  - 逐页翻译
- 阶段二 `深度探究`
  - 背景补课
  - 引导学习
  - 批判阅读
  - 深度研究
- 阶段三 `知识内化`
  - 底部工作台中的卡片和边注沉淀

界面核心区域包括：

- 左侧论文库与章节导航
- 中央 PDF 阅读器
- 右侧 AI 功能面板
- 底部工作台 `BottomWorkbench`

### 智能能力

- `问答`
  - Python 侧使用轻量 agentic RAG
  - 优先检索当前论文，必要时补充内部文献库
  - 返回 `rag_sources`、`queryPlan`、`retrievalJudge`、`sentenceSourceMap`
- `术语解释 / 划词解释`
  - 基于选中文本、页内上下文和论文检索片段生成解释
- `逐页翻译`
  - 优先走结构化页面翻译
  - 保留版面块与覆盖层信息
  - 超时和失败时允许回退
- `背景补课`
  - 根据论文主题、骨架和用户知识水平生成概念图谱、学习路径与补课材料
  - Neo4j 为可选增强，不是运行前提
- `引导学习`
  - 固定 5 轮苏格拉底式问题
  - 优先基于当前论文证据评估用户回答
- `批判阅读`
  - 围绕贡献、方法、实验、局限四条轴线进行证据化分析
  - 生成结构化批判报告与 claim-support 映射
  - 基于 claims 支撑率、缺失证据、夸大风险和方法/实验覆盖生成规则型 `contributionScore`、`riskScore` 与 `noveltyDimensions`，不需要训练或微调模型
- `深度研究`
  - 先生成 research brief preview
  - 再创建异步研究任务
  - 任务状态、计划、发现与报告保存在 Python SQLite 快照中
  - 前端按 `pdfId` 恢复最近任务

## 仓库结构

```text
.
├─ frontend/                    # React + Vite 前端工作台
│  ├─ src/
│  │  ├─ components/            # 各功能面板与工作台组件
│  │  ├─ hooks/                 # 页面状态和会话逻辑
│  │  ├─ services/              # API 与本地存储封装
│  │  └─ utils/                 # 翻译、学习、证据展示等纯逻辑
│  └─ VERSION                   # 前端展示版本号
├─ backend-java/                # Spring Boot 网关
│  ├─ src/main/java/.../controller/AcademicController.java
│  ├─ src/main/java/.../service/AiService.java
│  └─ src/main/resources/application.properties
├─ ai-service-python/           # FastAPI AI 服务
│  ├─ app.py
│  ├─ routes/api.py
│  ├─ core/                     # PDF 解析、outline、RAG 基础能力
│  ├─ services/                 # 聊天、分析、研究任务、trace、安全等服务
│  ├─ rag/                      # RAG 获取和 hybrid retrieval 包装
│  └─ schemas/                  # Pydantic 请求模型
├─ docs/
│  └─ 中期答辩/                  # 历史答辩资料，保留
├─ docker-compose.yml
├─ CHANGELOG.md
├─ ARCHITECTURE.md
└─ API.md
```

## 运行架构

默认访问链路：

```text
Browser
  -> http://localhost:5173
  -> http://localhost:8081/api
  -> http://ai-service:8000/api
  -> http://grobid:8070
```

端口说明：

| 服务 | 本机地址 | 说明 |
| --- | --- | --- |
| 前端 | `http://localhost:5173` | Vite dev server |
| Java 网关 | `http://localhost:8081/api` | 浏览器唯一后端入口 |
| Python AI 服务 | `http://localhost:8000/api` | Java 容器内转发目标 |
| GROBID | `http://localhost:8070` | PDF 结构解析 |
| Neo4j | `http://localhost:7474` | 可选 profile |

## 环境变量

根目录 `.env` 主要供 Docker Compose 与 Python 服务使用：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_TRANSLATION_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING_TYPE=enabled
DEEPSEEK_REASONING_EFFORT=high

NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=
NEO4J_AUTH=neo4j/pixiu_neo4j_password

RESEARCH_TASK_DB_PATH=ai-service-python/data/research_tasks.sqlite3
```

前端可选环境变量：

```env
VITE_API_BASE_URL=http://localhost:8081/api
VITE_MODEL_NAME=DeepSeek V4
```

## 快速启动

### 方式一：Docker Compose

推荐直接在仓库根目录执行：

```bash
docker compose up --build
```

如果只想启动主要服务：

```bash
docker compose up -d frontend backend ai-service grobid
```

如果要启用 Neo4j：

```bash
docker compose --profile neo4j up -d
```

启动后访问：

```text
http://localhost:5173
```

### 方式二：本地分服务开发

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

GROBID 建议继续通过 Docker 运行：

```bash
docker compose up -d grobid
```

## 数据持久化边界

### 浏览器侧

`frontend/src/services/localDb.js` 中的 IndexedDB 库名为 `PixiuAcademicDB_v6`，主要存：

- `pdfStore`
- `historyStore`
- `analysisStore`
- `notesStore`
- `deconstructStore`
- `libraryStore`
- `highlightStore`
- `sessionStore`
- `translationStore`
- `backgroundKnowledgeStore`
- `artifactStore`

清理浏览器站点数据会丢失本地阅读记录与缓存 PDF。

### Java 侧

- H2 文件数据库路径：`backend-java/data/academic_db.mv.db`
- 保存论文记录与聊天历史

### Python 侧

- Chroma 向量库目录：`/app/chroma_data` 或本地配置路径
- 深度研究 SQLite：`ai-service-python/data/research_tasks.sqlite3` 或 `RESEARCH_TASK_DB_PATH`
- trace 为进程内摘要存储，不做长期数据库持久化

## 验证命令

前端：

```bash
cd frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Java：

```bash
cd backend-java
mvn test
```

Python：

```bash
cd ai-service-python
python -m pytest tests -q
```

也可运行部分高价值回归：

```bash
cd ai-service-python
python -m pytest tests/test_outline_extractor.py tests/test_page_translation_service.py -q
```

## 文档导航

- [ARCHITECTURE.md](ARCHITECTURE.md): 系统分层、数据流、状态与存储设计
- [API.md](API.md): 当前对外 API、请求响应模型和注意事项
- [CHANGELOG.md](CHANGELOG.md): 变更记录
