# Pixiu Academic Assistant

Pixiu Academic Assistant 是一个面向学术论文阅读的 AI 工作台。它把 PDF 解析、单论文阅读辅助、证据化分析，以及新的多论文 Agent 研究工作区整合在同一个项目里。

## 非开发用户快速开始

如果你只需要使用系统阅读和研究论文，请直接查看 [用户指南](docs/USER_GUIDE.md)。指南覆盖 PDF 上传与论文库、问答、划词解释、翻译、背景补课、引导学习、批判阅读、Deep Research、多论文 Agent 研究、工作台保存和常见失败处理。

## 当前技术栈

- `frontend/`：React 19 + Vite 7 前端工作台。
- `backend-java/`：Spring Boot 网关与轻量持久化层。
- `ai-service-python/`：FastAPI AI 服务，负责解析、检索、分析、任务执行和 trace。
- `grobid`：PDF 结构抽取服务。
- `ChromaDB + sentence-transformers`：当前论文和内部文献库检索。
- `H2`：Java 侧论文记录和聊天历史持久化。
- `SQLite`：Python 侧 Deep Research 任务快照持久化。
- `IndexedDB`：浏览器侧阅读会话和工作区状态持久化。
- `SQLite` 与宿主 artifact 目录：保存受限代码执行任务、防篡改审计链和待执行 CSV。

## 当前能力

### 阅读 IDE

主阅读工作区已经打通端到端链路：

- 上传并解析 PDF。
- 上传时联合检查 PDF 文本层与 GROBID 解析文本；扫描件或低文本 PDF 会保留阅读能力，并在论文库和篇章解构面板提示先 OCR 或更换文字版 PDF。
- 提取论文骨架和章节结构。
- 基于证据的单论文问答。
- 划词或术语解释。
- 逐页翻译。
- 当前论文驱动的自适应背景补课：分两阶段识别概念与前置关系，区分当前论文支持和模型推断，并展示节点/边证据覆盖率。
- 苏格拉底式引导学习。
- 带证据主张的批判阅读。
- 带 trace 和持久化快照的 Deep Research 异步任务。
- Deep Research 报告在结果区置顶展示，默认呈现净化后的用户视图：`deepResearchPanelModel.ts` 的 `sanitizeResearchReport` 会按后端已知的二级标题与 bullet 前缀，剥离“执行统计 / 证据收集摘要 / 来源追溯”整段以及每条 finding 的“JUDGE评分 / 来源分布 / 跨源一致性”等开发可观测噪声；面板标题栏提供“开发者详情”开关（默认关闭），开启后改用后端返回的原始全文，并额外显示 trace 调试、外部检索预算、Task/Trace ID 与 JUDGE/覆盖度等细节。
- Deep Research 报告生成（后端 `research_aggregator.py`）已修正多处排版与内容缺陷：研究问题正确内插（不再出现字面 `+ question +`）、执行摘要不再与综合判断逐字重复、证据对比表改为列表输出（前端未启用 GFM 表格也能正常渲染）、来源类型统一映射为中文标签（避免 `current_paper` 被前端数学预处理误判为下标公式）、交叉验证与争议地图 claim 按词/句边界截断（不再半词截断或破坏列表结构）。
- 右侧推荐下一步会根据当前阅读状态给出 2-3 个动作，可继续单论文阅读、发起 Deep Research，或带当前论文进入 Agent 研究。
- 当前页译文和单章节篇章解构摘要可以加入当前论文工作台，并保留页码或章节信息。

### Agent 研究

Agent 工作区已经不再只是静态原型壳。当前已经具备第一版可用的端到端链路：

