# 开发约束与接口约定

本文档约定技术栈版本、目录规范、前后端接口契约及新增接口规范，**所有后续开发必须遵守**，以保证与现有代码兼容、便于协作与维护。

## 2026-04-04 增量约束

- 前端新增或调整请求时，必须继续集中落在 `frontend/src/services/api.js`。
- Java 对外接口必须继续保持 `/api` 前缀，本次新增 `GET /api/chat/history/{sessionId}` 与 `POST /api/critical-reading/{pdfId}` 也遵守该约束。
- Python 对外接口必须继续保持 `/api` 前缀；即使内部已拆分模块，`main.py` 仍需可直接作为入口。
- “批判性阅读”必须基于真实论文内容生成，允许通过 `pdfId` 走 RAG / 已解析内容回查，但禁止重新引入前端 mock。
- 任何后续接口调整都要同步 README 与 CHANGELOG，避免文档和实现脱节。

## 2026-04-20 基线审计补充

- Python 测试默认通过 `ai-service-python/pytest.ini` 仅收集 `tests/`，避免扫描 GROBID 或临时目录导致权限错误。
- Java 测试必须使用 `src/test/resources/application.properties` 中的内存 H2 配置，禁止测试写入 `backend-java/data/academic_db.mv.db`。
- README、CHANGELOG 与本文档必须反映当前已实现接口；聊天历史、批判性阅读、逐页翻译、苏格拉底会话与背景补课均不再标记为“预留”或“Mock”。
- Python 返回的 `rag_sources` 必须使用统一证据结构，标准字段为 `sourceId`、`text`、`metadata`、`similarity`、`score`、`pdfId`、`chunkIndex`、`sourceType`。
- `rag_sources[].id` 仅作为旧背景补课 UI 的兼容别名保留，新代码应优先使用 `sourceId`。

---

## 一、技术栈要求

### 1.1 前端 (frontend/)

| 项目 | 要求 | 说明 |
|------|------|------|
| 运行时 | Node.js 18+ | 建议使用 LTS |
| 框架 | React 19.x | 使用函数组件 + Hooks，禁止 class 组件 |
| 构建 | Vite 7.x | 配置见 `vite.config.js`，勿改为 Webpack |
| 样式 | Tailwind CSS 3.x | 类名写在 JSX，禁止引入新 CSS 框架 |
| 请求 | Axios | 所有后端请求必须通过 `src/services/api.js` 的 `apiService` 或 `apiClient` |
| 环境变量 | `VITE_*` | 仅 Vite 以 `VITE_` 开头的变量会暴露给前端，API 基地址为 `VITE_API_BASE_URL` |

- **新增依赖**：优先使用 `package.json` 中已有库的同类方案；新加 npm 包需在 `package.json` 中锁定主版本，并更新本约束文档。
- **代码风格**：遵循现有 ESLint 配置（`eslint.config.js`），提交前执行 `npm run lint`。

### 1.2 后端网关 (backend-java/)

| 项目 | 要求 | 说明 |
|------|------|------|
| JDK | 21 | 与 Spring Boot 3.4.x 一致 |
| 框架 | Spring Boot 3.4.x | 仅使用 Web、Lombok，不引入 Spring Security 等除非统一规划 |
| 包名 | `com.ai.assistant.backend_java` | 新类必须在该包或其子包下 |
| API 根路径 | `/api` | 所有对外 REST 接口必须以 `/api` 为前缀，与前端 `VITE_API_BASE_URL` 对应 |
| 跨域 | WebConfig | 已允许 `http://localhost:5173`，生产需改为实际前端域名 |

- **配置**：大文件上传已在 `application.properties` 中设为 100MB；Python 服务地址通过环境变量 `PYTHON_URL` 注入（默认 `http://localhost:8000/api`），Docker 下为 `http://ai-service:8000/api`。
- **超时**：调用 Python 的 `RestTemplate` 已设置较长读超时（60s），新增转发接口若耗时长需评估并必要时单独配置。

### 1.3 AI 服务 (ai-service-python/)

| 项目 | 要求 | 说明 |
|------|------|------|
| Python | 3.10+ | 建议 3.10 或 3.11 |
| 框架 | FastAPI | 异步端点使用 `async def` |
| 路由前缀 | `/api` | 所有对外接口挂在 `/api` 下，与 Java 的 `PYTHON_URL` 拼接一致 |
| 大模型 | DashScope (通义千问) | API Key 从环境变量 `DASHSCOPE_API_KEY` 读取，勿写死在代码中 |
| GROBID | 固定主机名 | Docker 内为 `http://grobid:8070`，本地调试可改为 `http://localhost:8070` |

- **依赖**：版本范围以 `requirements.txt` 为准，新增依赖需写明版本区间并注明用途。
- **敏感信息**：禁止在仓库中提交 `.env` 或含 API Key 的文件；`.env` 仅本地/CI 使用，根目录 `.env` 由 docker-compose 注入 ai-service。

### 1.4 基础设施

