# 行内原式与运算符分行修复

日期：2026-10-09。代码分别提交`d812c43`（抽取、区域与协议）、`22c731a`（标记点击）。阶段6及A14未整体验收。本批所有生成回复均为明确标注的离线夹具，没有新增Provider请求、任务或索引写入。

## 已修复范围

真实PDF.js抽取中，大型运算符的字体原点高于实际文字基线；乘积符号被读为Q并排进上一行`subtractQ`。当前使用PDF.js公开字体ascent/descent及邻近数学锚点调整分行，源像素坐标仍来自原始字体位置。没有把所有Q替换为乘积，也没有自行重建分数、上下标或运算式。

能够识别的行内等式、集合关系与维度表达式改用整页唯一原式标记，记录对应文本范围和PDF区域。模型只收到标记及正文，不收到损坏的数学字符串；后端验证每个标记一次且顺序一致，新增保护不会与已定位编号冲突。缓存保留区域和版本2；旧版本继续按原有整段原图显示，不能把旧的每段重复编号套到新坐标。

全景译文中的版本2标记可点击查看相应区域，正文来源默认折叠。实际T乘积、体积分数均完整显示。区域按文本项边界定位，可能带邻近文字；不声称已精确定位到每个字形，也不承诺任意PDF数学语法都能识别。保存成果和独立HTML仍保留整页原图，这一批没有新增成果中的逐式点击或多页导出。

## 验证

- Python阅读工具相关24项回归通过，`stage6-inline-v7-backend-tests.log`。
- 最终完整前端47个文件281项Vitest和19组Node脚本通过，`stage6-inline-v7-full-verified.log`。类型检查及当前生产构建通过，`stage6-inline-v7-typecheck-final.log`、`stage6-inline-v7-build-final.log`。生产构建仍有原有大包提示，不计作失败。
- LightGaussian真实第4页抽取7项检查通过：运算符不黏入上一行、损坏乘积不进入翻译正文、后续正文保留、原式区域有界、8个标记整页唯一、全部标记进入请求、缓存往返保持。`stage6-inline-v7-runtime.json/log`。首次探测用JSON字符串比较不同键顺序误报缓存失败；保存`runtime-before`记录，改为对象深度比较后通过，没有放松坐标或标记条件。
- 同一实际输入进入原生翻译函数，4个初始批次使用受控响应，5项协议检查通过：8个标记各一次、无黏连Q、5段无缺失、版本2、终态success。见`stage6-inline-v7-service-probe.log`。这不是模型译文质量证明。
- 原始3DGS真实第4页抽取及段落重排检查通过，`stage6-inline-v7-original3dgs-layout.json/log`，避免只凭单篇公式样例宣称通用通过。
- IAB只读核验页实际打开原式8、关闭后打开原式7，截图`stage6-inline-v7-product-browser.jpg`、`stage6-inline-v7-volume-browser.jpg`。前者确认透射率乘积上下限，后者确认4/3分数；页面明确标注占位正文而非模型译文。实际页面使用同一生产全景组件，读取现有任务的权威PDF，未保存成果或更新旧记录。
- 活动对话/研究生成任务各0后重启AI容器；`/health`为200/ok，GROBID及RAG正常，Provider目的地址仍为`https://api.deepseek.com`。见`stage6-inline-v7-idle.log`、`stage6-inline-v7-service.json`。

## 验证期间的失败与环境恢复

首轮前端测试被Windows沙盒文件解析限制阻止，改走审批路径。新增测试最初未被`.test.ts`配置收集，改为仓库已支持的JSX测试；早期模拟场景误用独立公式而非混合正文，修正为真实行内场景。另修复缓存坐标规范化的浮点尾差；所有失败日志保留，不计作通过。

捆绑pnpm执行test前自动安装，移动npm依赖并生成额外锁文件，安装最终被ignored-builds终止；同时测试因依赖暂缺未启动。按原`package-lock.json`恢复时发现项目Vite的esbuild锁文件；确认5173监听进程和项目内子进程后暂时停止它们，使用`npm ci --ignore-scripts`恢复原锁定依赖，再隐藏窗口恢复Vite。意外生成的pnpm锁文件已删除，仓库`package.json`与`package-lock.json`没有差异。使用原npm脚本完成最终测试及构建。失败及恢复日志分别保留`stage6-inline-v7-full-tests.log`、`stage6-inline-v7-dependency-restore.log`、`stage6-inline-v7-dependency-restored.log`。

## 剩余门槛

去掉黏入正文的Q不保证模型正确翻译原作者措辞；真实翻译、划词解释和批判/组合输出须再核对。A11/A14尚未通过真实内容，A18独立Edge仍连接失败，A20真实新手尚未参与；默认入口切换仍等待完整门槛。此前18例授权已用完，下一批固定真实案例须按新的具体授权执行，不能把本批合成响应改写为真实成功收据。