- 创建和切换 Agent 项目。
- 删除 Agent 项目。
- 新建项目时从论文库搜索并多选论文，草稿中可移除已选论文。
- 从阅读 IDE 的推荐下一步进入 Agent 时，当前打开论文会作为 Agent 新项目草稿的默认已选论文。
- 向项目挂载多篇论文。
- 创建异步 Agent 任务。
- Python 侧已完成 Agent 资源化迁移：公开主路径切到 `workspace + runs`，内部状态按 `project / run / review / artifacts / timeline / workspace` 拆分建模与持久化，旧 `agent-tasks` 形态仅保留为兼容适配层。
- 轮询任务进度和阶段状态。
- 展示时间线事件、工具调用、证据片段、对比表、冲突候选、开放问题和报告草稿。
- Agent 工具调用会记录内部工具版本和结构化安全范围；内部注册层在执行前后严格校验输入与输出，非法参数不会进入 handler。
- 服务端按项目返回 Agent 任务历史，刷新、换浏览器或服务重启后可恢复项目历史。
- Agent 终态任务会保存脱敏 trace summary，服务重启后仍可按 `traceId` 恢复关键调用、预算和耗时计数。
- Deep Research 和 Agent 都支持在任务创建及计划审查阶段显式授权只读外部学术检索；只有内部证据不足时才会调用白名单 Crossref，并在来源卡和报告引用中区分外部证据。
- 外部 Provider 失败、超时或预算耗尽时任务会保留内部证据和未解决缺口，以脱敏原因降级，并继续进入最终人工审查。
- Agent 推理管线已拆分为三个独立节点：`evidence_weighing` 对每条证据计算四维可信度（来源类型信任度、页码锚定覆盖、跨来源一致性、JUDGE 评分），输出加权证据；`cross_paper_reasoning` 在加权证据上做确定性跨论文分析，产出共识（consensus）、互补（complementary）、矛盾（contradictory）和证据缺口（gaps）四类洞察；`conflict_resolution` 对冲突候选进行自动裁决（可信度差距 ≥ 0.4 且高权重方 ≥ 0.8 时自动判定），并负责 follow-up 循环的信息增益跟踪与计数器更新。
- follow-up 循环采用信息增益驱动的自适应终止策略：每轮计算新增证据占比，连续两轮增益低于 10% 时自动停止；同时受安全上限（max 5 轮）、证据饱和（≥ 12 条）和无缺口信号三重保护。节点实现位于 `agent_langgraph_reasoning.py`，确定性可信度公式位于 `evidence_credibility.py`。
- 前端快照仍按项目保存任务历史，作为旧接口或临时失败时的 fallback。
- Agent 报告草稿、跨论文对比表和单条关键证据可以加入工作台；报告与对比表归入进入 Agent 时的当前论文，证据卡同时保留来源论文、页码、章节、项目和任务标识。未打开当前论文时保存入口会禁用。

### 论文写作（基础版，部分可用）

本地设计稿将论文写作定义为研究流程的可选终态产出：读取研究问题，以及 Agent 的 findings、evidence 和 conflicts，生成 Abstract、Introduction、Related Work、Methodology、Results、Discussion、Conclusion 和参考文献；用户可以分节预览、编辑、重新生成，并导出 Markdown、LaTeX、BibTeX，或保存到工作台。设计稿还计划在 Agent 任务完成后提供内联入口。

当前实现完成了基础生成和文件导出链路，但尚未达到上述完整交互目标：

