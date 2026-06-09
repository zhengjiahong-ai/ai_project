# 前端最终兼容性收尾报告

## 0. 编码说明

- 本项目源码按 `UTF-8` 处理。
- 终端或部分 shell 输出里出现的中文乱码，已按“显示环境问题”处理，不等同于源码真实损坏。
- 本轮检查中，只有会影响解析或运行的真实语法 / 数据兼容问题才计入缺陷。

## 1. 审核范围

本轮重点检查以下三类兼容性：

- 旧版本本地持久化数据是否还能被当前前端读取
- 当前前端改造后的组件是否仍然适配现有后端接口
- `App.jsx` 到各工作流组件的传参与状态流转是否一致

已重点核对的文件包括：

- `frontend/src/App.jsx`
- `frontend/src/services/api.js`
- `frontend/src/services/localDb.js`
- `frontend/src/services/workspaceSession.js`
- `frontend/src/hooks/usePaperArtifacts.js`
- `frontend/src/hooks/usePaperSession.js`
- `frontend/src/components/PdfViewer.jsx`
- `frontend/src/components/ChatPanel.jsx`
- `frontend/src/components/PaperAnalysis.jsx`
- `frontend/src/components/CriticalAnalysisPanel.jsx`
- `frontend/src/components/BackgroundKnowledgePanel.jsx`
- `frontend/src/components/SocraticQuestionsPanel.jsx`
- `frontend/src/components/DeepResearchPanel.jsx`
- `frontend/src/components/BottomWorkbench.jsx`
- `frontend/src/components/artifactModel.js`
- `frontend/src/components/deepResearchPanelModel.js`
- `frontend/src/components/insightCardModel.js`

## 2. 结论摘要

整体结论：**当前这版“工作流化前端”与现有后端接口总体兼容，和旧版本本地数据也基本兼容，可进入 Docker 环境做最后一轮手测。**

本轮共确认了两类真实问题：

1. `SocraticQuestionsPanel.jsx` 存在真实语法损坏，已修复。
2. `PdfViewer.jsx` 对旧版高亮记录缺少归一化，旧缓存点开弹窗时存在潜在报错风险，已补齐兼容处理。

除以上两点外，未发现新的“必须改后端”问题，也未发现当前工作流包装引入新的接口字段依赖。

## 3. 已确认兼容的部分

### 3.1 本地数据库与旧缓存

- IndexedDB 仍使用 `PixiuAcademicDB_v6` / `LOCAL_DB_VERSION = 6`，本轮没有改动 store 结构。
- 论文级缓存的主 store 名称未变：
  - `pdfStore`
  - `historyStore`
  - `analysisStore`
  - `notesStore`
  - `deconstructStore`
  - `highlightStore`
  - `sessionStore`
  - `translationStore`
  - `backgroundKnowledgeStore`
  - `artifactStore`
- `workspaceSession.loadPaperSnapshot()` 的读取顺序与 `usePaperSession.restorePaperState()` 的恢复逻辑保持一致，没有引入新的必填缓存字段。

### 3.2 工作台卡片与旧资产数据

- `artifactModel.normalizeInsightArtifact()` 已兼容旧字段：
  - `id -> artifactId`
  - `isPinned -> pinned`
- `usePaperArtifacts.replaceWorkbenchCards()` 会统一走 `normalizeInsightArtifacts()`，因此旧工作台卡片进入新版“研读沉淀台”时可自动补齐默认值。
- `BottomWorkbench.jsx` 对旧卡片中缺少 `lane/tags/userNote/sourceAnchorId` 的情况有兜底：
  - `lane` 默认回落到 `inbox`
  - `tags` 缺失时按空数组处理
  - `userNote` 缺失时不渲染
  - `sourceAnchorId` 缺失时只是不显示“回到原文”按钮

### 3.3 苏格拉底引导学习会话

- `normalizeSocraticSession()` 兼容旧 session 结构：
  - 缺少 `reviewSuggestions` 时回落为空数组
  - 缺少 `evidenceQuality` / `missingAspects` 时自动补默认值
  - `currentIndex/currentQuestion/isComplete` 会自动推断
- `App.jsx` 提交答案时仍然使用现有后端字段：
  - `evaluation.masteryLevel`
  - `evaluation.feedback`
  - `evaluation.hint`
  - `evaluation.coveredAspects`
  - `evaluation.missingAspects`
  - `evaluation.evidenceQuality`
  - `nextIndex`
  - `nextQuestion`
  - `finalSummary`
  - `reviewSuggestions`
- 前端没有要求后端新增字段。

### 3.4 深度研究任务

- `DeepResearchPanel.jsx` 统一通过 `normalizeResearchTask()` 和 `normalizeTraceSummary()` 读取数据。
- 对以下字段均有降级容错：
  - `status`
  - `stage`
  - `progress`
  - `findings`
  - `report`
  - `traceId`
  - `error`
- `App.jsx` 中研究任务恢复、轮询、trace 拉取仍基于现有接口：
  - `/research-tasks`
  - `/research-tasks/brief-preview`
  - `/research-tasks/:id`
  - `/research-tasks/latest`
  - `/traces/:id`

### 3.5 问答、批判阅读、背景补课

- `ChatPanel.jsx` 新增的 `contextTitle/contextSummary/nextActionHint` 都是可选展示字段，`App.jsx` 已完整传入。
- 聊天消息仍兼容原有后端返回的多种格式：
  - `reply`
  - `message`
  - `data.reply`
  - `sentenceSourceMap`
  - `rag_sources`
