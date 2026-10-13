# 阶段5迁移批次实测范围（2026-10-08）

> 历史记录：用户随后明确不需要旧研究项目导入功能。其入口、接口、转换服务和专用测试已移除，本记录不代表当前可用功能或当前验收要求。既有数据与备份保留；当前阶段5范围见 `../STAGE5_EXECUTION_PLAN.md`。

状态：本批局部通过，阶段5整体未通过。没有新增Provider生成；同一导入重放为数据库操作。

## 旧研究资料范围

安全只读列表发现6个项目；本批实际浏览器导入1个，不将列表读取算作全部迁移。

| 原项目ID | 标题 | 本批状态 |
|---|---|---|
| a1109643-1e63-43fa-b881-74c8ea881604 | 3dgs | 列表读取，未导入 |
| b1a9758b-d2d7-4fd5-999c-2427e8ad9585 | 演示：LightGaussian 压缩方法 | 浏览器导入并核对 |
| 324d50ec-764f-4473-85cd-d8063b38cabf | 样例：3DGStream 与动态 3DGS 综合研究 | 列表读取，未导入 |
| 7dc6aa86-9f23-4a8f-99df-e7fd014f4cf0 | 两篇论文综合研究演示 | 列表读取，未导入 |
| 87708392-a207-46a5-b95f-f99c1ad5dbdc | 动态3dgs | 列表读取，未导入 |
| c278347a-135b-4e17-8ef3-4cfbc20caae3 | 动态3DGS | 列表读取，未导入 |

## 实际核对

导入目标 `legacy-agent:a2a04a3d-b30f-39d6-9630-9d74a003d110`。原始快照包含1次运行、1份报告、1份计划审核、1份最终审核、11条时间线，无研究任务/消息/辩论。原报告正文与3条来源保留，报告是历史结果，未重新生成，也不代表报告内容质量通过。

浏览器实际下载 `演示：LightGaussian 压缩方法-旧项目备份.json`；下载文件与服务端legacyArchive及持久化备份相等。验证副本 `stage5-agent-backup-verified.json`，截图 `stage5-agent-import-browser.jpg`。初次UI导入后任务采用回调存在错误，已修复为workspace.adoptServerTask；重放导入返回already_imported并成功打开原任务，无重复导入。

Java重启后运行 `verify_stage5_migration.py`：正文、来源、档案及下载一致；同快照重放返回当前任务且无写入。收据 `stage5-agent-migration-runtime.json`。`verify_stage5_identity.py` 核对服务端无ID文档修复、完整原始备份和重复调用不变，收据 `stage5-identity-runtime.json`。

旧论文编号 `2311.17245v6.pdf` 的服务端PDF缺失。迁移预览提示缺文件，新导入不会自动聚焦该文件；已导入任务的编辑状态保留。未把另一个SHA256编号的已上传同名论文自动关联为该旧材料。

## 相关自动验证与剩余边界

Java：TaskDocumentIdentityControllerTest 3项、TaskAgentMigrationControllerTest 3项、TaskDocumentTransferControllerTest 7项，本批共13项。前端：旧项目转换、导入UI、远端存储、统一界面4文件31项。Python只读导出2项。类型检查与生产构建通过。移动测试包括目标更新阶段异常整体回滚和同请求并发只写一次。

Java测试最初被自动审批拦下，理由是清表代码可能影响文件数据库；核对测试配置并在命令显式指定独立内存数据库后通过，真实任务库未清理。

用户后续收缩范围：无需全量迁移旧项目和文档。仍待充分验证代表性缺文件失败提示、变化快照的备份恢复体验、独立客户端实际恢复、完整版本恢复/失败交互及A15–A18；无需导入其余5个项目或恢复所有历史PDF。本批结果不能替代剩余验收。