- **GROBID**：使用镜像 `lfoppiano/grobid:0.7.2`，端口 8070；升级版本需在 `docker-compose.yml` 与本文档同步更新。
- **Docker**：服务名固定为 `frontend`、`backend`、`ai-service`、`grobid`；Java 通过服务名 `ai-service` 访问 Python，勿改为 `localhost`。

---

## 二、接口约定

### 2.1 通用约定

- **数据格式**：请求/响应统一使用 JSON（文件上传除外为 `multipart/form-data`）。
- **错误响应**：HTTP 状态码 + 响应体。建议格式：`{ "status": "error", "message": "可读错误说明" }`。
- **成功响应**：建议包含 `"status": "success"` 及业务字段；列表/分页等可另行约定。

### 2.2 前端调用的后端接口（Java 暴露，baseURL = VITE_API_BASE_URL）

以下为前端 `api.js` 已使用或预留的接口，**路径与请求体不得随意变更**，否则需同步修改前端。

| 方法 | 路径 | 请求体/参数 | 说明 |
|------|------|-------------|------|
| POST | `/api/upload` | `multipart/form-data`, 字段名 `file` | PDF 上传，Java 转发到 Python `/api/analyze-pdf` |
| POST | `/api/explain` | `{ "text": string, "pdfId": any, "pageNumber": number, "context": string }` 或 `{ "term": string, "context": string }` | 术语/划词解释，Java 转发到 Python `/api/explain-term`；带 `pdfId` 时优先基于当前论文 RAG |
| POST | `/api/chat` | `{ "message": string, "pdfId": any, "history": array?, "paperSkeleton": object? }` | 对话，Java 持久化当前论文会话并转发到 Python `/api/chat`；Python 结合论文摘要、历史和 RAG 片段返回回答与统一 `rag_sources` |
| GET | `/api/chat/history/:sessionId` | - | 读取 Java H2 中按 `pdfId/sessionId` 保存的聊天历史，前端用于恢复远端会话 |
| POST | `/api/translate-page` | `{ "pdfId": string?, "pageIndex": number, "pageText": string, "paperSkeleton": object?, "pageLayout": object? }` | 逐页翻译，Java 转发到 Python `/api/translate-page`，支持版面块与译文缓存 |
| POST | `/api/critical-reading/:pdfId` | - | 批判性阅读，Java 转发到 Python `/api/deep-analysis`，基于当前论文索引内容生成分析 |
| POST | `/api/socratic-questions` | `{ "paper_content": string, "reading_progress": string }` | 引导式学习（苏格拉底式提问），Java 转发到 Python `/api/socratic-questions` |
| POST | `/api/socratic-session/start` | `{ "pdfId": string?, "paperSkeleton": object?, "readingProgress": string }` | 启动 5 轮苏格拉底式引导会话 |
| POST | `/api/socratic-session/answer` | `{ "pdfId": string?, "paperSkeleton": object?, "readingProgress": string, "currentIndex": number, "currentQuestion": string, "userAnswer": string, "turns": array? }` | 提交当前回答，返回掌握度评估、提示与下一题或最终总结 |
| POST | `/api/background-knowledge` | `{ "pdfId": string?, "paperSkeleton": object?, "paperStructure": object?, "paper_topic": any?, "user_knowledge_level": any? }` | 背景补课图谱，Java 转发到 Python `/api/background-knowledge` |

- **说明**：  
  - Java `AcademicController` 中 `explainTerm` 接收 `Map<String, Object>`，会将 `text`/`term` 适配为 Python 所需的 `term`，并透传 `pdfId`、`pageNumber`、`context`。
  - 新增接口时，Java 路径必须带 `/api` 前缀；Python 路径为相对 `PYTHON_URL` 的后缀（如 `/analyze-pdf`、`/explain-term`）。

### 2.3 Java → Python 已对接的接口

| Java 调用 | Python 路径 | 说明 |
|-----------|-------------|------|
| POST upload → 转发 | POST `/api/analyze-pdf` | 请求体为 multipart，Python 返回 `{ status, paper_skeleton, paper_structure, translationLayoutIndex, pdfId, ragIndexed }` |
| POST explain → 转发 | POST `/api/explain-term` | 请求体 `{ term, context, pdfId?, pageNumber? }`，Python 返回 `{ status, term, explanation, rag_sources }` |
| POST chat → 转发 | POST `/api/chat` | 请求体 `{ message, pdfId?, history?, paperSkeleton? }`，Python 返回 `{ status, message, rag_sources }`，并优先使用当前论文 RAG 片段 |
| POST translate page → 转发 | POST `/api/translate-page` | 请求体 `{ pdfId?, pageIndex, pageText, paperSkeleton?, pageLayout? }`，Python 返回页级译文、译文块和渲染模式 |
| POST critical reading → 转发 | POST `/api/deep-analysis` | Java 传 `{ pdf_id }`，Python 通过已索引论文内容生成批判性阅读结果 |
| POST socratic questions → 转发 | POST `/api/socratic-questions` | 请求体 `{ paper_content, reading_progress }`，Python 返回 `{ status, questions }` |
| POST socratic start → 转发 | POST `/api/socratic-session/start` | 请求体 `{ pdfId?, paperSkeleton?, readingProgress }`，Python 返回开场引导和第 1 题 |
| POST socratic answer → 转发 | POST `/api/socratic-session/answer` | 请求体包含当前题目、用户回答和历史轮次，Python 返回评估、下一题或最终总结 |
| POST background knowledge → 转发 | POST `/api/background-knowledge` | 请求体兼容 `pdfId`、论文结构和用户知识水平，Python 返回前置知识图谱与学习路径 |