| 能力 | 当前状态 | 实际行为 |
| --- | --- | --- |
| 阅读 IDE 入口 | 已实现 | 右侧“论文写作”标签可输入研究问题和可选标题，并调用 `POST /api/generate-paper-draft`。Python 与 Java 网关均有对应路由。 |
| 草稿生成 | 部分实现 | 后端生成 6～7 个英文结构化章节。Abstract 和 Conclusion 调用 LLM；Introduction、Methodology、Results、Discussion 和 Related Work 主要由固定模板与传入数据拼装。 |
| 研究证据接入 | 接口具备，独立入口未接通 | API 可接收 findings、evidenceItems 和 conflicts；阅读 IDE 当前只传研究问题与标题，不会自动检索当前论文，也不会把 Deep Research 或 Agent 结果注入请求，因此从独立入口生成时通常没有真实 findings 和参考文献。`sourceIds` 虽进入请求模型，但后端生成器当前没有使用它筛选或加载来源。 |
| 分节预览 | 当前不可用 | 后端返回 `sections` 数组，前端按键值对象读取，数据契约不一致，真实接口响应无法形成分节预览。现有前端 E2E 使用 mock 对象响应，没有覆盖这一真实契约问题。 |
| 分节编辑 | 界面存在，未形成闭环 | 编辑只更新浏览器内的 section 状态，不会重新生成 Markdown、LaTeX 或 BibTeX；随后下载或保存到工作台仍使用生成时的旧内容。 |
| 分节重新生成 | 当前不可用 | 前端会发送 section 与 existingSections，但后端内部仍按章节数组处理，不能正确替换指定章节；失败只写入控制台，没有用户可见错误。 |
| 生成进度 | 占位实现 | 请求是一次性同步返回，没有逐节流式生成；生成过程中进度条不会随章节推进。 |
| 导出 | 基础可用 | 前端可下载 `.md`、`.tex`、`.bib`。后端还写出 `pixiu-paper.sty`，但前端没有下载入口。LaTeX 只是源码输出，不会编译 PDF。 |
| 保存到工作台 | 部分实现 | 可以把生成时的 Markdown 保存为 `paper_draft` 产物；分节编辑后的内容不会同步进入该 Markdown。 |
| Agent 完成后生成草稿 | 尚未接入当前界面 | `PaperWriterPanel` 保留 currentRun 预填代码，但当前 Agent 工作区没有渲染该面板或“生成论文草稿”入口，阅读 IDE 使用时也没有传入 currentRun。 |
| 服务端文件落盘 | 已实现 | 每次生成会在 `PAPER_DRAFT_DIR`（默认 `ai-service-python/data/paper_drafts/`）下写入 Markdown、LaTeX、BibTeX 和 `.sty` 文件；目前没有草稿列表、版本管理、恢复或删除界面。 |

因此，当前功能适合生成一个可下载的初始英文综述骨架，不应视为已经完成的、证据约束的论文写作系统。正式用于论文写作前，需要先修正章节响应契约，并接通来源选择、证据引用、编辑后重新渲染和 Agent 结果入口。

### LLM 缓存

为减少重复 LLM 调用开销，Python AI 服务内置了基于 SHA-256 + SQLite 的响应缓存：

- 以 `(model, temperature, system_prompt, user_prompt)` 拼接后取 SHA-256 作为缓存键，命中时直接返回缓存响应，跳过实际 API 调用。
- 默认 TTL 60 分钟（可通过 `PIXIU_LLM_CACHE_TTL_MINUTES` 调整），过期条目自动逐出。
- 缓存模式通过 `PIXIU_LLM_CACHE_MODE` 控制，默认 `exact` 启用精确匹配；设为其他值则禁用缓存。
- 数据库默认路径 `ai-service-python/data/llm_cache.sqlite3`，可通过 `PIXIU_LLM_CACHE_PATH` 指定。
- 线程安全，所有读写操作由 `threading.Lock()` 保护；LLM 客户端每次调用自动记录 `llmCacheHits` / `llmCacheMisses` 计数。

### API 限流

FastAPI 层已集成基于 token bucket 算法的请求限流中间件：

- 按请求路径自动分桶：`/api/agent-*tasks|runs` 对应 Agent 桶（默认 10 RPM），`/chat|/explain|/socratic` 对应聊天桶（默认 30 RPM），`/translate` 对应翻译桶（默认 10 RPM），其余路径归入全局桶（默认 60 RPM）。
- 每个 IP 在每个桶中独立计费，burst 容量为 `rate / 2`（最少 1 个 token）。
- 令牌按时间线性恢复；超限时返回 `429` 并附带 `Retry-After` 头。
- 通过 `PIXIU_RATE_LIMIT_ENABLED` 全局开关；各桶 RPM 分别通过 `PIXIU_RATE_LIMIT_GLOBAL_RPM`、`PIXIU_RATE_LIMIT_AGENT_RPM`、`PIXIU_RATE_LIMIT_CHAT_RPM`、`PIXIU_RATE_LIMIT_TRANSLATE_RPM` 配置。

### 分享功能

支持将完成的 Agent 研究报告生成为只读分享链接：

