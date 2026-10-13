# Deep Research 单实例备份、恢复与回退

适用：当前 Java/H2 + Python/SQLite + Chroma 单实例部署。2026-10-13 已在本机完成配套恢复演练；不是多实例、生产高可用或在线热备方案。质量发布门槛仍以实施记录和固定案例为准。

## 备份边界

必须一起保存：

| 内容 | 本机开发位置 | 作用 |
| --- | --- | --- |
| Java 数据库 | `backend-java/target/stage0-data/academic_db.mv.db` | 任务、消息、笔记、成果、研究投影、论文原文件和解析结果 |
| Python 业务数据 | `ai-service-python/data` | 原研究、任务操作等已有业务记录 |
| 新版研究库和 checkpoint | Linux 卷 `academic_dr_runtime_20261012` 中 `/research_data/store` | 执行状态、证据、调用账本、检查点、外部全文 |
| Chroma 索引 | `tmp/dr-container-validation/chroma` | 当前论文向量索引 |
| Java 包、Python 镜像和源码版本 | 本次部署实际使用版本 | 与数据契约一致的程序 |
| 配置清单 | 目录、端口、Provider、功能开关 | 恢复实际挂载和路由；密钥通过原有安全配置注入 |

这些是本机实测位置，不是固定生产路径。先检查实际 Java 启动参数、容器挂载和环境中的目录项。不要把旧 `tmp/dr-live-data` 当作当前运行库。不要把密钥写入备份日志或提交仓库。

## 一致备份

1. 从权威研究库检查 `queued/running/stopping`，等待结束或通过正常操作暂停；不要将未知调用重新发出。
2. 保存代表性任务、成果和论文文件的内容指纹。关闭 Java 入口并停止 Python 服务，防止备份期间新写入。
3. 在停服后复制 H2、Python 业务目录和 Chroma 到一个全新备份目录。不要直接复制运行中的 H2 文件或仅复制 SQLite 主文件而丢掉 WAL。
4. 在可访问 Linux 数据卷的工具容器中运行研究备份工具：

   ```sh
   python /app/scripts/deep_research_backup.py backup \
     --database /research_data/store/research.sqlite3 \
     --sources /research_data/store/sources \
     --destination /backup/research --services-stopped
   python /app/scripts/deep_research_backup.py verify /backup/research
   ```

   `--services-stopped` 是操作人的停服确认，不负责停止服务。工具用 SQLite backup API 导出独立数据库，校验完整性及被引用全文。源连接使用只读模式，但 WAL 数据库可能需要创建共享内存文件，数据卷的只读挂载可能导致 `unable to open database file`；停服后使用正常可写挂载，由工具保持业务记录只读。
5. 对备份全部文件计算 SHA-256，最后写入部署清单；保存实际应用包及版本信息。恢复原服务并确认健康及原任务内容不变。

## 恢复到隔离副本

先恢复到新目录/新 Linux 卷，不覆盖原库。Windows 文件夹绑定中的研究 SQLite 曾复现重开 `disk I/O error`，当前已改用 Linux 命名卷；恢复继续使用 Linux 卷。

```sh
python /app/scripts/deep_research_backup.py restore \
  --backup /backup/research --destination /restore/store
```

Java 使用复制的 H2 文件和备份包，设置新端口（本次 `8083`），将 `PYTHON_URL` 指向恢复 Python（本次 `http://127.0.0.1:8003/api`）。Python 必须使用独立的数据、索引和研究挂载，并明确设置：

```text
DEEP_RESEARCH_DB_PATH=/research_data/store/research.sqlite3
DEEP_RESEARCH_SOURCE_DIR=/research_data/store/sources
CHROMA_DB_PATH=/app/chroma_data
CHROMA_DB_DIR=/app/chroma_data
DEEP_RESEARCH_V2_ENABLED=false
DEEP_RESEARCH_EXTERNAL_ENABLED=false
DEEP_RESEARCH_FULLTEXT_ENABLED=false
```

本次恢复检查将模型密钥置空，不执行新研究。嵌入模型使用已有离线缓存。不要漏掉 `CHROMA_DB_PATH`：默认目录位于源码挂载内，会因只读挂载导致索引初始化失败。Docker Desktop 的本次内部网络未发布主机端口，容器内 200 不能代替 Java 到 Python 的链路验证；改用正常开发网络并明确绑定本机端口后才通过。

预热完成后检查：

- Java 能读取既有任务、消息、笔记、成果与研究；从 Java 下载原论文并核对 SHA-256。
- 已存报告仍可读；关闭新版入口时新请求被拒绝，不能交给旧引擎继续执行。
- 对同一既有运行同步发布两次，消息和成果均不增加。
- 比较全部研究主要内容及完整调用账本指纹；验证外部全文缓存哈希和按论文身份限定的索引数量。
- 结束演练后停止隔离服务，保持原服务可用；保留备份和验证记录。

## 本次实测结果及范围

证据摘要：[`deep-research-evidence/deployment-20261013.json`](deep-research-evidence/deployment-20261013.json)。本地原始记录位于 `tmp/dr-deployment-drill-20261013`。

- 配套备份与新目录恢复通过；33 条研究主要内容、971 条完整调用账本前后指纹一致。
- 代表性 D2 任务经 Java API 核对：2 篇论文、8 条消息、16 项成果、15 条研究记录及报告指纹一致。该任务笔记为 0 条，不以此宣称非空笔记编辑路径已覆盖。
- 两篇实际 PDF 字节和哈希一致；被引用外部全文缓存哈希一致。
- 恢复索引中四篇冻结论文分别为 55、82、57、56 个片段。集合含其他旧身份，总数 363，不能把总数当四篇论文数量。
- 新版开关关闭，实际新请求返回 503；重复发布两次均 200 且没有新增消息/成果；账本没有新增调用。

此演练验证本机停服一致备份、恢复读取和关闭入口后的行为。它不替代真实研究内容质量、完整浏览器体验、生产环境发布演练或多实例故障转移。恢复检查使用的源码包含表格提取修复 `14ad3f8`，Java 代码本轮未修改。

## 固定案例执行工具

从仓库根目录运行。默认只预览清单中的冻结问题、材料身份和预算，不发HTTP请求：

```powershell
.venv-refactor/Scripts/python.exe ai-service-python/scripts/verify_deep_research_case.py H1
```

在已授权发送范围内，显式指定`--submit --attempt 1`才允许一次研究提交。同一案例和attempt已有回执时只GET查询，即使再次传入`--submit`也不会重新生成。研究POST前以独占文件写入并fsync意图；未收到确认则保持unconfirmed，后续运行拒绝重发，需要先核对服务端请求账本。不要删除不确定回执或用新attempt绕过核对。

默认回执目录为`tmp/dr-acceptance-receipts`，`CASE-vN.json`记录意图和运行身份，`CASE-vN.result.json`保存最近一次读取。不同输入不能复用同一回执；D5还需`--task-id`及`--parent-run-id`，不能创建无父运行的追问。D6/H6故障用例使用离线集成测试，不走模型提交入口。

工具不会把服务端completed标记当作质量通过，也不会把问题清单中的预期答案发送给模型。留出案例一旦用于调参，仍须按设计稿退出留出集并登记替换。
