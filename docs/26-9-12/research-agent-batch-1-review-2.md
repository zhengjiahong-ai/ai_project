# 研究 Agent 批次 1：第二次评审

评审结论：仍需返修，暂不进入批次 2。本轮正式入口与创建后的状态处理已经基本合格，剩余问题集中在轮询 fallback 的无损合并和测试有效性。

## 已通过

- 新任务只调用 `createAgentRun(projectId, payload)`，没有回退到 `/agent-graph` 或 legacy task 创建接口。
- 创建响应会校验非空 `runId`、非空 `projectId`，并校验 run 归属于当前项目。
- 创建成功后会先用返回的 run 构造并缓存任务，再刷新 workspace。
- workspace 刷新失败时会保留已缓存任务、清空输入框并显示准确错误，不会重复创建 run。
- 计划审核只调用 `reviewAgentRunPlan`，其测试已经通过真实按钮点击验证。
- 源码中的“批次 1”过程注释已经清理。
- 独立执行定向测试：13 项通过。
- 独立执行 TypeScript 检查：通过。
- `git diff --check` 没有空白错误，仅有 Windows 行尾提示。

## 必须返修

### 1. polling fallback 仍不是无损合并

当前代码把 `previousTask.events` 直接作为 `buildTaskFromRunWorkspace` 的 `timeline` 参数。两者字段结构不同：已有 event 使用 `eventId/stage/summary`，原始 timeline 使用 `id/phase/detail|title`。再次规范化后，已有事件会变成空 ID、空阶段和空摘要。

此外，`previousArtifacts` 没有保留 `llmSynthesis` 和 `advancedAnalysis`；新的 run 元数据如果不含 `researchTimeline`，已有研究链也会丢失。`fetchedArtifacts ?? previousArtifacts` 只做对象级选择，非空但缺字段的 artifacts 响应仍可用默认空值覆盖已有数据。

要求：

- 先用 run、成功取得的 artifacts 和成功取得的原始 timeline 构造新任务，再按字段与 `previousTask` 做合并。
- 请求失败或返回中缺少某字段时，保留已有字段。
- 至少无损保留 `evidenceItems`、`findings`、`comparisonTable`、`conflicts`、`openQuestions`、`draftReport`、`events`、`toolCalls`、`researchTimeline`、`llmSynthesis` 和 `advancedAnalysis`。
- timeline 请求失败或没有可用的新事件时，直接在构造完成后使用 `previousTask.events`；不要把规范化后的 events 当作原始 timeline 再传入转换函数。
- 新响应明确提供某字段时使用新值；需要区分“字段缺失/请求失败”和“后端明确返回空集合”。

### 2. 产物保留测试没有验证产物

测试夹具中的 evidence、finding、event 不是产品实际数据结构：

- evidence 使用 `{ id, title }`，证据规范化需要有效的 `sourceId` 和内容/位置字段，因此该数据可能被直接过滤。
- finding 使用 `text`，展示代码读取的是 `summary`。
- event 使用 `{ id, label }`，当前任务事件结构使用 `eventId/type/timestamp/stage/summary`。

测试最后只断言“执行中”状态仍显示，没有断言 evidence、draft、finding 或 event 仍存在，所以即使产物全部丢失也会通过。

要求：使用符合真实模型的夹具，并在 fallback 完成后逐项断言原有证据正文、报告正文、finding 摘要和 event 摘要仍在展示数据中。若这些字段不都直接渲染，可 mock 展示子组件并检查传入的 `currentTask`，或测试抽出的纯合并函数。

### 3. 终稿审核测试与实际 UI 不符

交付报告称 `AgentHumanFinalReview` “当前无 UI”，但 `AgentWorkspaceMainSections.jsx` 已渲染“确认终稿”按钮，`AgentWorkspaceMain.jsx` 会在 `awaiting_final_review` 状态展示该组件。当前测试只断言 API 尚未调用，没有验证最终审核行为。

要求：找到并点击“确认终稿”，断言：

- `reviewAgentRunFinal(TEST_RUN_ID, payload)` 被调用；
- payload 至少包含当前 UI 生成的 `reviewNotes` 和 `riskReviews`；
- `resumeAgentGraph`、`reviewAgentFinal` 没有调用。

同时修正交付报告，不再把该组件描述为无 UI。

### 4. 创建成功 UI 测试仍可能被初始化请求污染

