# 本轮三例后的离线修正

2026-10-09。真实三例已各提交一次，累计28例；本批次未追加模型调用。

修正只作用于已核验数值短语的呈现：中性“SSIM变化为”由原文给出方向，不重复指标；紧邻相同数据集含空格时不再重复括号；完整“over 200 FPS on complex scenes”保留严格超过及复杂场景限定。不同指标、相反方向、不一致上下界仍拒绝；未知短语仍原样引用。

比较范围中明确为true的未核对字段转为中文，并去除句号接分号。提示要求模型使用读者语言。数字合同提示明确本条占位符与绑定一一对应，定性结论不能附闲置实验绑定；严格校验未放宽，也不修补模型原始响应。

相关5文件95项回归通过，见stage4-reading-v10-tests.log。原始v9批判/比较JSON在原生当前RAG检索中重放，Provider边界拦截，批判仍partial=true，比较仍partial=false。新比较句为“LightGaussian 报告在 Mip-NeRF 360 上 SSIM仅下降0.007，表示规模从782MB到45MB；复杂场景渲染速度为超过200 FPS。”并保留作者报告、未作同条件比较的标记。范围保留主表列归属尚未核对这一限制。

原始响应未改动，索引前后SHA256均4708c07a18e305c6aed2bdb183e439ba2de02fcd5ccfa8dc867b44afbf1bf3f9；Provider、任务写入和索引写入均0，见stage4-reading-v10-native.log。重放脚本verify_cached_reading_v10.py不发布任务或覆盖旧收据。

剩余问题：批判的首项仍缺数值占位符；主表实验条件及列归属仍未完整核对。比较中“剪枝步骤会避免……细节损失”还需语义验收，不能以引用存在等同完整支持。此次修正不证明未来模型必定遵守提示，也不把原真实结果记为已修复后通过。A11/A14/A18/A20及正式切换门槛保持未完成。

修复提交8f164ff。两项持久任务存储确认无活动生成后，仅重启现有AI服务加载；health、GROBID、RAG均ok，原阅读任务重启前后逐字段一致、revision19保持。见stage4-reading-v10-reload.log、stage4-reading-v10-before-reload.json及stage4-reading-v10-reload-runtime.json。健康检查和任务GET为只读，没有新模型请求。
