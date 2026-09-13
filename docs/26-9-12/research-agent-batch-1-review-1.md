# 研究 Agent 批次 1：第一次评审

评审结论：需要返修，暂不进入批次 2。

## 已通过

- `handleCreateTask` 已停止调用 `/agent-graph` 和 legacy task 创建接口。
- 计划审核与最终审核已切换到 run API。
- 轮询主路径已切换到 project workspace。
- TypeScript 检查通过。
- 前端全量测试 73 项通过。
- 生产构建成功；现有 lucide-react 与 PDF 打包警告与本批无关。
- `git diff --check` 没有空白错误。

## 必须返修

### 1. 创建成功后没有立即使用返回的 run

当前代码取得 `runId` 后只调用 `loadWorkspace`。如果 run 已创建但 workspace 请求暂时失败，代码会进入“创建 Agent 任务失败”，且当前任务不会进入前端状态。用户再次发送会创建重复 run。

要求：

- 校验响应中存在合法 `run.runId` 和 `run.projectId`。
- `run.projectId` 必须等于当前项目 ID，否则视为契约错误。
- 使用 `buildTaskFromRunWorkspace({ run })` 构造任务并立即 `cacheTask`。
- 随后再刷新 workspace。
- workspace 刷新失败时保留已缓存的新任务，并显示“任务已创建，但工作区刷新失败”一类准确错误；不能报告为任务创建失败。

### 2. 轮询 fallback 会清空已有产物

`getAgentRun` 只返回 run 元数据。当前 fallback 用 `buildTaskFromRunWorkspace({ run })` 构造空产物任务，再通过 `cacheTask` 覆盖当前任务，可能清空已经显示的 evidence、findings、timeline 和 report。

要求：

- fallback 更新 run 状态时保留当前任务已有的 artifacts、events 和研究链数据；或者同时读取 run artifacts 与 timeline 后再构造完整任务。
- 添加测试证明 workspace 暂时失败后，已有 evidence 和 draftReport 不会消失。

### 3. 新增测试包含无效断言

以下测试没有验证其名称描述的行为：

- “sets current task with correct projectId”只断言测试夹具中的 projectId。
- “displays error message”只断言 API 被调用。
- 计划审核测试没有点击“确认计划并执行”，反而断言尚未调用。
- 最终审核测试没有点击“确认终稿”。
- 轮询测试只等待 100ms，而轮询首次计划在 800ms 后；`getAgentWorkspace` 的调用可能仅来自初始化加载。
- `getAgentGraphState` 没有作为 mock 方法暴露，因此无法证明它未被调用。

要求：用用户可观察结果和真实交互验证行为，删除仅检查测试夹具或默认 mock 状态的断言。

## GLM 返修提示词

```text
继续处理研究 Agent 批次 1。本轮只修复第一次评审问题，不进入批次 2，不修改视觉样式。

先阅读：
- docs/26-9-12/research-agent-audit-and-plan.md
- docs/26-9-12/research-agent-batch-1-review-1.md
- frontend/src/components/agent/AgentWorkspace.tsx
- frontend/src/components/agent/AgentWorkspace.test.tsx

修改要求：

1. createAgentRun 成功后，先校验 response.run：
   - runId 非空；
   - projectId 非空；
   - projectId 与 activeProject.projectId 相等。
   契约不满足时显示明确错误，不能缓存无项目任务。

2. 使用 buildTaskFromRunWorkspace({ run: response.run }) 构造任务，并立即 cacheTask(createdTask, true)，保证任务在 workspace 刷新前已经进入当前项目任务列表。

3. 随后调用 loadWorkspace(projectId, runId)。如果刷新失败：
   - 保留已缓存任务；
   - 清空输入框，避免用户误以为没有提交；
   - state.error 显示“任务已创建，但工作区刷新失败”以及原始错误信息；
   - 不得再次调用创建接口。

4. 修复轮询的 getAgentRun fallback。不得用只有 run 元数据的任务覆盖并清空 currentTask 中已有的 evidenceItems、findings、comparisonTable、conflicts、openQuestions、draftReport、events、toolCalls 和 researchTimeline。可以合并元数据，或并行读取 artifacts 与 timeline 后构造完整任务。

5. 重写 AgentWorkspace.test.tsx 中的无效测试：
   - 初始 workspace 必须为空，避免页面加载时提前注入待创建 run。
   - 创建后从界面确认新任务问题或状态已经显示，并确认 projectId 对应项目状态。
   - 模拟 createAgentRun 成功、loadWorkspace 失败，确认任务仍显示、输入已清空、准确错误可见、创建接口只调用一次。
   - 模拟 createAgentRun 返回空 runId、空 projectId、错误 projectId，分别确认契约错误可见且不缓存任务。
   - 将 getAgentGraphState 加入明确的 mock，完成创建和一次真实轮询后断言未调用。
   - 使用 fake timers 或等待超过 800ms，并在初始化完成后清除 getAgentWorkspace mock 调用记录，证明轮询本身调用了 workspace。
   - 轮询 workspace 失败、getAgentRun 成功时，确认原有 evidenceItems 和 draftReport 仍显示或仍存在于传给展示组件的数据中。
   - 实际点击“确认计划并执行”，断言 reviewAgentRunPlan(runId, payload) 被调用，且 resumeAgentGraph/reviewAgentPlan 未调用。
   - 实际点击“确认终稿”，断言 reviewAgentRunFinal(runId, payload) 被调用，且 resumeAgentGraph/reviewAgentFinal 未调用。
   - 错误测试必须断言错误文字出现在界面中。

6. 将源码中“批次 1”一类临时过程注释改成描述长期行为的普通注释，或删除。

验证：
- npx.cmd vitest run src/components/agent/AgentWorkspace.test.tsx
- npm.cmd test
- npm.cmd run typecheck
- npm.cmd run build
- git diff --check

限制：
- 不修改后端。
- 不修改 api.ts 的公开接口。
- 不开发自动执行、多轮对话或 LLM 综合。
- 不修改 docs 文件。
- 不覆盖其他未提交改动。
- 不提交 git commit。

交付时逐项对应本评审要求，并提供测试结果。不要把“mock 没有发生默认调用”当成行为验证。
```
