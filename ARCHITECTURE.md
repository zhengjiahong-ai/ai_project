# Architecture

## 概览

Pixiu Academic Assistant 是一个面向论文阅读的多服务工作台，核心职责分成三层：

1. `frontend`
   - 承担阅读工作台 UI、用户交互、浏览器本地状态与 PDF 渲染
2. `backend-java`
   - 作为浏览器唯一后端入口
   - 负责上传转发、会话历史持久化、统一 `/api` 路由
3. `ai-service-python`
   - 负责 PDF 解析、结构提取、检索、LLM 编排、批判分析、研究任务与 trace

配套依赖：

- `GROBID`: 论文结构化解析
- `ChromaDB + embeddings`: 当前论文与内部文献检索
- `H2`: Java 网关状态存储
- `SQLite`: Python 深度研究任务快照
- `IndexedDB`: 浏览器端阅读资产缓存

## 系统上下文

```text
Browser
  -> Frontend (React/Vite)
  -> Backend Java (/api)
  -> AI Service Python (/api)
  -> GROBID
  -> ChromaDB / internal retrieval
  -> Optional Neo4j
```

## 前端架构

### 核心入口

前端主入口在 `frontend/src/App.jsx`，它把工作台组织为：

- 顶部导航栏 `Navbar`
- 左侧论文库与阅读导航 `LibrarySidebar`
- 中部 PDF 区域 `PdfViewer`、`PdfToolbar`
- 右侧多功能工作区
- 底部沉淀工作台 `BottomWorkbench`

### 功能分区

右侧工作区按阶段划分为三个 section：

- `阅读助手`
  - `chat`
  - `deconstruct`
  - `translation`
- `分析研究`
  - `analysis`
  - `background`
  - `socratic`
  - `deep-research`
- `资产沉淀`
  - `notes`

对应的主要组件：

- `ChatPanel`
- `PaperAnalysis`
- `TranslationPanel`
- `CriticalAnalysisPanel`
- `BackgroundKnowledgePanel`
- `SocraticQuestionsPanel`
- `DeepResearchPanel`

其中 `BackgroundKnowledgePanel` 不再只依赖单一的 `user_knowledge_level` 下拉选择，而是由两类信息共同驱动：

- 显式读者画像 `reader_profile`
  - `selfAssessedFamiliarity`
  - `preferredDepth`
  - `learningGoal`
  - `knownConcepts`
  - `confusingConcepts`
- 隐式行为信号 `behavior_signals`
  - 最近提问次数与问题文本
  - 翻译、标注、笔记、工作台沉淀等使用情况
  - 当前阅读位置与所在功能页

这样背景补课会更接近“围绕当前阅读卡点进行自适应补课”，而不是机械套用固定等级。

### 前端状态组织

`App.jsx` 管理整条阅读会话主状态，包括：

- 当前 PDF 文件与 `pdfId`
- 聊天消息
- 篇章解构结果 `deconstructData`
- 批判阅读结果 `analysisData`
- 背景补课结果
- 苏格拉底学习会话
- 逐页翻译状态
- 深度研究状态
- 本地笔记与工作台资产

核心 hooks：

- `useThemePreference`
- `useAbortableChat`
- `usePaperArtifacts`
- `usePaperSession`
- `useReadingWorkspace`
- `useTaskActivity`

### 浏览器持久化

浏览器使用 `idb` 访问 IndexedDB，封装在：

- `frontend/src/services/localDb.js`
- `frontend/src/services/workspaceSession.js`

IndexedDB 负责保存：

- PDF Blob
- 聊天记录
- 解构结果
- 批判阅读结果
- 高亮和笔记
- 背景补课结果
- 翻译状态
- 苏格拉底会话
- 工作台资产
- 论文库条目

`localStorage` 仅保存轻量 UI 状态：

- 当前激活 tab
- 上次打开的 `pdfId`

## Java 网关架构

### 角色

Java 层不是复杂业务层，而是一个“统一入口 + 简单持久化 + 转发层”：

- 对浏览器暴露固定 `/api`
- 接收上传并转发给 Python
- 保存聊天历史到 H2
- 提供聊天历史恢复接口
- 为 Python 任务类接口补一层统一 HTTP 入口

### 关键类

- `AcademicController`
  - 声明所有 `/api/*` 路由
- `AiService`
  - 执行转发、上传封装、历史读写和错误适配
- `PaperRepository`
  - 保存论文记录
- `ChatMessageRepository`
  - 保存会话消息

### 存储

H2 文件数据库用于保存：

- `Paper`
- `ChatMessage`

这里保存的是“网关层需要的会话数据”，不是完整论文内容。

## Python AI 服务架构

### 入口与路由

- `main.py` 作为 uvicorn 入口
- `app.py` 创建 FastAPI 应用
- `routes/api.py` 注册全部 `/api` 路由

应用启动时会执行 `startup_warmup()`，尝试预热 RAG 后端。

### 代码组织

`ai-service-python` 主要分成四块：

- `core/`
  - PDF/TEI 解析与 outline 构建
- `services/`
  - 聊天、翻译、背景补课、分析、研究任务、trace、安全
- `rag/`
  - RAG 获取与 hybrid 检索包装
- `schemas/`
  - Pydantic 请求模型

### 关键服务

#### `analysis_service.py`

负责：

- 上传 PDF 后驱动 GROBID 解析
- 从 TEI 构建章节树
- 提取摘要与论文结构摘要
- 将正文块写入 RAG
- 批判阅读 `deep_analysis`

输出中最关键的是：

