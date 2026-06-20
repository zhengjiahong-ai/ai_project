# Layout Parser Benchmark Spike

## 结论

本轮结论为 **keep GROBID**：继续使用 GROBID 0.7.2 与现有 PDF.js layout 工具，不替换生产解析链路。Infinity-Parser 只在官方代码、模型、许可证和可复现安装入口均可核验后进入 **run isolated pilot**；当前不满足条件，不进入 **integrate adapter**。

原因如下：

- GROBID 在两篇标准英文学术论文上能恢复主要章节，但章节 F1 仅为 `0.600` 和 `0.467`；三篇中文资料的章节 F1 均为 `0`。
- Active RIS 标注页的公式/图区域检测 precision 为 `0.333`、recall 为 `0.500`、F1 为 `0.400`，仍有明显误检和漏检。
- PDF.js layout 在已匹配 anchor 上保持了正确顺序，但 25 个 gold anchor 中有 5 个未匹配；两篇含表格的单栏中文资料被误判为双栏。
- Active RIS 仍有 2 个公式模式残留在翻译请求文本中，不能证明当前过滤已可靠覆盖复杂公式。
- [Infinity Parser 论文](https://arxiv.org/abs/2506.03197) 将 `layoutRL` 描述为训练框架，将 Infinity-Parser 描述为相应 VLM 解析器；截至本次 spike，未发现可验证的官方代码、模型和许可证组合，因此状态记录为 `not_runnable`，未用其他解析器替代。

## 样本与标注

固定样本定义位于 `ai-service-python/benchmarks/layout_parser/fixtures.json`。每个条目包含相对路径、SHA-256、版式标签、章节 gold、阅读顺序 anchor 以及代表页上的公式/表格/图片区域。区域坐标来自 PDF 页面渲染后的人工检查，统一使用 `[0, 1]` 归一化坐标。

| 样本 | 主要版式 | 代表页 |
| --- | --- | ---: |
| Active RIS | IEEE 双栏、密集公式、图片 | 2 |
| Semantic Alignment Code Translation | ACM 双栏、算法与表格 | 2 |
| 论文阅读助手升级技术详解 | 中文单栏、跨页表格、混合英文 | 2 |
| 论文阅读助手自主性研究 | 中文单栏、多表格、混合英文 | 2 |
| DeepResearch 项目论文 | 中文表单、长段落 | 2 |

除仓库已有的 Active RIS 外，其余本地 PDF 不新增副本；manifest 通过路径与 SHA-256 检查样本身份。样本缺失或校验和不一致时，runner 输出 `missing` 或 `checksum_mismatch`，不会计算伪分数。

## 指标

- 章节：去除编号、统一大小写与标点后做精确匹配，报告 precision、recall、F1。
- 阅读顺序：在人工 anchor 的共有子集上计算 pairwise order accuracy，同时单独报告未匹配 anchor，避免高 accuracy 掩盖文本缺失。
- 公式/表格/图片区域：仅在人工标注页评分；类型、页码相同且 IoU `>= 0.5` 才算匹配。
- 过滤失败：报告正文误过滤、公式残留、阅读顺序 inversion 和双栏串行错误计数。
- 耗时：记录单文档 GROBID 后处理耗时和 PDF.js 标注页处理耗时，仅用于本机对比，不作为跨机器性能结论。

## 结果

运行环境：Windows 11、Python 3.13.9、Node.js 24、GROBID 0.7.2、pdfjs-dist 3.4.120。完整原始数据见 `grobid-results.json` 和 `layout-results.json`。

### GROBID

| 样本 | 状态 | 章节数 | 章节 F1 | 标注页区域 P/R/F1 | 全文区域数 |
| --- | --- | ---: | ---: | --- | ---: |
| Active RIS | success | 12 | 0.600 | 0.333 / 0.500 / 0.400 | 63 |
| Semantic Code Translation | success | 22 | 0.467 | 0 / N/A / 0（1 个误检） | 20 |
| 升级技术详解 | success | 0 | 0 | N/A / 0 / 0（漏检 1） | 1 |
| 自主性研究 | success | 1 | 0 | N/A / 0 / 0（漏检 2） | 2 |
| DeepResearch 项目论文 | success | 0 | 0 | N/A（无区域 gold） | 0 |

可核查失败点：

- Active RIS 的图和公式共 8 个 gold 区域，仅匹配 4 个，同时产生 8 个 false positive。
- Semantic 代表页没有区域 gold，但 GROBID 产生 1 个区域，属于误检。
- 两篇中文表格资料的代表页分别漏检 1 个和 2 个表格区域。
- 中文资料的大标题多为视觉字号/加粗层级，GROBID TEI 几乎没有形成可用章节树。

### PDF.js layout 与翻译过滤

| 样本 | 列模式 | anchor 匹配 | 顺序准确率 | 正文误过滤 | 公式残留 |
| --- | --- | ---: | ---: | ---: | ---: |
| Active RIS | two-column | 4/5 | 1.000 | 0 | 2 |
| Semantic Code Translation | two-column | 5/5 | 1.000 | 0 | 0 |
| 升级技术详解 | two-column | 4/5 | 1.000 | 0 | 0 |
| 自主性研究 | two-column | 2/4 | 1.000 | 0 | 0 |
| DeepResearch 项目论文 | single-column | 5/6 | 1.000 | 0 | 0 |

顺序准确率只覆盖已匹配 anchor；因此 Active RIS、中文资料的 `1.000` 不能解释为完整文本没有丢失。升级技术详解和自主性研究的视觉版式均为单栏，但表格中的分散文本块触发了 `two-column`，这是明确的列检测失败。

## 复现

先启动项目固定版本的 GROBID：

```powershell
docker compose up -d grobid
```

运行 GROBID benchmark：

```powershell
cd ai-service-python
$env:GROBID_SERVER_URL='http://localhost:8070'
python -m benchmarks.layout_parser.runner --manifest benchmarks/layout_parser/fixtures.json --output benchmarks/layout_parser/grobid-results.json
```

运行 PDF.js layout benchmark：

```powershell
cd frontend
npm.cmd run benchmark:layout
```

运行专项测试：

```powershell
cd ai-service-python
python -m pytest tests/test_layout_parser_benchmark.py -q

cd ../frontend
npm.cmd run test:layout-benchmark
```

若 GROBID 不可访问，Python runner 对每篇文档记录 `grobid_unavailable` 且 `metrics=null`。Infinity-Parser 当前固定记录为 `not_runnable`，不生成候选分数。

## 后续门槛

- **keep GROBID**：当前默认；现有接口和解析流程不变。
- **run isolated pilot**：仅当 Infinity-Parser 存在官方可下载代码、模型、明确许可证和固定版本，且能在隔离环境输出结构化文本、阅读顺序与区域坐标时触发。
- **integrate adapter**：isolated pilot 在同一 fixture 上章节 F1、区域 F1 和 anchor 覆盖率均明显优于当前基线，且延迟、显存、许可证与安全范围可接受后，另立任务设计 adapter；本次不满足。
