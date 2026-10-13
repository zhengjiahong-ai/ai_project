# 当前表格白名单范围核验

2026-10-09。无新增模型生成，累计28个授权固定案例已使用完。

发现此前台账把“主表列归属未核对”作为整体限制不够准确。主表已有按原PDF绘制位置逐格核对的完整行；当前模型资料同时保留原始合并表头的tableColumnMappingUnverified=true，比较提示又把该标记表述为列映射整体未核对。v9模型因此在限制中声称主表不能逐列核对。现明确：verifiedTable为行白名单，原始不确定标记不否定白名单，只禁止猜测其他行和合并格。比较与批判共用该提示，未更改原始标记或任何数字校验。

实际原PDF SHA256与LightGaussian文件身份一致。重跑原PDF＋既有TEI核验，主表两组数据集、8个完整行一致；实际持久检索后的最终比较输入保留白名单9、10行（带星号基线和Ours），与新核对PDF逐格一致。A6000来自同论文实际正文。

实际输入上的6个受控计算均通过：Mip-NeRF360为237 FPS、存储比17.38、SSIM下降0.007；Tank and Temple为357 FPS、存储比17.32、SSIM下降0.013。这里的“计算通过”只证明现有校验路径，不是模型回答。另有未列入当前白名单的行、错误数据集、错误硬件、去星号基线4类反例均拒绝。索引前后文档及元数据哈希均4708c07a18e305c6aed2bdb183e439ba2de02fcd5ccfa8dc867b44afbf1bf3f9，Provider/任务写入/索引写入均0。

证据：stage4-table-scope-v11-native.log、stage4-table-scope-v11-runtime.json；脚本ai-service-python/scripts/verify_table_scope_v11.py；126项回归见stage4-table-scope-v11-tests.log。初次回归仅新测试异常文案预期错误，修正断言后通过，未放宽实现。

独立Edge本轮通过Windows工具识别到运行窗口，但获取浏览器状态时工具停止：无法足够可靠地确定当前URL以执行策略。停止后没有继续UI输入，没有绕过保护；没有打开本地应用、读取成果或完成独立恢复。A18仍未通过。用户随后选择本人参与体验，A20尚未实际执行，不以选择参与等同体验完成。

旧真实批判仍partial，缺占位符的实验结论仍被拒绝。新提示是否被真实模型遵守，以及完整语义质量，尚待实际核对。阶段4–7及默认入口仍未完成。

修复提交5867020，持久生成存储检查空闲后已重启加载。health/GROBID/RAG均ok，新版入口HTTP200；原阅读任务与重启前快照逐字段相同，revision19保持。证据stage4-table-scope-v11-reload.log、stage4-table-scope-v11-before-reload.json与stage4-table-scope-v11-reload-runtime.json。这些是服务及读取核验，不计浏览器体验或新模型生成通过。
