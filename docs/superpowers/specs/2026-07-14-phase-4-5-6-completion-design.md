# Phase 4/5/6 Completion Design

> 补齐阶段四（v0.4.0）、阶段五（v0.5.0）、阶段六（v0.6.0）的缺口，将所有新能力接入前端 UI 和用户工作流。

## 背景

CHANGELOG 中记录的阶段四/五/六共 17 个模块的 Python 代码已全部实现并包含真实算法逻辑。但存在以下缺口：

1. **3 个模块未注册为 Agent 工具**：`research_dialogue.py`、`reproducibility_checker.py`、`research_monitor.py` 的公开函数未在 `tool_registry.py` 中注册，Agent 编排器无法调用。
2. **`reproducibility_checker.py` 存在安全和兼容性问题**：使用 `rm -rf`（Windows 不兼容），通过 `subprocess.run(["bash", "-c", cmd])` 直接在宿主机执行 git clone + pip install + python main.py，无任何隔离。
3. **所有 17 个模块的前端接入为零**：用户无法从 UI 发起论文写作、研究监控、实验复现验证等操作；Agent 产出的结构化数据（元分析、假设引擎、推理链等）以原始 JSON 展示，无可视化。

## 范围

### 维度一：后端补齐

#### A. 工具注册

在 `tool_registry.py` 中新增 8 个工具注册：

| 模块 | 注册工具名 | 安全范围 | 关键输入 |
|------|-----------|---------|---------|
| `research_dialogue` | `generate_clarification_question` | read_only | question, findings, conflicts, gaps, roundNumber |
| `research_dialogue` | `incorporate_user_feedback` | read_only | question, userAnswer, currentDirection |
| `research_monitor` | `create_research_monitor` | restricted | question, sources, frequency |
| `research_monitor` | `check_new_publications` | restricted | monitorId |
| `research_monitor` | `get_monitor_digest` | read_only | monitorId |
| `research_monitor` | `list_research_monitors` | read_only | — |
| `research_monitor` | `deactivate_research_monitor` | restricted | monitorId |
| `reproducibility_checker` | `verify_reproducibility` | restricted | paperId |

工具总数：31 → 39。每个工具均需 `tool_registry` 标准注册：version 1.0.0、完整 inputSchema/outputSchema、safetyScope（含 access/dataScopes/networkAccess/sideEffects/sensitiveOutput）、trace step 包裹、counter 记录。

#### B. reproducibility_checker 安全修复

**问题**：
- `subprocess.run(["rm", "-rf", tmp])` — POSIX only，Windows 崩溃
- `subprocess.run(["bash", "-c", cmd])` — 宿主机直接执行任意命令
- `git clone` + `pip install` + `python main.py` — 完全无沙箱

**方案**（复用现有 `code_worker/runner.py` 的 Docker 沙箱基础设施）：

1. `rm -rf` → `shutil.rmtree(tmp, ignore_errors=True)`（与 `code_worker/runner.py:275` 一致）
2. 新增 `PIXIU_ALLOW_REPRODUCIBILITY` 环境变量，默认 `false`。为 `false` 时工具返回 `status=disabled`。
3. GitHub URL 白名单：`_find_code_repo()` 中只放行 `github.com` host，拒绝 gist、gitlab、bitbucket 等。
4. 沙箱执行函数 `_run_docker_sandbox_cmd()` 替代 `_run_sandbox_cmd()`：
   - 复用 `WORKER_IMAGE_DIGEST`（Python 3.13.9）
   - `--network none`、`--read-only`、`--cap-drop ALL`、`no-new-privileges`、固定 seccomp
   - 仓库目录只读挂载到 `/input/repo`
   - 输出目录独立临时挂载到 `/output`
   - CPU 60s hard limit、256 MiB 内存、32 PID
   - 执行完成后强制 kill → rm → 残留核验 → 临时目录清理
5. `pip install` 阶段不联网——依赖必须在 `requirements.txt` 中声明且预先存在于镜像中（或跳过 install，直接尝试 import）。由于无法保证第三方依赖在镜像中预装，实际执行策略改为：检测到 `requirements.txt` 有外部依赖时返回 `verdict=unable_to_verify, reason=dependencies_not_preinstalled`，仅当代码仅使用标准库时尝试执行。

#### C. Agent 编排增强

在 `agent_orchestrator.py` 中：