- 前端 Agent 面板可对已完成报告生成分享 token（UUID4 十六进制字符串）。
- Token 及其关联的项目标题、报告正文保存到 SQLite（默认 `ai-service-python/data/shares.sqlite3`），7 天自动过期。
- 分享页面 `/share/{token}` 为独立只读视图：仅展示报告 Markdown 正文、项目标题和过期时间，不暴露 PDF 正文、完整证据、API key、trace、聊天历史或工作台内容。
- 过期或无效 token 返回中文提示“分享链接不存在或已过期”。

当前 AI 效果边界：

- 全局“执行审批”中心支持上传单个 UTF-8 CSV，审查固定描述统计脚本、输入、运行时和配额后批准隔离执行，并在核验产物与审计摘要后单独批准发布。未发布产物不会进入研究报告、Agent evidence 或工作台。

- Agent 结论已经从通用占位文本升级为有证据依据的规则型草稿。
- 这仍是第一版规则型综合，不是最终形态的复杂多步推理系统。
- Deep Research 和 Agent 的后端编排边界已经拆出 planner/executor/aggregator/orchestrator 模块，现有使用流程不变，但后续接入 LangGraph 或 Deep Orchestrator 时可以优先替换这些内部层。
- 已提供默认关闭的只读 MCP adapter 原型；它仅以本机 `stdio` 独立启动，不挂载 FastAPI，也不新增网络监听或 Java 转发。
- 背景知识图谱只使用当前论文、论文骨架和显式主题，不读取论文库中的其他论文，也不会自行联网；无当前论文片段支持的知识和关系会明确标记为模型推断。
- 只读外部学术检索已接入 Deep Research 和 Agent 的证据不足分支，但生产默认仍关闭。P3-17 严格评测因 Crossref `hitAt5=0.333333` 未达到 `0.8` 门槛，当前不进入常规启用或灰度。

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
KNOWLEDGE_GRAPH_DB_PATH=ai-service-python/data/knowledge_graph.sqlite3

# 默认不要设置；仅启动本机只读 MCP adapter 时显式设为 true
PIXIU_MCP_ENABLED=false

# MCP adapter 传输方式：stdio（默认，独立进程）或 sse（挂载到 FastAPI 主端口）
PIXIU_MCP_TRANSPORT=stdio

# SSE 监听地址与端口（仅 PIXIU_MCP_TRANSPORT=sse 时生效）
PIXIU_MCP_SSE_HOST=127.0.0.1
PIXIU_MCP_SSE_PORT=8001

# 可选的 MCP 认证 token（不设置则无认证）
PIXIU_MCP_AUTH_TOKEN=

# 仅测试使用；生产环境不要启用
PIXIU_LLM_MODE=deepseek
# PIXIU_LLM_FIXTURE_PATH=ai-service-python/tests/fixtures/llm_responses.json
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

可选的只读 MCP adapter 与 FastAPI 独立。只有 MCP 客户端显式传入开关时才启动：

```json
{
  "mcpServers": {
    "pixiu-readonly": {
      "command": "python",
      "args": ["-m", "mcp_adapter"],
      "cwd": "C:/path/to/ai_project/ai-service-python",
      "env": {
        "PIXIU_MCP_ENABLED": "true"
      }
    }
  }
}
```

该入口只公开 `read_paper_skeleton`、`retrieve_current_paper`、`retrieve_library`。当前论文检索禁止 `includeAll=true`，并对结果数量和文本长度使用比内部工具更严格的 MCP 预算。不要把该 `stdio` 进程转发为公网服务。

MCP adapter 也支持 SSE 传输模式，挂载到 FastAPI 主端口（`http://localhost:8000/mcp/sse`），需在 `.env` 中配置：

```env
PIXIU_MCP_ENABLED=true
PIXIU_MCP_TRANSPORT=sse
# 可选认证
PIXIU_MCP_AUTH_TOKEN=your-secret-token
```

SSE 模式下客户端直接连接 `http://localhost:8000/mcp/sse`，无需单独启动进程。

GROBID 建议继续通过 Docker 启动：

```bash
docker compose up -d grobid
```

## Agent 工作区说明

今天 Agent 工作区完成了比较完整的一轮迭代，当前包括：

- Planner 生成计划后进入人工审查，可增删改研究指令、选择 focused papers 并调整约束，确认后才执行检索。
- Aggregator 生成草稿后进入终稿审查，可逐项标记冲突和缺证据为“已核查”或“仍需跟进”，确认后任务才完成。

