# v22唯一批判案例及表号误判修复

2026-10-10。用户明确回复“允许这 1 个批判案例”后，LightGaussian固定问题仅提交一次至https://api.deepseek.com，模型deepseek-v4-pro，实际执行源码6164a45。累计固定案例37，本次额度用完；不自动重发。

## 实际执行与保存

原服务均停止。原Java文件数据库离线备份后恢复Java/Vite；Docker Desktop临时通信端点异常，备份改名三个明确的临时文件后恢复，未删除容器或卷。授权脚本重新核对Provider、模型、三个源码哈希、索引就绪和原9任务/8收据完整保持。

实际收据succeeded/partial=true，8个判断发布7个。原响应、执行收据、任务、逐判断引用和实际浏览器截图分别保存为stage4-analysis-v22-cached-response.json、stage4-critique-v22-receipt.json、stage4-critique-v22-task.json、stage4-analysis-v22-diagnosis.json和stage4-critique-v22-browser.png/json。缓存归档按真实授权时间窗口筛选唯一结构响应，原生用户/系统提示及cache key精确匹配。原9任务/8收据保持见stage4-analysis-v22-preservation-after.json。

已发布计算：Mip-NeRF360/Tank and Temple相对同A6000重训基线压缩17.38/17.32倍、帧率倍数1.65/3.37、PSNR下降0.27/0.22dB、LPIPS上升0.020/0.024；未外推所有场景。剪枝训练视图依赖、SH训练位姿邻域蒸馏、选择性VQ的外观相似假设均有独立事实/推断引用。实际成果和来源默认折叠展示保留，不冒充用户本人或独立浏览器观察。

## 明确失败原因与离线修复

拒绝的是首条实验事实：FPS237/357和存储45/25MB均有完整factId绑定，但正文“表1”被FREE_NUMBER当成未绑定测量数字。采用有限例外：仅当前判断引用了有_verifiedTable的表格，且其元数据标题明确为Table 1时，允许中文/英文同编号表号；未引用、未核对、不同编号、百分数和小数均不例外。不修改实验选项、条件或数字绑定。

五文件182项相关pytest通过（test_grounded_numeric_rendering、test_grounded_critique、test_experiment_facts、test_comparison_measurements、test_conversation_capabilities），其中8项新回归覆盖有效表号与拒绝边界。原样缓存响应在精确提示匹配、Provider禁止和任务写入0条件下回放：8项均通过，partial=false。见stage4-analysis-v22-table-label-replay.json和stage4-analysis-v22-table-label-diagnosis.json。原始响应字符串未改、未人工补填绑定；原实际收据和保存成果仍partial=true。第一次离线诊断在归档进程尚未结束时读取了不完整文件，随后等进程结束再只读重做；没有重新调用模型。

## 尚缺范围

离线partial=false不等于修复后真实案例已通过。内容抽查仍发现剪枝事实用了“最大体积归一化”，原引用明确有90%排序体积参考，概括精度不足；修复后离线摘要只保留首段绝对值，没有呈现质量代价。阶段4不据结构通过计作完整验收；默认入口补丁仍未应用。后续先改善摘要及参数语义表达，不自动追加Provider。独立Edge恢复和完整新手流程已按用户要求免验。

## 修复加载

真实证据单独提交b19b408；有限表号修复及原样回放单独提交6ad9115。确认无活动对话/研究生成后短暂重启ai_service_python。2026-10-10重启后health正常，新数值模块SHA256与本地一致，10任务/9收据与重启前相同，包括实际v22部分结果；Provider/任务写入0。前后独立记录stage4-table-label-v22-reload-before/after.json。未应用默认入口补丁，未将原成果替换为离线结果。
