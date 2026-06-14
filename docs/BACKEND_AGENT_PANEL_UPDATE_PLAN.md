# 后端 Agent 面板更新计划书

## 1. 现状结论

当前 Java 后端的定位非常明确：它是浏览器唯一后端入口，负责 `/api` 统一暴露、上传转发、聊天历史持久化、研究任务转发与错误适配。

从源码看：

- `backend-java/src/main/java/com/ai/assistant/backend_java/controller/AcademicController.java`
  - 当前没有任何 Agent 项目或 Agent 任务专属路由。
- `backend-java/src/main/java/com/ai/assistant/backend_java/service/AiService.java`
  - 当前只封装了已有单论文能力和深度研究任务转发。
- H2 中当前持久化对象仍然只有：
  - `Paper`
  - `ChatMessage`

因此后端目前不具备承载 Agent 面板的“项目管理层”和“会话聚合层”。

## 2. 后端应该新增什么

### 2.1 新增 Agent 项目 API 网关

Java 层应该新增一组稳定的 `/api/agent-projects` 路由，负责给前端提供统一入口，而不是让前端直接拼 Python 内部任务接口。

建议新增：

- `POST /api/agent-projects`
- `GET /api/agent-projects`
- `GET /api/agent-projects/{projectId}`
- `PATCH /api/agent-projects/{projectId}`
- `POST /api/agent-projects/{projectId}/papers`
- `DELETE /api/agent-projects/{projectId}/papers/{pdfId}`

职责：

- 校验参数
- 归一化响应
- 将前端的项目操作转发到 Python
- 在需要时补充 Java 侧会话信息

### 2.2 新增 Agent 任务 API 网关

建议新增：

- `POST /api/agent-projects/{projectId}/tasks`
- `GET /api/agent-projects/{projectId}/tasks/latest`
- `GET /api/agent-tasks/{taskId}`
- `POST /api/agent-tasks/{taskId}/cancel`
- `GET /api/agent-traces/{traceId}`

职责：

- 将 Agent 任务和现有 `research-tasks` 区分开
- 保持接口语义清晰：
  - `research-tasks` 仍偏单论文深度研究
  - `agent-tasks` 偏多论文研究编排

### 2.3 Java 侧持久化建议

Java 不需要承接复杂 AI 编排，但建议增加最小项目级元数据持久化，便于前端恢复和网关聚合。

建议新增实体：

- `AgentProject`
  - `id`
  - `title`
  - `goal`
  - `status`
  - `createdAt`
  - `updatedAt`
- `AgentProjectPaper`
  - `projectId`
  - `pdfId`
  - `sortOrder`
  - `addedAt`
- `AgentTaskRef`
  - `taskId`
  - `projectId`
  - `traceId`
  - `status`
  - `lastStage`
  - `updatedAt`

为什么建议 Java 也存一层：

- 便于前端快速列出项目
- 便于做“最近项目 / 最近任务”恢复
- 便于未来接入权限或多用户时作为网关侧控制点

### 2.4 响应归一化

Agent 面板后续会返回更复杂的数据结构，Java 层需要承担“对前端稳定”的职责。

建议在 `AiService.java` 中新增归一化方法：

- `normalizeAgentProjectBody`
- `normalizeAgentTaskBody`
- `normalizeAgentTraceBody`

统一保证：

- 有 `status`
- 有稳定 `project / task / trace` 顶层字段
- 透传错误码但不丢失 message
- 对 Python 返回的字段缺失做兼容兜底

### 2.5 兼容与隔离策略

需要明确三类接口边界：

- 现有阅读接口：
  - 不改语义
- 现有深度研究接口：
  - 继续服务单论文长任务
- 新 Agent 接口：
  - 新增，不污染旧接口结构

后端要避免的做法：

- 不要把 Agent 任务硬塞进现有 `/api/chat`
- 不要让一个接口同时承担“普通问答”和“跨论文编排”
- 不要在 Java 里复制 Python 的编排逻辑

## 3. 后端分阶段计划

### Phase 1：先补网关 API 和项目元数据

目标：让前端可以拿到真实项目对象，不再依赖本地 mock。

任务：

- 增加 `AgentProject` 相关实体和 repository。
- 增加 `AcademicController` 新路由。
- 增加 `AiService` 对 Agent 项目与任务的转发封装。
- 增加错误透传和响应归一化测试。

验收标准：

- 前端可创建项目、查看项目、增删项目论文
- Java 测试覆盖主要成功与失败路径

### Phase 2：补任务生命周期聚合

目标：让网关成为 Agent 任务的一致入口。

任务：

- 增加 Agent task 创建、查询、取消、latest 查询接口。
- 将 Java H2 中的 `AgentTaskRef` 与 Python 任务快照关联。
- 为前端提供 `projectId -> latestTask` 的稳定查询能力。

验收标准：

- 前端刷新后可以稳定恢复最近任务
- taskId 和 projectId 关系可追溯

### Phase 3：补协作和可观测能力

目标：让 Java 成为稳定的外部契约层。

任务：

- 增加 `agent-traces` 只读接口转发。
- 支持项目级任务列表查询。
- 补充分页、排序、状态过滤参数。
- 规范错误码体系。

验收标准：

- 前端无需理解 Python 内部结构即可消费 Agent 相关能力
- 旧阅读功能不受影响

## 4. 建议新增测试

- Controller 测试：
  - Agent 项目创建、查询、加论文、删论文、创建任务、取消任务
- Service 测试：
  - 转发成功
  - Python 400/404/409 透传
  - 空响应兜底
- Repository 测试：
  - 项目和论文关联查询

## 5. 推荐交付顺序

1. 先加 Java 新路由和转发能力。
2. 再加 H2 项目元数据表。
3. 再补 latest task / trace / task list 聚合。
4. 最后再考虑分页、筛选和未来多用户隔离。