### 2.4 Python 已实现的其他接口（内部或后续扩展）

以下接口目前仅 Python 提供，若前端需要，应由 Java 增加对应路由并转发：

| 方法 | Python 路径 | 请求体 | 说明 |
|------|-------------|--------|------|
| POST | `/api/rag/add-literature` | `multipart/form-data`, 字段名 `file`，可选 metadata | 向 Python 文献库追加索引，当前前端未直接使用 |
| POST | `/api/rag/retrieve` | query/top_k/filter_metadata | 直接检索 Python RAG，当前前端未直接使用 |
| POST | `/api/deep-analysis` | `{ "paper_content": string? }` 或 `{ "pdf_id": string? }` | 深度/批判分析能力；当前 Java 通过 `/api/critical-reading/{pdfId}` 转发 `pdf_id` |

---

## 三、新增/修改接口规范

1. **前端**  
   - 仅在 `src/services/api.js` 中新增或修改方法；统一使用 `apiClient` 或 `apiService`，baseURL 来自 `VITE_API_BASE_URL`。  
   - 超时：上传/长耗时接口可单独设置 `timeout`（如 60s、120s）。

2. **Java**  
   - 新接口写在 `AcademicController` 或新 Controller 下，统一 `@RequestMapping("/api")` 或等价前缀。  
   - 若转发到 Python，在 `AiService` 中新增方法，使用 `RestTemplate` 调用 `PYTHON_SERVICE_URL + "/xxx"`；敏感配置用 `@Value` 从环境变量读取。

3. **Python**  
   - 新路由挂在 `/api` 下，请求/响应模型使用 Pydantic；返回 JSON 时用 `JSONResponse`，错误时 `status_code=4xx/5xx` 并 body 含 `status: "error"` 与 `message`。

4. **文档**  
   - 新增或变更接口后，必须更新本文档「二、接口约定」对应表格及 README 中的「请求链路」说明（如有变化）。

---

## 四、目录与文件约定

- **前端**：页面级组件与业务组件放在 `src/components/`；通用逻辑放 `src/hooks/`；API 封装仅保留在 `src/services/api.js`。  
- **Java**：Controller 仅做参数校验与转发，业务逻辑放在 Service 层；配置类放在 `config` 包下。  
- **Python**：路由与请求模型在 `main.py` 中；若逻辑增多，可拆出 `services/`、`models/` 等模块，但需保证 `main.py` 仍为单入口。  
- **环境变量**：根目录 `.env` 仅放 DASHSCOPE 等与 AI/密钥相关变量；前端 `.env` 仅放 `VITE_API_BASE_URL` 等前端所需变量；禁止提交真实 API Key 到版本库。

---

## 五、检查清单（开发/合并前）

- [ ] 前端新请求均通过 `api.js`，且 baseURL 使用环境变量。  
- [ ] Java 新接口路径以 `/api` 开头；转发 Python 的 URL 使用 `PYTHON_URL`。  
- [ ] Python 新接口在 `/api` 下，且与 Java 转发路径一致。  
- [ ] 未在代码中硬编码 API Key、端口或前端地址（生产）。  
- [ ] 本文档与 README 中相关接口说明已更新。  
- [ ] 前端 `npm run lint`、Java 编译、Python 导入与关键路径测试通过。

遵守以上约束可最大程度避免前后端联调失败、环境不一致和接口漂移问题。如有例外需求，需在文档中注明原因并同步更新约束。

---

## 2026-04-11 前置知识图谱接口补充

- 前端新增独立“背景补课”页签，所有请求继续集中走 `frontend/src/services/api.js` 的 `backgroundKnowledge` 方法。
- Java 新增 `POST /api/background-knowledge`，只透传 JSON 到 Python `POST /api/background-knowledge`，不写入 H2。
- Python `BackgroundKnowledgeRequest` 兼容旧 `{ paper_topic, user_knowledge_level }`，并新增 `{ pdfId, paperSkeleton, paperStructure }`。成功响应包含 `{ status, pdfId, paper_topic, user_knowledge_level, graph, learning_path, background_knowledge, rag_sources, neo4j }`。
- Neo4j 只作为可选持久化增强：配置 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 时尝试写入；未配置或连接失败不得阻断接口成功。
- `docker-compose.yml` 中 Neo4j 必须保留在 `neo4j` profile 下，默认启动不得依赖该服务。
