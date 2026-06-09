# 前端变更总结（2026-06-09）

### 2026-06-09 23:40 v0.1.19

1. **完成论文阅读工作流前端重构**：将原本偏功能堆叠的界面重新组织为“浅读解构 - 深度探究 - 知识内化”的连续阅读流程，在 `frontend/src/App.jsx` 中补齐阶段导航、当前研读上下文、推荐下一步动作与顶部辅助导航折叠逻辑，强化不同功能之间的串联关系。
2. **重构右侧核心功能页交互**：重新设计 `ChatPanel`、`PaperAnalysis`、`CriticalAnalysisPanel`、`BackgroundKnowledgePanel`、`SocraticQuestionsPanel`、`DeepResearchPanel` 的信息节奏与展示层级，把后端一次性返回的大块内容拆成更适合逐步阅读与参与的前端交互，增强用户输入、AI 输出和系统提示之间的区分度，并优化长耗时任务下的等待反馈。
3. **优化论文库与进度表达逻辑**：重构 `LibrarySidebar`，把原本仅基于页码的“阅读进度”升级为更严谨的“研读完成度”，综合页码覆盖、篇章解构、问答、翻译、背景补课、批判阅读、引导学习、深度研究、笔记与工作台卡片等多维信号；新增 `frontend/src/utils/studyProgress.js` 负责计算与兼容旧本地数据。
4. **重做底部工作台与成果导出能力**：将 `BottomWorkbench` 从简单的卡片堆叠区重构为“总览 / 整理卡片 / 复盘边注 / 成果导出”四视图工作台，采用左侧列表、右侧检视器的整理模式，并新增 `frontend/src/utils/workbenchExport.js`，支持将当前论文成果导出为 Markdown、JSON 与纯文本，便于汇报、归档与二次加工。
5. **补齐兼容性处理与文档沉淀**：在不修改后端接口的前提下完成本轮前端适配，兼容旧版 IndexedDB 本地数据与当前接口结构；同步维护 `docs/PAPER_READING_WORKFLOW_FRONTEND_SPEC.md`、`docs/FRONTEND_FINAL_COMPATIBILITY_REPORT.md`、`docs/FRONTEND_DAILY_UPDATE_2026-06-09.md`，并明确源码文件按 UTF-8 处理，终端可见乱码仅视为显示问题而非文件本身异常。
