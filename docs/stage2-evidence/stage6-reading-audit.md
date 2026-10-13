# 阶段6首批实际验收

日期：2026-10-08。使用Java现有文件数据库、Vite新版预览 `http://127.0.0.1:5173/?unified=1`。

测试任务 `stage6-reading-demo-20261008`，文档 `stage6-reading-note`。正文为明确标注的人工界面样例，不是模型或论文质量验收。创建脚本重跑只读取已有任务，不覆盖浏览器修改。

浏览器操作：

- 首次打开成果显示Markdown标题、表格及列表，无编辑输入框，阅读按钮选中。
- 点击编辑，改成“界面草稿验收”；切回阅读后显示草稿及“未保存修改”，再编辑仍能继续。
- 点击保存后显示“已保存”，历史新增原始正文。
- 显式恢复原始版本，编辑正文进入历史；切回阅读并刷新后原样例正文完整，仍无编辑输入框。
- 页面内重命名任务为“阶段6：阅读与编辑体验验收”；刷新后保持名称。

只读核验 `verify_stage6_reading.py`：原始Markdown逐字相同、编辑正文在两项历史版本中、任务名称正确，论文和消息数组未改变。收据 `stage6-reading-runtime.json`，截图 `stage6-reading-browser.jpg`。此客户端核验不证明独立浏览器缓存恢复。

自动测试：`npx vitest run src/UnifiedTaskApp.test.jsx src/components/TaskRename.test.jsx src/components/DocumentVersionHistory.test.jsx src/components/DocumentOrganizer.test.jsx`，4文件26项通过。包括空草稿、冲突、恢复、跨任务成果、重命名失败保留及保存期间阻止恢复。最终 `npm run typecheck`、`npm run build` 均通过，仍有第三方pdfjs eval、use client及空vendor-react chunk构建警告。

限制：截图是869×550现有视口；没有据此宣称移动端适配完成。当前Docker未启动，页面显示“暂时无法查询请求记录”；本批未验证AI执行。阶段4内容质量及阶段5独立浏览器恢复仍保留原待验状态。
