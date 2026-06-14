# Pixiu Academic Assistant

Pixiu Academic Assistant 是一个面向学术论文阅读的 AI 工作台。它把 PDF 解析、单论文阅读辅助、证据化分析，以及新的多论文 Agent 研究工作区整合在同一个项目里。

## 当前技术栈

- `frontend/`：React 19 + Vite 7 前端工作台。
- `backend-java/`：Spring Boot 网关与轻量持久化层。
- `ai-service-python/`：FastAPI AI 服务，负责解析、检索、分析、任务执行和 trace。
- `grobid`：PDF 结构抽取服务。
- `ChromaDB + sentence-transformers`：当前论文和内部文献库检索。
- `H2`：Java 侧论文记录和聊天历史持久化。
- `SQLite`：Python 侧 Deep Research 任务快照持久化。
- `IndexedDB`：浏览器侧阅读会话和工作区状态持久化。

## 当前能力

### 阅读 IDE

主阅读工作区已经打通端到端链路：

- 上传并解析 PDF。
- 提取论文骨架和章节结构。
- 基于证据的单论文问答。
- 划词或术语解释。
- 逐页翻译。
- 自适应背景补课。
- 苏格拉底式引导学习。
- 带证据主张的批判阅读。
- 带 trace 和持久化快照的 Deep Research 异步任务。

### Agent 研究

Agent 工作区已经不再只是静态原型壳。当前已经具备第一版可用的端到端链路：

- 创建和切换 Agent 项目。
- 向项目挂载多篇论文。
- 创建异步 Agent 任务。
- 轮询任务进度和阶段状态。
- 展示时间线事件、工具调用、证据片段、对比表、冲突候选、开放问题和报告草稿。
- 在前端快照中按项目保存任务历史。
- 切换项目时恢复对应项目的任务历史。

当前 AI 效果边界：

- Agent 结论已经从通用占位文本升级为有证据依据的规则型草稿。
- 这仍是第一版规则型综合，不是最终形态的复杂多步推理系统。

## 运行链路

当前产品里存在两条 API 访问路径。

### 阅读 IDE 链路

```text
Browser
  -> Frontend http://localhost:5173
  -> Java gateway http://localhost:8081/api
  -> Python AI service http://ai-service:8000/api
  -> GROBID http://grobid:8070
```

### Agent 研究链路

Agent 面板当前默认由前端直接访问 Python Agent API：

```text
Browser
  -> Frontend http://localhost:5173
  -> Python AI service http://localhost:8000/api
```

Java 网关源码里已经包含 Agent 转发接口，但本地运行时可能尚未重建到最新版本，所以当前前端默认直连 Python，避免 Agent 面板因为 Java 运行时滞后而不可用。

## 环境变量

根目录 `.env` 主要供 Docker Compose 和 Python 服务使用：

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
VITE_AGENT_API_BASE_URL=http://localhost:8000/api
VITE_MODEL_NAME=DeepSeek V4
```

说明：

- `VITE_API_BASE_URL` 用于阅读 IDE。
- `VITE_AGENT_API_BASE_URL` 用于 Agent 工作区。
- Python CORS 已允许本地 Vite 来源，例如 `http://localhost:5173`。

## 快速启动

### Docker Compose

在仓库根目录执行：

```bash
docker compose up --build
```

只启动主要服务：

```bash
docker compose up -d frontend backend ai-service grobid
```

启用 Neo4j：

```bash
docker compose --profile neo4j up -d
```

启动后访问：

```text
http://localhost:5173
```

### 本地分服务启动

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

GROBID 建议继续通过 Docker 启动：

```bash
docker compose up -d grobid
```

## Agent 工作区说明

今天 Agent 工作区完成了比较完整的一轮迭代，当前包括：

- 更完整的右侧 Agent 工作区展示，而不是简单 mock 面板。
- 拆分后的前端子组件，便于后续维护。
- 基于 `tasksByProjectId` 的项目级任务历史。
- 切换项目时恢复历史任务。
- 完整显示 `draftReport`，不再只截断展示前几个段落。
- 前端直连 Python Agent API。
- 异步执行阶段：`planning -> retrieving -> synthesizing -> done`。
- 第一版跨论文冲突检测和基于证据的结论草稿。

当前限制：

- Agent 项目和任务在 Python 侧仍是进程内存储，服务重启后会丢失。
- 前端项目切换已经可用，但后端还没有“列出某项目所有任务”的接口。
- Agent 结论已经能生成有用草稿，但仍是轻量规则型综合。
- 如果 Java 运行时早于最新 Agent 转发代码启动，Agent 模式应继续使用默认的 Python 直连路径，或重建 Java 服务。

## 数据持久化

### 浏览器侧

IndexedDB 保存本地阅读工作区和产物，包括：

- PDF。
- 聊天历史。
- 分析结果。
- 笔记和高亮。
- 翻译状态。
- 背景补课结果。
- 工作台产物。
- Agent 工作区快照，包括项目级任务历史。

### Java 侧

H2 保存：

- 论文记录。
- 聊天消息。

### Python 侧

Python 保存：

- Chroma 检索索引。
- Deep Research SQLite 快照，默认位置为 `ai-service-python/data/research_tasks.sqlite3` 或 `RESEARCH_TASK_DB_PATH`。
- 进程内 Agent 项目和 Agent 任务。
- 进程内 public trace summary；Deep Research 终态 trace summary 会随 SQLite 任务快照保存。

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

## 已知问题

- `npm run build` 当前会因为 `frontend/src/components/MessageMarkdownRenderer.js` 缺少 `rehype-katex` 依赖而失败；这和本次 Agent 工作无关。
- 某些本地环境如果没有安装 Python 测试依赖，`pytest` 可能不可用。
- Agent 服务当前优先完成框架搭建、链路打通和有意义草稿输出，复杂算法和更强综合质量留给后续迭代。

## 文档导航

- [ARCHITECTURE.md](ARCHITECTURE.md)：系统结构、运行链路、持久化边界和模块职责。
- [API.md](API.md)：接口契约、请求响应结构和关键数据形态。
- [CHANGELOG.md](CHANGELOG.md)：变更记录。
