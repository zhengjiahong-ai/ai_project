# v9：简洁数值表达及原始字体运算符恢复

2026-10-09。代码提交：`43a08ed`、`3007020`。本批新增Provider调用0；此前用户批准的v7三例均已各执行一次，累计25个真实案例已用完。阶段4–7仍未整体通过，统一界面保持`?unified=1`。

## 已修复及实测范围

- 已经同论文原文核验的作者数值短语由服务端呈现为简洁中文，例如“从782MB到45MB”“SSIM仅下降0.007”“超过200 FPS”。不改引用、数值、单位、方向或上下界；相邻模板改变指标、方向或界限时拒绝。未支持的语法明确保留原文，不猜译。
- LightGaussian物理第4页原始Type1字体程序明确记录81为producttext、88为summationdisplay、89为productdisplay；ToUnicode缺少这些映射，实际PDF.js绘制编码也分别为81/88/89。现在在翻译输入构建前恢复对应∏/∑，没有根据CMEX字体名称或Q/X/Y猜测。原始正文对象不被修改，普通变量Q不变。
- 转换后的CFF字体字符名称存在偏移，早期方案已丢弃；生产实现只读原始PDF字体程序，并与实际绘制编码匹配。字体重名、Encoding覆盖、缺失字形、无法读取或不支持的字体回退原抽取内容。文档解析缓存复用，字体异步加载有有限等待。新增依赖pdf-lib固定1.17.1。
- 实际PDF输入复核恢复4个大型运算符，并保留8个原式标记及区域。T式输入包含∏，后端mathContext标记product，但仍明确structureVerified=false；没有把扁平抽取的上下限或完整公式结构标成已核对。

## 自动及原生路径验证

| 验证 | 结果与边界 |
| --- | --- |
| Python相关完整回归 | 11文件203项通过，2条已有依赖弃用警告，见`stage4-readable-v9-complete-tests.log`。最后数值负例断言复核14项通过。 |
| 前端完整回归 | 48文件291项及19组Node检查通过，见`stage6-glyph-v9-full-tests.log`；这是最后字体异步等待修复之前的完整结果。 |
| 最后字体异步等待修复 | 3文件22项通过，含真正延后解析字体的用例，见`stage6-glyph-v9-font-ready-tests.log`。未把前一次完整套件冒充最后版本完整重跑。 |
| 当前类型与构建 | `stage6-glyph-v9-current-typecheck.log`及`stage6-glyph-v9-current-build.log`通过；构建保留体积警告，没有抑制。 |
| 原分析缓存走当前原生服务/检索 | `stage4-readable-v9-native-final.log`：未改原模型JSON，Provider调用禁止，索引前后哈希均4708c07a18e305c6aed2bdb183e439ba2de02fcd5ccfa8dc867b44afbf1bf3f9。合格结果保留，未支持论断仍丢弃，比较仍是partial，不能计真实模型成功。 |
| 实际PDF字体/布局 | `stage6-math-font-v9.json`、`stage6-math-glyph-v9.json`及对应inspect日志：原始编码、绘制编码、恢复结果、8个标记和T式区域可核对；没有新生成。 |
| 原翻译缓存走当前翻译服务 | `stage6-glyph-v9-native.log`：输入能明确给出product，旧“减去全部不透明度”译文仍被拒绝，3个合格块保留；4个缓存替代批次，Provider0。此探针使用完整布局，未应用历史TEI排除区域，block-1图注在旧缓存中缺失，block-5语义错误；不能说该探针只有1段失败，也不能视为v7界面输入完全重演。 |

## 浏览器及历史记录

独立的离线展示任务`stage4-readable-display-20261009-v9`明确标注“离线展示夹具，不计真实模型验收”。实际页面中简洁中文比较表可读，来源、比较范围、原文依据与尚待确认默认折叠。DOM及截图为`stage4-readable-v9-browser.json/png`。

真实PDF阅读页保持LightGaussian物理第4/19页，原图可见、阅读工具存在，浏览器无错误/警告，记录`stage6-glyph-v9-reading-browser.json/png`。PDF.js原文文本层没有被替换；字体恢复作用于翻译输入，不宣称原文DOM已经恢复Unicode，也不宣称新译文已生成。

AI空闲重启加载记录`stage4-readable-v9-reload.log`；只读状态复核`stage4-readable-v9-state.json`显示AI/GROBID/RAG健康、原阅读任务revision17和两个v7失败收据逐字段保持。旧v8状态快照没有改写内容。所有本批实际UI显示为本地缓存/离线展示，无新增翻译重试。

## 未完成范围与下一步

A11：修复后新生成批判与解释/比较的实际内容尚未验证。A14：运算符输入修复已测，但新译文语义、保存及新内容导出尚未验证。A18：独立Edge客户端此前多次连接失败，同一浏览器新标签或HTTP不能替代。A20：真实新手观察尚未执行。

新三例的具体材料、身份、验收点和一次提交规则见`stage4-reading-v9-case-plan.json`，当前状态为待授权，没有执行。授权后仅运行批判、两句解释＋比较及LightGaussian第4页翻译；保留原始失败结果和旧成果。未获新范围授权不向Provider发送论文正文。