- 更完整的右侧 Agent 工作区展示，而不是简单 mock 面板。
- 拆分后的前端子组件，便于后续维护。
- 基于服务端 `GET /api/agent-projects/{projectId}/tasks` 的项目级任务历史。
- 切换项目时优先读取 `GET /api/agent-projects/{projectId}/workspace`，再按需回退到服务端历史任务；本地 `tasksByProjectId` 只作为 fallback。
- 项目卡片支持确认后删除，删除不会重排已有项目标题编号，后续默认编号继续单调递增。
- Python 侧会把 Agent 项目、任务和事件摘要写入 SQLite 快照，服务重启后可恢复项目、latest task 和终态任务输出。
- 完整显示 `draftReport`，不再只截断展示前几个段落。
- 阅读 IDE 与 Agent 共用来源 chip、片段详情和跳转语义；无页码来源会展开缓存片段，不显示伪跳转。
- Agent evidence、冲突候选和报告引用可进入阅读 IDE；跨论文来源会先恢复对应本地论文，再定位到 0-based `pageIndex` 对应页面。
- 前端直连 Python Agent API。
- 异步执行阶段：`planning -> retrieving -> synthesizing -> done`。
- 第一版跨论文冲突检测和基于证据的结论草稿。
- Agent 工作区和顶部“阅读 IDE / Agent 研究”切换按钮已覆盖全局明暗主题切换。

当前限制：

- 服务重启前仍在 `running` 或 `pending` 的 Agent 任务会恢复为 `failed`，并在任务错误和事件摘要中说明被服务重启中断。
- `awaiting_plan_review` 和 `awaiting_final_review` 会持久化并在重启后继续等待用户操作。
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
- Agent 工作区快照，包括项目级任务历史 fallback。
- Agent 默认项目编号游标。

### Java 侧

H2 保存：

- 论文记录。
- 聊天消息。

### Python 侧

Python 保存：

- Chroma 检索索引。
- Deep Research SQLite 快照，默认位置为 `ai-service-python/data/research_tasks.sqlite3` 或 `RESEARCH_TASK_DB_PATH`。
- Agent SQLite 快照，默认位置为 `ai-service-python/data/agent_state.sqlite3` 或 `AGENT_STATE_DB_PATH`；删除项目会同步删除该项目任务和事件摘要，终态任务会随快照保存脱敏 `traceSummary`。
- 背景知识图谱 SQLite 快照，默认位置为 `ai-service-python/data/knowledge_graph.sqlite3` 或 `KNOWLEDGE_GRAPH_DB_PATH`；配置 Neo4j 时仍会同时写入可选镜像。
- 进程内 public trace summary；Deep Research 和 Agent 终态 trace summary 会随 SQLite 任务快照保存。trace counters 包含 LLM、内部检索、重试、截断和外部学术检索调用/缓存/失败/证据/延迟/预算阻止计数；外部检索 query 只保存 hash、长度和 token 数摘要。

Python AI 服务内部已经将单论文 Deep Research 拆为 `research_planner.py`、`research_executor.py`、`research_aggregator.py`，并将多论文 Agent 研究的计划、工具调用摘要、证据聚合和报告综合拆到 `agent_orchestrator.py`。2026-07-08 起，Agent 内部又新增 `agent_run_service.py`、`agent_review_service.py`、`agent_artifact_service.py`、`agent_timeline_service.py`、`agent_workspace_service.py` 和 `agent_state_repository.py`，把执行状态机、审查包、产物、时间线和聚合视图从旧的大型 task snapshot 中拆出来；当前对外主接口已切到 `GET /api/agent-projects/{projectId}/workspace` 与 `agent-runs/*`，旧 `agent-tasks/*` 仅作为 compatibility adapter。Deep Research 和 Agent 的真实冲突会读取已有背景图谱的一跳邻域，补充来源覆盖说明；无图谱时自动降级，报告仍要求人工核查且不会自动裁决。需要隔离 Agent 或图谱状态库时可设置 `AGENT_STATE_DB_PATH`、`KNOWLEDGE_GRAPH_DB_PATH`。

