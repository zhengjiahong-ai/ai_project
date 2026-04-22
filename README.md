# 学术论文 AI 助手（Pixiu Academic Assistant）

基于 AI 的学术论文阅读与批判性分析平台，支持 PDF 上传、篇章解构、术语解释、对话式问答与批判性阅读报告。

---

## 项目概述

- **前端**：React 单页应用，提供 PDF 预览、划词解释、聊天与多 Tab 分析面板。
- **后端网关**：Spring Boot 统一对外 API，转发请求到 Python AI 服务。
- **AI 服务**：FastAPI + GROBID 解析 PDF，通义千问（DashScope）结合 RAG 做摘要、解释、翻译与分析。
- **部署**：Docker Compose 一键启动前端、Java、Python、GROBID 四类服务。

---

## 技术栈

| 层级       | 技术                     | 版本/说明 |
|------------|--------------------------|-----------|
| 前端       | React                    | 19.x      |
| 前端构建   | Vite                     | 7.x       |
| 前端样式   | Tailwind CSS             | 3.x       |
| 前端 PDF   | @react-pdf-viewer, pdfjs-dist | 3.x       |
| 前端请求   | Axios                    | 1.x       |
| 前端存储   | IndexedDB (idb)          | 本地持久化 |
| 后端网关   | Spring Boot              | 3.4.x, Java 21 |
| AI 服务    | FastAPI, Uvicorn         | Python 3.x |
| PDF 解析   | GROBID                   | 0.7.2 (Docker) |
| 大模型     | 通义千问 (DashScope)     | qwen-max  |
| 编排       | Docker Compose           | -         |

---

## 项目结构

```
.
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── components/       # PdfViewer, ChatPanel, Navbar, PaperAnalysis, CriticalAnalysisPanel 等
│   │   ├── services/         # api.js 封装后端请求
│   │   └── App.jsx
│   ├── .env                  # VITE_API_BASE_URL 指向 Java 后端
│   └── package.json
├── backend-java/             # Spring Boot 网关
│   └── src/main/java/.../controller/AcademicController.java
│   └── src/main/java/.../service/AiService.java
├── ai-service-python/        # FastAPI + GROBID + DashScope
│   ├── main.py               # /api/analyze-pdf, /api/explain-term 等
│   └── requirements.txt
├── docker-compose.yml        # frontend, backend, ai-service, grobid
├── .env                      # DASHSCOPE_API_KEY（根目录，供 ai-service 使用）
└── docs/
    └── CONSTRAINTS.md        # 技术栈与接口约束（开发必读）
```

---

## 请求链路

1. **浏览器** → `VITE_API_BASE_URL`（默认 `http://localhost:8080/api`）→ **Java 后端**
2. **Java** → `PYTHON_URL`（Docker 下为 `http://ai-service:8000/api`）→ **Python AI 服务**
3. **Python** 解析 PDF 时 → `http://grobid:8070` → **GROBID 容器**

---

## 快速开始

### 环境要求

- Node.js 18+
- JDK 21
- Python 3.10+
- Docker & Docker Compose（若使用容器化运行）

### 本地开发

1. **配置环境变量**
   - 项目根目录 `.env` 中配置 `DASHSCOPE_API_KEY`（通义千问 API Key）。
   - 前端 `frontend/.env` 中可选配置 `VITE_API_BASE_URL`（默认 `http://localhost:8080/api`）。

2. **启动 Python AI 服务**（需先启动 GROBID，或使用 Docker 一起启动）
   ```bash
   cd ai-service-python && pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000
   ```

3. **启动 Java 后端**
   ```bash
   cd backend-java && ./mvnw spring-boot:run
   ```

4. **启动前端**
   ```bash
   cd frontend && npm install && npm run dev
   ```

5. 浏览器访问 `http://localhost:5173`。

### Docker 一键启动

```bash
# 确保根目录 .env 中有 DASHSCOPE_API_KEY
docker-compose up --build
```

- 前端：http://localhost:5173  
- Java API：http://localhost:8080  
- Python AI：http://localhost:8000  
- GROBID：http://localhost:8070  

