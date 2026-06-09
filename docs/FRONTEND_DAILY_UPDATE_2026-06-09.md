# 2026-06-09 前端修改整理

## 1. 今日目标

今天的前端修改主要围绕四个方向展开：

- 把原本割裂的功能入口串成一条更符合论文阅读习惯的工作流
- 在不改后端接口的前提下，提升前端的上下文承接、等待体验和交互引导
- 修复与旧版本本地数据、当前后端接口之间的兼容性风险
- 缓解右侧工作区过于拥挤的问题，减少界面压迫感

## 2. 已完成的主要改动

### 2.1 阅读流重构

在 `frontend/src/App.jsx` 中完成了工作流化框架改造：

- 增加三阶段阅读流：
  - `浅读解构`
  - `深度探究`
  - `知识内化`
- 将原有功能 tab 重新纳入阶段化阅读路径
- 增加“当前研读上下文”卡片
- 增加“推荐下一步”卡片
- 把原本平铺的工具入口改造成更明显的流程引导

### 2.2 右侧功能区的交互优化

对右侧工作区做了多轮压缩和整理：

- 右栏默认宽度从 `38%` 提升到 `42%`
- 左侧 PDF 区默认宽度从 `62%` 调整到 `58%`
- 阶段条改成横向可滚动的紧凑 chip
- “当前研读上下文”和“推荐下一步”改成响应式双卡布局
- 压缩了 section tabs 和功能 tabs 的 padding 与占高

### 2.3 功能按钮默认隐藏

根据最新需求，顶部两排功能按钮现在默认收起：

- `阅读助手 / 分析研究 / 资产沉淀`
- `批判阅读 / 背景补课 / 引导学习 / 深度研究` 等功能按钮

当前交互方式：

- 默认只显示一个 `功能导航` 入口
- 点击后展开导航按钮组
- 再次点击可收起

这样做的目的是：

- 减少右栏初始拥挤感
- 把注意力优先留给当前页面的实际内容
- 仍然保留快速切换能力，不影响熟悉流程后的高效使用

### 2.4 面板内容和提示语优化

以下组件都做了“先摘要、后细节”的信息组织优化，并加强了用户与 AI 的区分：

- `frontend/src/components/ChatPanel.jsx`
- `frontend/src/components/PaperAnalysis.jsx`
- `frontend/src/components/CriticalAnalysisPanel.jsx`
- `frontend/src/components/BackgroundKnowledgePanel.jsx`
- `frontend/src/components/SocraticQuestionsPanel.jsx`
- `frontend/src/components/DeepResearchPanel.jsx`
- `frontend/src/components/PdfViewer.jsx`
- `frontend/src/components/BottomWorkbench.jsx`

重点包括：

- 减少一次性抛出过多内容
- 增强“用户输入 / AI 回答 / 系统提示”的视觉区分
- 优化慢接口场景下的等待文案和中间态
- 为后续资产沉淀提供更自然的入口

### 2.5 底部工作台重构

`frontend/src/components/BottomWorkbench.jsx` 已从普通“笔记/卡片堆放区”改为更明确的研读沉淀台：

- 按 lane 分组：
  - `inbox`
  - `evidence`
  - `argument`
  - `draft`
- 支持编辑、置顶、回源、转笔记等操作
- 更贴近“论文研读后逐步沉淀”的真实使用方式

## 3. 兼容性与稳定性修复

### 3.1 已修复的问题

本轮已确认并修复以下真实问题：

- `frontend/src/components/SocraticQuestionsPanel.jsx`
  - 存在源码级语法损坏
  - 已按 UTF-8 重新整理并修复

- `frontend/src/components/PdfViewer.jsx`
  - 旧版高亮缓存可能缺少：
    - `chatHistory`
    - `actionLabel`
    - `sourceAnchorId`
    - `position.pageIndex`
  - 已新增高亮记录归一化逻辑，保证旧数据可安全打开

### 3.2 已确认兼容的部分

已完成对以下方向的兼容性检查：

- 旧 IndexedDB 本地缓存恢复
- 旧 artifact/workbench card 数据恢复
- 旧 Socratic session 数据恢复
- 深度研究任务恢复与轮询
- 当前后端接口字段适配
- `App.jsx` 与各面板组件的传参适配

总结报告已单独保存到：

- `docs/FRONTEND_FINAL_COMPATIBILITY_REPORT.md`

## 4. 本地验证情况

今天没有继续尝试 Docker 外完整构建，按当前项目运行方式改为做轻量验证。

已完成的本地检查：

- `frontend/src/components/PdfViewer.jsx` 语法级检查通过
- `frontend/src/components/SocraticQuestionsPanel.jsx` 语法级检查通过
- 以下 smoke tests 通过：
  - `frontend/src/utils/socraticSessionModel.test.js`
  - `frontend/src/components/artifactModel.test.js`
  - `frontend/src/components/deepResearchPanelModel.test.js`
  - `frontend/src/services/api.test.js`

## 5. 今日变更涉及文件

核心改动文件：

- `frontend/src/App.jsx`
- `frontend/src/index.css`
- `frontend/src/components/ChatPanel.jsx`
- `frontend/src/components/PaperAnalysis.jsx`
- `frontend/src/components/CriticalAnalysisPanel.jsx`
- `frontend/src/components/BackgroundKnowledgePanel.jsx`
- `frontend/src/components/SocraticQuestionsPanel.jsx`
- `frontend/src/components/DeepResearchPanel.jsx`
- `frontend/src/components/PdfViewer.jsx`
- `frontend/src/components/BottomWorkbench.jsx`

文档文件：

- `docs/PAPER_READING_WORKFLOW_FRONTEND_SPEC.md`
- `docs/FRONTEND_FINAL_COMPATIBILITY_REPORT.md`
- `docs/FRONTEND_DAILY_UPDATE_2026-06-09.md`

## 6. 当前状态

当前可以认为已经进入“最终收尾前”的稳定阶段：

- 主体工作流已经成型
- 关键兼容性问题已补齐
- 右栏拥挤问题已明显缓解
- 功能导航已默认收起，界面更干净

## 7. 下一步建议

建议下一步只做两件事：

1. 在 Docker 环境中按阅读主链路做一轮烟测
2. 根据烟测结果，只修小问题，不再做大范围结构调整

## 8. 本轮追加改动

在当天后续迭代中，又补了一轮“右栏减压 + 功能页交互拆解”：

- 右侧顶部辅助区现在默认折叠为一条摘要栏
- 鼠标靠近右侧顶部时，阶段条、上下文、下一步建议和功能导航会自动展开
- 问答面板进一步压缩了顶部说明区、消息卡留白和输入区高度
- `篇章解构` 已改成三步阅读模式：
  - 先看全局
  - 再看目录
  - 最后进细节
- `批判阅读` 已改成三步分析模式：
  - 先看判断
  - 再看主张
  - 最后看证据
- `背景补课` 已改成三步补课模式：
  - 先补什么
  - 怎么补
  - 看依据

这轮改动的目的，是把后端一次性返回的大块信息拆开，改成更接近“用户逐步推进”的阅读节奏，而不是把所有内容同时堆在页面里。