1. **研究对话循环**：新增 `awaiting_clarification` 状态。编排器在证据矛盾或稀疏时调用 `generate_clarification_question`，用户回答后调用 `incorporate_user_feedback`，调整方向后继续。最多 3 轮。
2. **工具选择池**：编排器的 LLM prompt 中自动包含 `tool_registry.list_tools()` 返回的工具摘要，新注册的 8 个工具自动进入可用池。
3. **领域专家**：在 `AgentRunCreateRequest` 中新增可选 `domain` 字段。编排器在 planning 阶段调用 `activate_domain_specialist(domain)`，将返回的领域工具列表、搜索策略、评估标准注入 Planner 的 system prompt。
4. **论文写作作为终态可选产出**：Agent run `succeeded` 后，`generate_paper_draft` 工具可用。调用时自动填充当前 run 的 findings/evidence/conflicts。

API 变更：
- `POST /api/agent-projects/{projectId}/runs` 请求体新增可选 `domain: str`
- `POST /api/agent-runs/{runId}/clarification` 新增接口，提交用户对追问的回答
- `GET /api/agent-projects/{projectId}/workspace` 响应新增 `pendingClarification` 字段

---

### 维度二：前端深度接入

#### D. 新独立面板

**D1. PaperWriterPanel.jsx** — 论文写作面板

- **位置**：阅读 IDE 右侧功能区新增"论文写作"标签页
- **交互流程**：
  1. 输入区：研究问题（必填）、论文标题（可选）、引用来源勾选（当前论文 findings + Agent run evidence）
  2. 生成按钮 → 调用 `generate_paper_draft` 工具 → 显示分节生成进度（Abstract → Introduction → Related Work → Methodology → Results → Discussion → Conclusion）
  3. 预览区：Markdown 实时渲染（复用 `MarkdownContent.jsx`），支持分节内联编辑
  4. 导出区：下载 Markdown（`.md`）、LaTeX（`.tex`）、BibTeX（`.bib`）三个文件
  5. 保存到工作台：论文草稿作为 artifact 存入底部工作台（`artifactModel.js` 新增 `paper_draft` 类型）
- **状态模型**：`paperWriterModel.js`（归一化工具响应、分节状态、编辑缓存）
- **复用**：Agent run 成功后的"生成论文草稿"按钮复用此面板的预览+导出部分（内联模式）

**D2. ResearchMonitorPanel.jsx** — 研究监控面板

- **位置**：Agent 工作区左侧新增"研究监控"入口（与项目列表并列）
- **交互流程**：
  1. 监控列表：每个监控卡片显示问题、来源标签（arXiv/PubMed）、最后检查时间、活跃状态开关
  2. 创建监控：问题输入 → 来源多选 → 频率选择（手动 / 每日）→ 调用 `create_research_monitor`
  3. 手动检查：点击"立即检查" → 调用 `check_new_publications` → 新论文列表（★ 评级、相关度分数、标题、摘要摘要）
  4. 摘要视图：调用 `get_monitor_digest` → Markdown 渲染
  5. 论文操作：每条新论文可一键加入论文库（`POST /api/rag/add-literature`）或创建 Agent 项目（预填论文标题）
  6. 删除/停用：调用 `deactivate_research_monitor`
- **状态模型**：`researchMonitorModel.js`
- **调度说明**：首版仅手动检查。前端记录上次检查时间并提示"距上次检查已 X 小时/天"。后续可添加 APScheduler 后端定时任务。

#### E. Agent 结果增强卡片

在 `AgentWorkspaceMainSections.jsx` 中，根据 `toolCalls[*].toolName` 选择专用渲染组件。遵循现有 `InsightCard` 折叠/展开模式，默认折叠摘要、可展开详情。所有卡片跟随全局明暗主题。

| 工具名 | 新组件 | 文件 | 核心可视化 |
|--------|--------|------|-----------|
| `meta_analyze` | `MetaAnalysisCard` | `MetaAnalysisCard.jsx` | 森林图（Recharts 水平散点+误差线）、异质性统计卡（Q/I²/tau²）、Egger 检验 p 值、GRADE 评级徽章 |
| `generate_and_verify_hypotheses` | `HypothesisCard` | `HypothesisCard.jsx` | 假设卡片列表，每条 statement + prediction + verdict 颜色徽章 + 置信度环形图 |
| `adjudicate_conflict` | `ConflictAdjudicationCard` | `ConflictAdjudicationCard.jsx` | Pro vs Con 左右对比布局，评分维度条形图（venue/recent/methodology/citations），赢家标签 |
| `trace_reasoning_chain` | `ReasoningChainCard` | `ReasoningChainCard.jsx` | 水平流程图：Claim → Source → Source → Summary，stance 颜色编码（绿/红/蓝） |
| `expand_citation_graph` | `CitationGraphCard` | `CitationGraphCard.jsx` | 力导向图（`react-force-graph-2d`），节点悬停显示标题/作者/年份 |
| `extract_chart_data` | `ChartAnalysisCard` | `ChartAnalysisCard.jsx` | Recharts 复现原图表（根据 chartType 选 bar/line/scatter）+ 数据系列表格 |
| `cross_lingual_search` | `CrossLingualCard` | `CrossLingualCard.jsx` | 按语言分组的结果表，标题（原文+中文翻译）、Provider、去重标记 |
| `adversarial_review` | `AdversarialReviewCard` | `AdversarialReviewCard.jsx` | 红色/琥珀色 counter-arguments 列表，置信度调整前后对比条，警告标记 |
| `activate_domain_specialist` | `DomainSpecialistBadge` | `DomainSpecialistBadge.jsx` | 紧凑徽章：领域图标 + 启用工具数 + 评估标准摘要 tooltip |
| Agent findings 增强 | `EvidenceSections` 现有组件增强 | `AgentWorkspaceEvidenceSections.jsx` | 每条 finding 底部新增"存入记忆"和"并行研究"按钮 |