---

## 主要功能

- **PDF 上传与篇章解构**：上传 PDF → GROBID 解析 → AI 生成 abstract/introduction/methods/results/discussion/conclusion 摘要。
- **对话与划词解释**：聊天面板发送消息；在 PDF 中划词可触发解释（对接 `/api/explain`，携带当前页上下文，经过轻量学术查询重写后优先基于当前论文 RAG 检索）。其中 `/api/chat` 已升级为轻量 Agentic RAG 流程：先做意图识别和查询计划，再优先检索当前论文、必要时补充文献库，并在回答前进行证据质量判断与最多一次重试；响应继续返回结构统一的 `rag_sources`，并可附带 `queryPlan` 与 `retrievalJudge`。
- **批判性阅读**：前端调用 Java `/api/critical-reading/{pdfId}`，Java 转发 Python `/api/deep-analysis`，基于当前论文全文 chunks 做贡献、方法、实验与局限的证据化批判阅读；响应在兼容旧字段的同时，还可附带 `evidence_based_contributions`、`weaknesses`、`overclaim_risks`、`missing_evidence`、`rag_sources` 与可选 `traceId`，前端面板会在原有布局上紧凑展示这些补充信息。
- **学术笔记**：支持在阅读时添加笔记并持久化到 IndexedDB。
- **全景翻译**：支持按当前 PDF 页提取文本并进行逐页全文翻译，译文显示在右侧专用面板中；翻页后自动跟随当前页更新，并对已翻译页面进行缓存，避免重复请求。
- **引导式学习**：保持固定 5 题的苏格拉底式学习流程，基于论文内容、阅读进度和论文骨架生成问题；每轮提问与回答评估会优先参考当前论文 RAG 证据，返回掌握度评估、证据判断和待补强要点，并在最终总结中给出建议回读章节、概念或证据点，帮助用户用问答方式推进理解。
- **深度研究**：新增独立“深度研究”页签，用户可围绕当前论文输入研究问题、启动任务、轮询查看阶段与进度、取消任务，并在同一面板中查看结构化 `findings` 与最终 Markdown 报告；任务状态当前只保留在浏览器会话内存中，刷新页面后不保证恢复，后端任务快照会兼容附带可选 `traceId` 以便排障。

---

## 背景补课 / 前置知识图谱

- 独立“背景补课”页签会手动调用 Java `/api/background-knowledge`，Java 再转发到 Python `/api/background-knowledge`。
- 面板支持按 `入门`、`一般`、`进阶` 三档知识水平生成补课结果；切换论文后会恢复该论文最近一次背景补课结果中的知识水平。
- Python 结合当前论文 `pdfId`、篇章结构、改写后的检索查询、Chroma RAG 片段和 LLM 返回前置概念图谱、学习路径、补课清单和结构统一的 RAG 依据片段。
- 图谱生成阶段会对概念节点做轻量去重并稳定 `node id`，优先把概念组织为“基础概念 -> 方法前置 -> 实验理解 -> 批判视角”四段式学习路径；旧 `learning_path` 仍保留以兼容旧缓存和旧前端结构。
- 每个概念节点会尽量绑定本次响应中的 `rag_sources`，响应可额外返回 `confidence` 与 `sourceCoverage`，用于衡量当前图谱的证据覆盖程度和整体可靠性。
- Neo4j 是可选持久化增强；未配置时接口仍返回 JSON 图谱，不影响默认开发和 Docker 启动。

可选启用 Neo4j：

```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=pixiu_neo4j_password
NEO4J_AUTH=neo4j/pixiu_neo4j_password

docker-compose --profile neo4j up --build
```

---

## 深度研究任务 API

