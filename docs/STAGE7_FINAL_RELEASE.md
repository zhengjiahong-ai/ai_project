# 阶段7正式入口验收

2026-10-10。结论：当前设计边界完成，阶段0–7按当前范围验收。统一任务界面已成为默认入口。

| 检查 | 实际结果 |
| --- | --- |
| 根地址 | http://localhost:5173/ 直接显示任务导航、论文/成果与对话三栏，无需预览参数。 |
| 论文与刷新恢复 | 在v26任务打开真实LightGaussian，19页PDF加载；刷新后任务、当前论文、页码和91%缩放保持，对话和成果仍可访问。 |
| 保存成果 | 实际打开原生成成果，正文、来源及已保存状态可见。刷新回到论文，成果保留并可再次打开；不声称中栏的成果选中状态跨刷新恢复。 |
| 回退入口 | ?unified=0 实际打开旧阅读IDE及研究Agent兼容界面；仅作为兼容回退，不改变新产品主路径。反向补丁检查通过，未实际回滚已交付代码。 |
| 共享路径 | /share/deadbeef?unified=1 仍进入原共享页，并显示无效链接状态；后端404对应。未创建公共分享、不宣称有效共享报告端到端实测。 |
| 构建与自动回归 | 切换后前端48文件303项通过，类型检查和生产构建通过；Python十个相关文件262项通过。Java48项既有当前契约证据保留，本次未修改Java也未重复测试。 |
| 数据保持与契约 | 12历史任务11收据保持。新v26操作身份和结果、消息及成果正文不变；打开论文正常更新新任务focusedPaperId、revision、updatedAt，收据内嵌当前任务快照随之更新。7完整Schema样例通过、5错误样例拒绝，跨材料/请求归属404。 |

真实v26批判7条独立判断通过，聊天425字，保留压缩、帧率及质量取舍。原模型响应和原保存成果一致，最终只读核验新增Provider0、任务写入0。阶段4详见STAGE4_ACCEPTANCE.md；阶段5、6及前期报告保留各自实测范围。

默认入口改动位于frontend/src/main.jsx。证据目录为docs/stage2-evidence/，主要文件：stage7-default-final.png/txt、stage7-default-paper-before-refresh.txt、stage7-default-paper-after-refresh.txt、stage7-default-artifact-after-refresh.txt、stage7-default-artifact-reopened.txt、stage7-default-legacy.txt、stage7-default-share.txt、stage7-default-final-state.json，以及stage7-default-tests/typecheck/build.log。

当前服务为Vite5173、Java8081、Python8000、GROBID8070。Java继续使用backend-java/target/stage0-data原验收库，本轮未切换数据库路径、清库或导入旧研究项目。执行mvn clean前须备份该target内的数据库；长期部署持久化目录另按实际环境配置，本次验收不等于生产部署。

用户取消完整新手流程，省略独立Edge恢复，两项免验且不计实测通过。当前不支持OCR、整篇多页图文导出；复杂公式仍结合原图核对。批判定性概述不作为完整显著性公式推导证据，T等因子应以原文公式为准。已有旧部分结果和失败收据保持历史状态，修复不会替用户改写正文。生产构建保留大包体提示，首次载入性能仍有优化空间。