## 验证命令

前端：

```bash
cd frontend
npm.cmd run lint
npm.cmd test
npx.cmd playwright install chromium
npm.cmd run test:e2e
npm.cmd run build
```

`test:e2e` 使用 Playwright Chromium 和测试内 route mock，覆盖 PDF 上传、论文库、阅读面板、研读工作台，以及 Agent 项目创建、外部检索显式授权、外部来源展示、Provider 故障降级、刷新恢复和最终人工审查；无需启动 Java、Python、Docker、真实 Provider 或真实模型服务。首次运行需安装 Chromium。

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

外部检索评测默认离线读取固定 snapshot，不访问 Provider 或 LLM：

```powershell
python -m benchmarks.external_search.provider_benchmark
python -m benchmarks.external_search.effect_benchmark
```

Council 单模型基线首次采样需要显式配置 `DEEPSEEK_API_KEY` 并执行 live 命令；已有真实 snapshot 后，去掉 `--live` 即可离线复算：

```powershell
cd ai-service-python
python -m benchmarks.council.baseline_benchmark --live
python -m benchmarks.council.baseline_benchmark
python -m benchmarks.council.comparison_benchmark --live
python -m benchmarks.council.comparison_benchmark
```

详细数据集、评分口径与脱敏边界见 `docs/council_benchmark.md`。P4-08 真实对照中双 Reviewer 的质量和效用门槛全部通过，但平均延迟为基线 `2.79183x`、平均 token 为 `2.512443x`，超过预设的 `2.5x` 上限，因此已移除 Deep Research 的 Council 生产接入。`council_service.py` 与 benchmark 结论继续保留；项目不配置或使用第二付费 Provider，未来恢复任何生产接入或第二 Provider 都必须另立任务并重新授权。

受限 code-native 能力目前只有不挂载路由的内部 Worker 原型，尚无执行 API、审批 UI、Agent 工具或 MCP 能力。原型仅接受已批准且 digest 匹配的单个 UTF-8 CSV，在固定 Python 3.13.9 Docker 镜像中运行不可修改的标准库模板并返回有界描述统计 JSON 元数据；输入只读、输出目录独立临时挂载，容器无网络、非 root、只读根文件系统且不能访问源码、用户目录或 Docker socket。不支持任意 Python、Shell、联网、第三方分析库、图表或多文件处理。完整边界与后续强制终止、清理门槛见 `docs/CODE_EXECUTION_SECURITY_PLAN.md`。

Python 测试也支持完全离线的固定 LLM 响应，不需要 `DEEPSEEK_API_KEY`，且不会请求 DeepSeek：

```powershell
cd ai-service-python
$env:PIXIU_LLM_MODE = "fixture"
$env:PIXIU_LLM_FIXTURE_PATH = (Resolve-Path ".\tests\fixtures\llm_responses.json")
python -m pytest tests/test_offline_llm.py tests/test_offline_core_paths.py -q
```

CI 使用同名环境变量即可。fixture 文件采用 `schemaVersion: 1`，每个响应包含唯一 `id`、`client`（`default` 或 `translation`）、非空 `promptContains`，以及二选一的 `output` 或 `outputJson`；可选 `usage` 固定 `inputTokens/outputTokens/totalTokens`，缺省时会生成带 `estimated=true` 的确定性估算。所有 marker 都匹配且仅匹配一个响应时才返回固定结果；未匹配、重复匹配或 schema 非法会直接失败，不会回退到真实 API。该模式只用于自动化测试。

## 已知问题

- 某些本地环境如果没有安装 Python 测试依赖，`pytest` 可能不可用。
- Agent 服务当前优先完成框架搭建、链路打通和有意义草稿输出，复杂算法和更强综合质量留给后续迭代。

## 文档导航

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md)：面向非开发用户的单论文阅读与多论文 Agent 研究操作指南。
- [ARCHITECTURE.md](ARCHITECTURE.md)：系统结构、运行链路、持久化边界和模块职责。
- [API.md](API.md)：接口契约、请求响应结构和关键数据形态。
- [CHANGELOG.md](CHANGELOG.md)：变更记录。