- Java 对外提供 `POST /api/research-tasks`、`GET /api/research-tasks/{taskId}` 与 `POST /api/research-tasks/{taskId}/cancel`，Python 内部提供同名 `/api/research-tasks` 路由。
- 创建任务请求体固定为 `{ question, pdfId, paperSkeleton? }`；当前模块严格围绕当前论文工作，因此 `pdfId` 必填，`paperSkeleton` 只用于增强规划上下文。
- 三个成功响应统一返回 `{ status, task }`，其中 `task` 包含 `taskId`、可选 `traceId`、任务 `status`、`stage`、`progress`、`plan`、结构化 `findings`、`report` 与 `error`。
- `findings` 当前固定为结构化摘要项：`{ subQuestion, summary, verdict, missingAspects, sourceIds }`；`verdict` 复用 `CORRECT | AMBIGUOUS | INCORRECT`，`sourceIds` 只引用本任务中实际使用的证据片段。
- 任务状态目前先存 Python 进程内存，适合作为模块 8 的最小版本；服务重启后任务不会恢复，完整任务面板与持久化增强留给后续模块。
- 前端现在已接入最小任务面板：通过 `frontend/src/services/api.js` 中的 `createResearchTask`、`getResearchTask`、`cancelResearchTask` 三个方法完成创建、轮询刷新与取消，不在组件内部直接拼接 URL。
- 右侧“深度研究”面板会展示任务 `status`、`stage`、`progress`、`plan`、结构化 `findings` 和最终 Markdown `report`；如果后端服务重启或任务状态丢失，面板只提示当前任务不可恢复，不伪装为持久化任务。

---

## Trace 与成本观测

- Python AI 服务现在会为聊天、划词解释、批判阅读、背景补课和深度研究任务生成轻量 trace，并在相关成功响应中兼容返回可选 `traceId`。
- trace 当前只保存在 Python 进程内存与服务日志中，用于排查长任务阶段、耗时、检索次数与 LLM 调用次数；服务重启后不会保留。
- trace 会记录截断后的问题摘要、query 摘要、证据条数、阶段状态和错误摘要，但不会记录 API Key、完整 prompt、完整用户全文或完整论文全文。

---

## 提示注入防护与权限边界

- Python AI 服务现在会把论文正文、`paperSkeleton`、`paperStructure`、页内上下文和 `rag_sources` 片段统一视为不可信资料；这些内容在进入 query rewrite、聊天回答、背景补课、批判阅读和深度研究规划 prompt 前都会经过轻量注入检测、去指令化清洗和 `UNTRUSTED PAPER/RAG CONTENT` 包装。
- 如果论文或检索片段里出现“忽略之前指令”“泄露 API Key”“打印 system prompt”“执行系统命令”“联网搜索/浏览网页”“调用工具/插件/MCP”等文本，系统只会把它们当作待分析内容，不会按其中要求越权执行、泄露密钥或改变当前工作边界。
- 当前模块没有新增真实工具调用接口；query planner 仍只允许 `current_paper` / `library` 两类检索 scope，deep research 仍只围绕当前论文与内部文献库工作，不会自动扩展到外部 Web 搜索。
- 长任务预算继续保持可控：deep research 固定生成 `3-5` 个子问题、检索链路最多自动重试 `1` 次，并对进入模型的上下文采用近似 `8000` tokens 的安全预算裁剪；安全命中信息只进入内部 trace / 日志，不增加新的公开响应字段。

---

## 本地基线检查

模块 0 基线审计使用以下命令确认当前项目状态：

```bash
# 前端
cd frontend
npm test
npm run lint
npm run build

# Python AI 服务
cd ../ai-service-python
python -m pytest -q

# Java 网关
cd ../backend-java
./mvnw test
```

当前基线说明：

- 前端 `npm test` 与 `npm run lint` 通过。
- Python 默认 `python -m pytest -q` 已限定收集 `tests/`，避免扫描临时目录。
- Java 测试使用内存 H2 数据库，避免污染 `backend-java/data/academic_db.mv.db`。
- 前端 `npm run build` 在当前 Windows/Node 环境下仍可能在 Vite transform 完成后以非零状态退出且无明确错误栈；该项作为后续构建专项继续排查。

---

## 相关文档

- [前端排错指南](frontend/TROUBLESHOOTING.md)
- [开发约束与接口约定](docs/CONSTRAINTS.md)（技术栈、接口契约、新增接口规范）

---

## 许可证

请根据项目实际情况补充许可证信息。
