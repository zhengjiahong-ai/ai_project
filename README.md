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
- **对话与划词解释**：聊天面板发送消息；在 PDF 中划词可触发解释（对接 `/api/explain`，携带当前页上下文，经过轻量学术查询重写后优先基于当前论文 RAG 检索），回答前会评估证据质量，证据不足时明确提示，并返回结构统一的 `rag_sources` 依据片段。
- **批判性阅读**：前端调用 Java `/api/critical-reading/{pdfId}`，Java 转发 Python `/api/deep-analysis`，基于当前论文索引内容生成贡献对比与批判性分析。
- **学术笔记**：支持在阅读时添加笔记并持久化到 IndexedDB。
- **全景翻译**：支持按当前 PDF 页提取文本并进行逐页全文翻译，译文显示在右侧专用面板中；翻页后自动跟随当前页更新，并对已翻译页面进行缓存，避免重复请求。
- **引导式学习**：基于论文内容、阅读进度和论文骨架生成苏格拉底式问题，支持逐轮作答、掌握度评估、提示反馈和最终总结，帮助用户用问答方式推进理解。

---

## 背景补课 / 前置知识图谱

- 独立“背景补课”页签会手动调用 Java `/api/background-knowledge`，Java 再转发到 Python `/api/background-knowledge`。
- Python 结合当前论文 `pdfId`、篇章结构、改写后的检索查询、Chroma RAG 片段和 LLM 返回前置概念图谱、学习路径、补课清单和结构统一的 RAG 依据片段。
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