- `CriticalAnalysisPanel.jsx` 和 `BackgroundKnowledgePanel.jsx` 都基于已有返回数据做展示增强，没有要求后端追加新结构。

## 4. 本轮发现并已修复的问题

### 4.1 `SocraticQuestionsPanel.jsx` 语法损坏

问题：

- 掌握度映射对象键值在源码层面被破坏，属于真实语法错误，不是终端显示问题。

处理：

- 已整体重写该组件为 UTF-8 正常文本。
- 同时统一优化了这块的提示语，让“用户回答”和“AI 评价”的区分更清晰。

影响：

- 修复后该面板可以正常通过本地语法检查。

### 4.2 旧版高亮记录兼容性不足

问题：

- `PdfViewer.jsx` 原先直接信任 `initialHighlights`。
- 如果旧缓存里的高亮缺少 `chatHistory`、`actionLabel`、`sourceAnchorId`、`position.pageIndex` 等字段，点击历史高亮弹窗时有概率触发异常。

处理：

- 已增加 `normalizeHighlightRecord()` / `normalizeHighlightCollection()`。
- 在加载 `initialHighlights` 时统一补齐以下默认字段：
  - `sourceAnchorId`
  - `actionId`
  - `actionLabel`
  - `chatHistory`
  - `position.pageIndex/top/left/width/height`
  - `highlightAreas`
  - `isLoading`

影响：

- 旧版高亮缓存现在可以安全显示，最差也会以“历史划线记录”模式降级展示，不会因为字段缺失而中断阅读流程。

## 5. 未发现适配问题但需要说明的点

### 5.1 `PdfViewer` 额外透传参数

- `App.jsx` 当前向 `PdfViewer` 传入了 `translationLayoutIndex`。
- `PdfViewer.jsx` 本身没有消费这个 prop。
- 这不会报错，也不会影响运行，只是一个“当前未使用的透传参数”。

建议：

- 后续如果不打算在 `PdfViewer` 中直接使用它，可以在下一轮清理无效传参，降低维护负担。

### 5.2 独立 esbuild bundle 检查中的环境噪音

- 使用裸 `esbuild --bundle` 检查 `App.jsx` 时，出现了两类环境相关提示：
  - `VERSION?raw` 是 Vite 的资源导入写法，独立 esbuild 不认识
  - `rehype-katex` / `remark-math` 在独立 bundle 路径下解析失败
- 这类问题**不等同于 Docker/Vite 运行时一定失败**，更像是“脱离 Vite 环境做裸 bundle 时的工具差异”。

说明：

- `frontend/package.json` 中已经声明了 `rehype-katex` 与 `remark-math` 依赖。
- 因此本轮不把它认定为接口或数据兼容问题。

## 6. 已执行的本地验证

### 6.1 语法级检查

以下文件已通过本地 `esbuild` 非 bundle 语法检查：

- `frontend/src/components/PdfViewer.jsx`
- `frontend/src/components/SocraticQuestionsPanel.jsx`

### 6.2 兼容性相关测试

已通过的本地 smoke tests：

- `node frontend/src/utils/socraticSessionModel.test.js`
- `node frontend/src/components/artifactModel.test.js`
- `node frontend/src/components/deepResearchPanelModel.test.js`
- `node frontend/src/services/api.test.js`

## 7. 剩余风险

以下风险不构成当前阻塞，但建议在 Docker 里做最后手测确认：

1. 旧 `highlightStore` 里如果存在更早期、结构更残缺的数据，本轮虽已做高亮归一化，但仍建议验证“点击历史划线 -> 打开弹窗 -> 继续追问 -> 存为笔记”整条链路。
2. 由于本轮没有实际跑 Docker 页面，像 `react-force-graph-2d`、PDF viewer、布局滚动条等可视化区域还需要浏览器级确认。
3. `notes` 标签页现在已转为“资产总览入口”，核心沉淀功能已下移到底部工作台，需确认老师/用户是否接受这个入口语义变化。

## 8. 建议的 Docker 烟测清单

建议按下面顺序快速手测一遍：

1. 打开一篇旧论文缓存，确认能正常恢复：
   - PDF
   - 问答历史
   - 高亮
   - 笔记
   - 工作台卡片
2. 点击一条历史高亮，确认弹窗能正常打开，不报错。
3. 在 PDF 中重新划词，分别试一次：
   - `解释`
   - `翻译`
   - `拆解`
   - `批判`
   - `记边注`
4. 在问答区发送一条消息，确认：
   - 用户 / AI 角色样式清晰区分
   - 上下文 chip 正常显示
   - “推荐下一步”跳转正常
5. 启动一次苏格拉底学习，完成至少一轮回答，确认：
   - 问题推进正常
   - 掌握度 badge 正常
   - 证据判断 / 缺口提示正常
6. 发起一次背景补课、批判阅读、深度研究，确认都能正常展示已有后端结果。
7. 把问答、边注、批判结果加入底部工作台，确认：
   - lane 分组正常
   - 编辑 / 置顶 / 回源 / 存为边注 正常
8. 刷新页面后，确认数据仍能恢复，且阅读流上下文不会错位。

## 9. 当前建议

可以进入“下下步收尾”：

- 不建议再做大范围结构调整
- 优先在 Docker 中完成一轮完整烟测
- 如果烟测稳定，就可以开始准备答辩时的“工作流化改造总结”与演示脚本
