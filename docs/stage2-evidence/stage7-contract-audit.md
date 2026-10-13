# 当前契约复核

日期：2026-10-08。结论：本次检查通过，整体重构仍未验收完成。

## 完整Schema与当前服务

执行`verify_stage7_shared_schema.py`，读取当前Java服务四个固定任务、成功与失败收据以及成功收据内嵌任务，共7个响应。使用现有本地Python容器中的jsonschema 4.26.0检查完整共享Schema，包含引用和条件约束，全部通过。

在内存中构造5个错误样例：缺少任务版本、负版本、重复材料、成功收据缺少结果、未知运行状态，全部被拒绝。检查前后四个任务逐字段一致。仅GET读取，没有模型调用或任务写入；原始响应未归档。Schema哈希与结果见`stage7-shared-schema-runtime.json`。

此前`stage7-read-contract-runtime.json`提供材料与收据归属、任务外访问404及重复读回证据。这些语义规则与此次结构校验范围不同，不能互相替代。

## 当前Java接口规则

使用JDK 25.0.1运行现有五组接口测试；编译目标仍为Java 21。上游使用模拟服务，数据库显式指定`jdbc:h2:mem:stage7_contract`，没有使用当前运行服务的数据目录。38项通过，失败、错误、跳过均为0：任务4项、运行15项、学习6项、研究9项、材料4项。摘要由本轮Surefire报告提取，见`stage7-java-contract-runtime.json`。

复现命令（在`backend-java`目录，先将JAVA_HOME与PATH指向相应JDK）：

```powershell
mvn test '-Dtest=TaskWorkspaceControllerTest,TaskOperationControllerTest,TaskLearningControllerTest,TaskResearchControllerTest,TaskMaterialControllerTest' '-Dspring.datasource.url=jdbc:h2:mem:stage7_contract;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE' '-Dlombok.version=1.18.42' '-DargLine=-Dnet.bytebuddy.experimental=true'
```

这些测试验证接口与写入规则，不证明真实模型内容质量、新手体验或独立浏览器恢复。没有为此次检查重复生成模型结果。

## 尚未满足的完成门槛

- A11/A14：既有10例真实模型授权已用完；修复后的内容复测请求仍待用户明确授权。
- A18：本轮浏览器工具清单仍报告Edge连接失败，没有获得可操作的独立浏览器。
- A20：真实新手观察未执行，需要真实参与者；代理操作不作为替代。

这些外部条件已连续多轮未改变。当前证据归档后不能继续以重复测试或文档增加宣称进展；统一界面仍保留预览入口，阶段4–7未整体完成。
