# 既有译文展示核验

这是开发用只读展示页，复用产品的 TranslationPanel 和 PanoramicTranslation，回放已授权的 LightGaussian 第4页模型结果；内容错误原样保留。页面没有模型请求，保存和重试均不可用，不加入生产应用路由。

在 `frontend` 目录运行现有开发服务器后，访问 `/qa/panoramic.html`。原图来自本地 Java 服务已有验证任务，需该服务运行于8081并保留材料。该页只验证显示，不能替代任务缓存恢复或内容质量验收。

fixture 可从本轮归档与用户已有 PDF 重建，不生成译文：

```powershell
node scripts/prepare-panoramic-preview.mjs 'D:\3DGS\paper\LightGaussian\2311.17245v6.pdf' '../docs/stage2-evidence/stage4-reading-v3-cached-responses.json' 'qa/translation-v3.json'
```

核验范围：图表和独立公式保留、中文正文16px重排、320/390px宽度、原图放大、滚动、关闭和Esc返回。截图和限制详见 `docs/stage2-evidence/stage6-panoramic-reflow-audit.md`。

“无定位正文”仅移除展示fixture的段落坐标，回放相同已归档全文译文，验证正文优先与整页原图折叠。不会修改产品缓存或修复旧内容；保存和重试仍不可用。

`/qa/reader.html` 使用产品PdfViewer检查损坏文件与无文字页。两份PDF由测试页面在内存中建立，不上传、不保存、不调用模型；只验证加载与文字工具提示，不能充当真实扫描论文或上传链路的完整验收。

`/qa/inline-math.html` 使用生产PanoramicTranslation和真实LightGaussian第4页，正文明确为定位占位文本。它验证版本2标记打开原式区域、关闭和再次打开，不生成译文或写任务，不能作为内容质量证据。区域按文本项边界定位，可能含邻近文字。可离线重建夹具并执行7项抽取/缓存检查：

```powershell
node scripts/verify-inline-math.mjs 'D:\3DGS\paper\LightGaussian\2311.17245v6.pdf' '../docs/stage2-evidence/stage6-inline-v7-runtime.json' 'qa/inline-math-v7.json'
```

`scripts/inspect-inline-math.mjs`仅用于字体问题诊断，私有字体对象访问不在生产代码中；实际抽取使用公开textContent.styles。证据及范围见`docs/stage2-evidence/stage6-inline-v7-audit.md`。