- `paper_skeleton`
- `paper_structure`
- `paper_structure.sections`
- `translationLayoutIndex`

#### `chat_service.py`

负责：

- 术语解释
- 普通聊天
- 苏格拉底式学习
- 逐页翻译入口转发

其中聊天不是简单 prompt 调用，而是一个轻量 agentic RAG 流程：

1. 生成查询计划 `queryPlan`
2. 优先检索当前论文
3. 必要时补充内部文献库
4. 使用 `retrievalJudge` 判断证据质量
5. 必要时自动重试一次
6. 基于证据生成回答并附来源

#### `research_task_service.py`

负责深度研究任务生命周期：

- 研究 brief preview
- 创建研究任务
- 异步执行
- 轮询查询
- 取消任务
- 恢复最近任务快照

任务执行阶段固定为：

- `planning`
- `retrieving`
- `judging`
- `synthesizing`
- `done`

任务状态固定为：

- `pending`
- `running`
- `succeeded`
- `failed`
- `cancelled`

#### `tool_registry.py`

这是 Python 内部能力编排的统一封装层。当前内建工具包括：

- `retrieve_current_paper`
- `retrieve_library`
- `read_paper_skeleton`
- `judge_evidence`
- `generate_background_graph`
- `run_critical_analysis`
- `translate_page`

深度研究优先通过这里调用内部能力，而不是直接散落调用底层模块。

#### `background_knowledge_service.py`

背景补课服务当前采用“显式画像 + 隐式行为”的自适应策略：

- 前端传入 `reader_profile`，表达用户自评熟悉度、补课目标、已掌握与卡点概念
- 前端传入 `behavior_signals`，补充近期提问、翻译、标注、笔记等行为
- Python 将二者归一化为内部 `reader_profile`
- 旧字段 `user_knowledge_level` 仍被接受，但仅作为兼容回退，不再是唯一控制参数

#### `trace_service.py`

为聊天、术语解释、背景补课、批判阅读和深度研究提供轻量 trace：

- 记录阶段
- 记录耗时
- 记录 retrieval / llm 计数
- 保存裁剪后的 request/response 元数据

注意 trace 是脱敏摘要，不保存完整 prompt、API Key 或完整论文全文。

#### `safety_service.py`

负责把论文正文、RAG 片段、页面文本等视为不可信输入，对进入模型的上下文进行包装和约束，降低提示注入风险。

## 解析与检索链路

### PDF 解析链路

```text
upload PDF
  -> Java /api/upload
  -> Python /api/analyze-pdf
  -> GROBID processFulltextDocument
  -> TEI XML
  -> parse_tei_xml + build_document_outline
  -> paper_skeleton / paper_structure / sections
  -> chunking + RAG indexing
```

### 问答链路

```text
Frontend ChatPanel
  -> Java /api/chat
  -> Python chat_service.chat
  -> build_chat_query_plan
  -> retrieve current paper and/or library
  -> judge evidence quality
  -> optional retry
  -> LLM answer
  -> rag_sources + sentenceSourceMap
```

### 批判阅读链路

```text
Frontend CriticalAnalysisPanel
  -> Java /api/critical-reading/{pdfId}
  -> Python /api/deep-analysis
  -> load current paper chunks
  -> analyze 4 axes
  -> structured report
  -> claim support classification
```

### 深度研究链路

```text
DeepResearchPanel
  -> brief preview
  -> create task
  -> ThreadPoolExecutor async run
  -> retrieve current paper first
  -> optional library supplement
  -> evidence judge
  -> synthesize report
  -> persist SQLite snapshot
```

## 存储边界

### 前端 IndexedDB

存“用户工作现场”：

- PDF 文件
- 论文库记录
- 对话
- 翻译
- 笔记
- 高亮
- 工作台资产
- 各功能模块结果

### Java H2

存“网关会话数据”：

- 论文记录
- 聊天历史

### Python SQLite

存“深度研究任务快照”：

- `taskId`
- `traceId`
- `status`
- `stage`
- `progress`
- `question`
- `pdfId`
- `plan`
- `findings`
- `report`
- `error`
- `createdAt`
- `updatedAt`

### Python RAG / Chroma

存“可检索证据片段”：

- 当前论文 chunk
- 论文元数据
- 页码、章节锚点等可用 metadata

## 设计约束

### 当前论文优先

几乎所有智能能力默认遵守：

- 优先使用当前论文证据
- 不足时才补内部文献库
- 不做外部 Web 搜索

### 证据化输出

聊天、解释、背景补课、批判阅读和深度研究都尽量附带：

- `rag_sources`
- `sentenceSourceMap`
- `retrievalJudge`
- `traceId`

### 兼容旧缓存

前端对旧 IndexedDB 缓存采取兼容策略：

- 旧论文可能只有单层目录
- 旧证据可能没有页码和章节锚点
- UI 在缺信息时降级展示，不伪造跳转能力

## 运维与部署

默认通过 `docker-compose.yml` 编排：

- `frontend`
- `backend`
- `ai-service`
- `grobid`
- `neo4j` 可选 profile

关键 volume：

- `java_data`
- `chroma_data`
- `research_task_data`
- `huggingface_cache`
- `grobid_data`
- `neo4j_data`

## 测试与质量控制

前端：

- `npm run lint`
- `npm test`
- `npm run build`

Python：

- `pytest tests -q`

Java：

- `mvn test`

整体设计上，这个项目已经不是单纯“PDF 上传 + 问答”的 demo，而是一个以当前论文为中心、强调证据、可恢复状态和长期沉淀的阅读工作台。
