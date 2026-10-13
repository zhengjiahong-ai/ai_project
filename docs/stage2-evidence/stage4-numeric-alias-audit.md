# 数字单位核验续验（2026-10-09）

代码提交：`2754a1f`。本批修复批判、比较共享数字校验的常见单位写法漏检，不计阶段4内容验收通过。

## 问题与改动

原匹配器仅识别部分指标和单位；有合法来源引用时，`999帧/秒`、`999帧每秒`、`999 frames per second`、`999×压缩`、`999x compression`、`999 MiB` 都可绕过数字校验。修复前新增反例测试为6失败、17通过，见 `stage4-numeric-alias-before.log`。

现在将有限的中英文帧率写法映射为FPS、倍率写法映射为倍，并识别二进制存储单位。MB与MiB仍分别核对，不假定转换；3×3、2x3矩阵尺寸不作为压缩倍率。输出和作者文字引用复用同一单位规范化，原文引用不改写。该规则只覆盖明确列出的写法，不宣称通用自然语言数字解析。

## 验证与范围

- 当前容器内运行 `tests/test_comparison_measurements.py`、`tests/test_grounded_comparison.py`、`tests/test_grounded_critique.py`、`tests/test_evidence_quotes.py`、`tests/test_pdf_table_columns.py`：73通过，2条既有依赖弃用警告。日志 `stage4-numeric-alias-tests.log`。
- `probe_numeric_aliases.py` 读取实际持久LightGaussian索引的主表chunk38及硬件chunk20，调用原生批判合成与校验，但模型返回由固定JSON代替，Provider调用被拦截。真实表内237FPS在Mip-NeRF 360、A6000、3D-GS星号基线条件齐全时，以“237帧/秒”通过；上述6个无支持数字均被拒绝。
- 5项探测检查通过，详情 `stage4-numeric-alias-runtime.json` 和 `stage4-numeric-alias-probe.log`。索引总数662；该论文持久正文和元数据前后相同，快照SHA256为 `f3cb825087a334ecb0c11a243b568b3f92bd1a0918bc414841786f1a67bab799`。未声称核对向量字节。
- Provider调用、任务写入、持久索引写入均0。最初容器名猜测错误、未运行测试，保留于 `stage4-numeric-alias-container-name.log`；随后确认并仅使用现有 `ai_service_python`。
- 只读核对活动对话操作及研究任务各0后，重启该AI容器加载修复，健康端点200且GROBID/RAG正常。见 `stage4-numeric-alias-idle.log`、`stage4-numeric-alias-service.json`。没有重启其他容器。

## 仍未完成

这是离线规则与真实输入核验，不是模型回答质量验收。既有18个真实案例授权已用完，新增四例计划等待用户明确回复，不重复提交旧案例。A11/A14仍需真实内容核对，A18需独立浏览器恢复，A20需真实新手观察；正式默认入口不切换，阶段4–7仍未完成。