#### F. Agent 工作区增强

**F1. 工具能力面板**

`AgentWorkspaceSidebar.jsx` 中新增"可用能力"折叠区：
- 通过轻量接口或前端常量展示 39 个工具的名称和图标
- Agent run 执行中高亮被调用的工具（绿色脉冲）
- 可展开查看每个工具的描述和安全范围摘要

**F2. 领域选择器**

`AgentWorkspaceMainComposer.jsx` 创建任务表单中新增"研究领域"下拉：
- 选项：通用 / 计算机科学 / 医学 / 生物学 / 物理学 / 经济学
- 选择后 `domain` 字段随 run 创建请求发送
- `agentWorkspaceModel.js` 的 `buildAgentRunCreatePayload` 映射新字段

**F3. 研究对话交互**

Agent run 在执行过程中进入 `awaiting_clarification` 状态时：
- 新增 `ClarificationCard.jsx` 组件：展示 1-2 个追问 + 文本输入框
- 用户提交后调用 `POST /api/agent-runs/{runId}/clarification`
- Run 继续执行，最多 3 轮追问
- 追问和回答记录在时间线中

**F4. 论文写作入口**

Agent run `succeeded` 后，在结果区顶部显示"✏️ 生成论文草稿"按钮：
- 点击后以 inline 模式展开 PaperWriterPanel 的预览+导出部分
- 数据自动填充当前 run 的 findings/evidence/conflicts
- 用户无需离开 Agent 工作区即可完成论文草稿生成

---

### 实施顺序

```
第1步: 后端 — 注册3个缺失模块 (A)         ~8个工具 + trace counter
第2步: 后端 — 修复reproducibility (B)      shutil + Docker沙箱 + 环境变量门控
第3步: 后端 — Agent编排增强 (C)            orchestrator prompt + domain + clarification状态
第4步: 前端 — 新面板 D1+D2                PaperWriterPanel + ResearchMonitorPanel
第5步: 前端 — Agent结果卡片 (E)           10个新卡片组件 + EvidenceSections增强
第6步: 前端 — 工作区增强 (F)              能力面板 + 领域选择 + 研究对话
第7步: 端到端验证 — npm test + pytest + 手动 smoke
```

---

### 不变更项

- 不修改现有 `/api/chat`、`/api/upload`、`/api/critical-reading` 等阅读 IDE 接口
- 不修改 Java 网关路由（新接口由前端直连 Python Agent API，与现有 Agent 链路一致）
- 不修改数据库 schema（research_monitor 使用独立 SQLite 文件，已在代码中定义）
- 不引入新的 Python 或 npm 依赖（所有新组件复用现有 Recharts、react-force-graph-2d、react-markdown 等）
- 不修改 Docker Compose 编排
- 不新增付费 LLM Provider

### 风险

| 风险 | 缓解 |
|------|------|
| `reproducibility_checker` Docker 沙箱中 pip install 无网络 | 仅尝试标准库代码；有外部依赖时返回 `unable_to_verify` 而非失败 |
| 39 个工具对 Agent 编排器 prompt 长度压力 | prompt 中仅包含工具名+一句话描述，完整 schema 按需查询 |
| 前端 10+ 新组件导致 bundle 增大 | 全部 lazy load（`React.lazy`），仅 Agent 工作区使用时加载 |
| `research_monitor` 无后端定时调度 | 首版仅手动检查；前端提示距离上次检查时间 |
| `meta_analysis` 森林图在暗色模式下可读性 | 使用 CSS 变量引用主题色，Recharts 通过 `ResponsiveContainer` + 动态 fill/stroke |
