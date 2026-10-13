# PDF列归属、量化条件与索引版本核验

2026-10-09。此批为无Provider生成的输入和校验核验，不能代替真实回答内容验收。

## 实现与验证

- `285e96c`用现有PyPDF2绘制操作及字体宽度定位PDF词元，逐格交叉核对TEI简单分组表。LightGaussian主表两数据集组、8个完整方法行通过；合并/损坏行、旋转页和不支持字体保持未核对，不猜列。
- `9c5c9f2`为比较数字要求核对行、指标、数据集、硬件和基线版本。同条结论必须注明条件；计算与作者报告分开，正文报告仍可使用连续证据。结构字段保留内部，用户界面不展示验证过程。
- `309300e`为新索引生成内容版本，保留已保存旧sourceId；`c9d82f5`修复80字符截断造成版本来源碰撞，并在调用模型前拒绝重复ID。失败输入留在`stage4-table-columns-v7-version-before.json`。
- `0344009`把已核对列与完整行带入批判实验轴，在原1800字符预算内保留，结构标签不冒充原文。
- 相关Python回归137项及3个子测试通过，见`stage4-table-columns-v7-tests.log`。

真实PDF位置诊断及主表原图：`stage4-table-layout-v7.json`、`stage4-table-layout-v7-page6.png`、`stage4-table-columns-v7-probe.json`。临时真实e5+BM25索引及固定JSON响应经过实际比较校验路径：正确量化条目通过，错误数据集/基线/计算倍数拒绝，见`stage4-table-columns-v7-runtime.json`。响应由测试控制，不能称为模型质量通过。

## 当前服务索引

先核对权威生成存储空闲，再仅刷新同一公开LightGaussian验证材料：37→55片段，其中18个表格片段；版本`2977684d0da4a8b6`，全库644→662。其他论文的ID、正文、元数据及向量整体哈希前后相同。原索引备份保存到`tmp/reindex-backups/stage4-light-index-v7-backup.json`，SHA-256核验通过，不提交大向量文件。

任务与已保存来源快照前后逐字相同，revision9；未改历史收据、成果、缓存或旧项目。记录见`stage4-light-index-v7-runtime.json`、`stage4-light-index-v7-recovery.json`及task-before/after。当前服务重启后，实际持久索引四轴及最终比较输入通过，实验提示含PDF核对列，Provider边界拦截，见`stage4-table-columns-v7-live-input.json`。

复杂表与语义对应仍有有限支持边界。A11/A14/A18/A20及默认入口不因这些离线和输入核验变成通过。第五轮真实案例另行归档。
