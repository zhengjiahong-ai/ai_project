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
- 轮询任务进度和阶段状态。
- 展示时间线事件、工具调用、证据片段、对比表、冲突候选、开放问题和报告草稿。
- Agent 工具调用会记录内部工具版本和结构化安全范围；内部注册层在执行前后严格校验输入与输出，非法参数不会进入 handler。
- 服务端按项目返回 Agent 任务历史，刷新、换浏览器或服务重启后可恢复项目历史。
- Agent 终态任务会保存脱敏 trace summary，服务重启后仍可按 `traceId` 恢复关键调用、预算和耗时计数。
- Deep Research 和 Agent 都支持在任务创建及计划审查阶段显式授权只读外部学术检索；只有内部证据不足时才会调用白名单 Crossref，并在来源卡和报告引用中区分外部证据。
- 外部 Provider 失败、超时或预算耗尽时任务会保留内部证据和未解决缺口，以脱敏原因降级，并继续进入最终人工审查。
- 前端快照仍按项目保存任务历史，作为旧接口或临时失败时的 fallback。
- Agent 报告草稿、跨论文对比表和单条关键证据可以加入工作台；报告与对比表归入进入 Agent 时的当前论文，证据卡同时保留来源论文、页码、章节、项目和任务标识。未打开当前论文时保存入口会禁用。

当前 AI 效果边界：

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
- 切换项目时优先从服务端恢复历史任务，本地 `tasksByProjectId` 只作为 fallback。
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

Python AI 服务内部已经将单论文 Deep Research 拆为 `research_planner.py`、`research_executor.py`、`research_aggregator.py`，并将多论文 Agent 研究的计划、工具调用摘要、证据聚合和报告综合拆到 `agent_orchestrator.py`。Deep Research 和 Agent 的真实冲突会读取已有背景图谱的一跳邻域，补充来源覆盖说明；无图谱时自动降级，报告仍要求人工核查且不会自动裁决。需要隔离 Agent 或图谱状态库时可设置 `AGENT_STATE_DB_PATH`、`KNOWLEDGE_GRAPH_DB_PATH`。

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

受限 code-native 能力目前只有安全设计，尚未实现 Worker、沙箱、执行 API、审批 UI 或内部工具。唯一候选场景被限定为：对用户确认的一份带表头 UTF-8 CSV，使用不可修改的 Python 3 标准库模板生成有界描述统计 JSON；不支持任意 Python、Shell、联网、第三方分析库、图表或多文件处理。P5-02 若不能实测证明隔离、资源限制和可靠清理，将停止后续接入。完整边界见 `docs/CODE_EXECUTION_SECURITY_PLAN.md`。

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