当前测试先让 `getAgentWorkspace` 返回一次空 workspace，之后永久返回含新 run 的 workspace。组件初始化期间可能触发不止一次 workspace 请求，因此新 run 可能在点击发送前已经进入界面，“创建后显示状态”仍可能是假阳性。

要求：

- 初始化阶段始终返回空 workspace，并先断言新任务状态/问题尚未显示。
- 初始化稳定后再切换 mock，使下一次创建后的刷新返回新 run；或者让该用例只依赖 `createAgentRun` 返回值的立即缓存，并保持 workspace 为空。
- 点击后同时断言创建 API 参数、任务问题或状态出现在 UI、任务属于当前项目。

## 给 GLM 的第二次返修提示词

```text
继续处理研究 Agent 批次 1。本轮只修复第二次评审列出的状态合并与测试问题，不进入批次 2。

先阅读：
- docs/26-9-12/research-agent-audit-and-plan.md
- docs/26-9-12/research-agent-batch-1-review-1.md
- docs/26-9-12/research-agent-batch-1-review-2.md
- frontend/src/components/agent/AgentWorkspace.tsx
- frontend/src/components/agent/agentWorkspaceModel.ts
- frontend/src/components/agent/AgentWorkspaceMain.jsx
- frontend/src/components/agent/AgentWorkspaceMainSections.jsx
- frontend/src/components/agent/AgentWorkspace.test.tsx

修改要求：

1. 修复轮询 workspace 失败后的 fallback，使它对 currentTask 做字段级无损合并。
   - 仍然并行请求 getAgentRun、getAgentRunArtifacts、getAgentRunTimeline。
   - 用成功取得的新数据构造 freshTask，再与 previousTask 合并。
   - 请求失败或响应缺少字段时，保留 previousTask 中的 evidenceItems、findings、comparisonTable、conflicts、openQuestions、draftReport、events、toolCalls、researchTimeline、llmSynthesis、advancedAnalysis。
   - timeline 失败或没有可用新事件时，直接保留 previousTask.events。不要把 previousTask.events 当作原始 timeline 传给 buildTaskFromRunWorkspace。
   - 后端明确返回空字段时可以采用空值；代码必须能区分字段缺失与明确为空。
   - run 的 status、stage、progress、error、updatedAt 等元数据以最新 run 为准。

2. 重写 fallback 保留测试。
   - 使用真实字段结构：evidence 至少有 sourceId 和可展示正文；finding 使用 summary；event 使用 eventId/type/timestamp/stage/summary。
   - 同时准备 comparisonTable、conflicts、openQuestions、toolCalls、researchTimeline、llmSynthesis、advancedAnalysis。
   - 模拟 workspace、artifacts、timeline 请求失败而 getAgentRun 成功。
   - fallback 后断言这些旧字段仍存在。可以断言 UI；未直接渲染的字段可通过 mock AgentWorkspaceMain 检查 currentTask，或为抽出的纯合并函数写测试。
   - 不能只断言任务状态。

3. 修复终稿审核测试。
   - awaiting_final_review 状态下等待“确认终稿”按钮出现并点击。
   - 断言 reviewAgentRunFinal(TEST_RUN_ID, expect.objectContaining({ reviewNotes: ..., riskReviews: ... }))。
   - 断言 resumeAgentGraph 和 reviewAgentFinal 未调用。
   - 删除“AgentHumanFinalReview 无 UI”的错误注释与交付说明。

4. 修复创建后 UI 测试的初始化污染。
   - 初始化阶段保持 workspace 为空，确认点击前页面没有新任务状态或问题。
   - 再执行输入与点击；用 createAgentRun 的返回 run 验证任务立即进入 UI。
   - 如需验证刷新结果，只在初始化完全稳定后切换 workspace mock。
   - 不允许第二次初始化请求提前注入 mockWorkspaceResponse。

5. 保留已经通过的入口统一、响应契约校验、刷新失败保留任务、计划审核真实交互等行为。

验证：
- npx.cmd vitest run src/components/agent/AgentWorkspace.test.tsx
- npm.cmd test
- npm.cmd run typecheck
- npm.cmd run build
- git diff --check

限制：
- 不修改后端。
- 不修改 api.ts 的公开接口。
- 不修改视觉布局、颜色、文案和卡片样式。
- 不开发自动执行、多轮对话、证据综合等后续批次功能。
- 不修改 docs 文件。
- 不覆盖其他未提交改动。
- 不提交 git commit。

交付报告必须描述实际执行过的用户交互和断言，不能以“组件没有 UI”或“状态仍显示”替代行为与数据验证。
```
