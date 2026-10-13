# 第三轮真实案例与阅读工具核验（2026-10-08）

本轮授权覆盖同一批 D:\3DGS\paper 中的 LightGaussian 与原始 3DGS 论文片段，发送到当前配置的 https://api.deepseek.com，最多四个固定案例，各执行一次，不自动重试。四个案例额度均已使用；后续修改只做离线验证，没有重新生成。这是案例次数，不等于模型内部调用次数；批判和分批翻译可能各包含多个初始模型调用。

## 真实结果

| 固定案例 | 保留证据 | 验收判断 |
| --- | --- | --- |
| 修复后聚焦批判 | `stage4-critique-v3-attempt.json`、`stage4-critique-v3-receipt.json` | 请求 succeeded，单篇材料范围及发布结构有效。区分了 Table 7 与主方法压缩口径，但重要性指标解释仍遗漏透射率因子 T，内容未通过。 |
| 简短解释＋比较 | `stage4-compose-v3-attempt.json`、`stage4-compose-v3-receipt.json` | 请求 failed，没有可验收成果。执行日志定位到摘录正文匹配校验；后续只读审计19处引用，仅1处不匹配，模型用省略号拼接三段原文。详见 `stage4-compose-v3-quote-audit.json`。保留严格校验，不放宽为未经核验的发布。 |
| LightGaussian 第 4 页翻译 | `stage6-translation-v3-attempt.json`、`stage6-translation-v3-browser.png` | 实际译文在浏览器显示；不是只创建了预留记录。公式被扁平化或缺失，版面出现大块空白且文字过小，内容和覆盖排版未通过。attempt 文件原来的等待文字保留，不改写历史记录。 |
| 第 4 页划词解释 Significance | `stage6-selection-v3-attempt.json`、`stage6-selection-v3-browser.png`、`stage6-selection-v3-runtime.json` | 生成解释并存为笔记，服务端 revision 5 保留选中文字、AI 解释、论文 ID 与零起始页码 3。解释遗漏透射率 T 和体积调整关系，内容未通过。 |

批判的 succeeded 只证明执行和发布结构，不证明事实完整；划词笔记持久化也不证明解释正确。单页翻译的原始版面问题后续已做重排和原图保留，模型公式内容错误仍未通过，详见图文译文核验记录。

## 已做后续修复

1. 前端和解释服务按选中文字所在位置截取上下文，保留附近定义和后续公式，避免固定截取页首。允许 PDF 换行和选择文本的空白差异；不能找到锚点时仍限制长度。提示要求核对可见公式因子及体积调整，抽取损坏时不猜完整公式。
2. 翻译请求使用已有版面过滤器排除独立公式、页脚及解析标注的保留区域，原布局仍保留。整页只有保留内容时不退回纯文本生成。
3. 后端删除缺失段落的自动逐段重试和整页模型兜底。已完成的译文返回 partial，附缺失段落 ID 和简短提示；全部失败时要求手动重试。前端刷新保留部分译文，进入译文视图不自动补发。保存部分译文时，成果标题和正文保留未完成标记。

这些修复没有真实模型再验证。20:12后恢复运行时，Python已加载上下文和部分译文修复；20:54空闲守卫确认无生成任务后，重启加载连续摘录提示修复，健康检查通过。

## 早期本地验证与限制（已解除的阻断保留为历史）

- Python：`..\.venv-refactor\Scripts\python.exe -m pytest tests/test_page_translation_service.py tests/test_reading_context.py -q`，删除死代码后再次运行，10 项通过。
- 前端：选中上下文、翻译状态、PDF 翻译布局、翻译展示模型、成果模型 Node 测试及 `npm run typecheck` 通过。覆盖页尾锚点、跨行选择、大小写差异、上下文长度、部分译文恢复及保存后的未完成标记。
- `npx vitest run src/hooks/usePageTranslation.test.jsx` 在加载 test-setup.js 前因沙箱 realpath EPERM 失败，执行 0 项测试；新增 Hook 测试不能算通过。
- `npm run build` 在解析 main.jsx 时因同类 EPERM 失败，不能声称本批生产构建通过。
- 19:50 后重新连接浏览器时原临时标签不存在；重新打开 localhost:5173 返回 ERR_CONNECTION_REFUSED。因此没有本次刷新后打开笔记、返回来源的新增浏览器证据。
- `git add` 无法创建 `.git/index.lock`，尚未提交本批改动。此前自动审批提示额度不足、不能完成审批；没有通过其他工具绕过审批执行 Git 或 Docker。

阶段 4、6 仍未通过；阶段 5 独立浏览器恢复与阶段 7 的完整验收仍待完成，新手真实观察 A20 未取得。

## 当时待提交拆分（后续已提交）

当前 HEAD 为 `e14cd5c`。索引写入失败，本批没有新提交；以下三个边界在审批可用后按顺序分别暂存并提交，不包含仓库中其它历史未跟踪材料。

1. `fix(reading): center explanation context on selected passage`：前后端上下文工具、对应测试、PdfViewer、term_explanation_service。
2. `fix(translation): preserve partial output without automatic retries`：page_translation_service 及测试、usePageTranslation 及测试、translationState 及测试、TranslationPanel、artifactModel 及测试、package.json。
3. `test(reading): record four authorized quality checks and remaining gates`：本文、STAGE6_EXECUTION_PLAN、v3 的四例 attempt / receipt / runtime / 截图及 verify_stage4_v3.py。

## 后续验证与提交（20:12后）

- Git及运行测试所需审批恢复；早期EPERM、服务未运行和未提交描述不再代表当前状态。Java使用本机JDK25启动兼容Java21编译的包，端口8081；Vite5173、Python8000、GROBID8070已恢复。
- 上下文及部分译文分别提交 `1c1c8dc`、`0966086`；图文重排 `ad40c82`、放大与裁切 `8b1eff4`、缓存配对 `5e3ea8a`、缓存读取守卫 `f07a3ed`。
- 原图组件4项、翻译Hook9项、统一界面26项测试通过；Node展示/布局测试、类型检查、生产构建通过。较早另外一组13项组件测试和25项统一界面测试也曾通过，以上数字不相加为新的唯一测试总数。
- 只读现有模型缓存和引用索引，19处摘录中的1处是省略号拼接；其余18处在完整索引正文中匹配。不用截断解释这处完整正文也不存在的摘录。连续摘录提示提交 `658ebee`，比较与研究19项测试通过。未放宽校验，未追加模型生成。
- 实际任务刷新后，原文笔记可重新打开，来源可跳回第4页。已有译文仍可显示，但旧段落配对与内容错误未全部通过；独立QA页使用归档原始真实模型结果，仅验证新展示。
- 四个案例原始结果保持，修复后没有新的Provider内容验收。阶段4、5、6、7仍未整体通过；A20无真实新手观察。
