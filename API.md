# API

## 说明

浏览器只应直接访问 Java 网关：

```text
http://localhost:8081/api
```

Java 再将请求转发到 Python：

```text
http://ai-service:8000/api
```

本文档分为两部分：

1. 浏览器可直接使用的 Java API
2. Java 转发到 Python 的内部对应关系

## 通用响应约定

大多数接口返回：

- 成功：`{ "status": "success", ... }`
- 失败：`{ "status": "error", "message": "..." }`

部分研究任务和 trace 查询接口还会配合 `404`、`409` 等 HTTP 状态码。

## Java 对外 API

### `POST /api/upload`

上传并解析 PDF。

请求：

- `multipart/form-data`
- 字段：`file`

成功响应示例：

```json
{
  "status": "success",
  "pdfId": "example_pdf",
  "title": "Example Paper",
  "authors": ["Author A", "Author B"],
  "paper_skeleton": {
    "abstract": "...",
    "introduction": "...",
    "methods": "...",
    "results": "...",
    "discussion": "...",
    "conclusion": "..."
  },
  "paper_structure": {
    "research_problem": "...",
    "core_hypothesis": "...",
    "method_framework": [],
    "claimed_contributions": [],
    "experimental_logic": "...",
    "limitations": "...",
    "outlineVersion": "1.4",
    "sections": []
  },
  "translationLayoutIndex": {},
  "ragIndexed": true,
  "ragChunkCount": 42
}
```

说明：

- `pdfId` 会被规范化，前端后续都应以它作为论文主键
- 成功后 Java 会在 H2 中记录论文条目

### `POST /api/chat`

论文问答。

请求体：

```json
{
  "message": "这篇论文的核心方法是什么？",
  "pdfId": "example_pdf",
  "history": [],
  "paperSkeleton": {}
}
```

成功响应示例：

```json
{
  "status": "success",
  "message": "......",
  "rag_sources": [],
  "sentenceSourceMap": {},
  "queryPlan": {
    "original": "...",
    "rewritten": "...",
    "keywords": [],
    "intent": "解释方法",
    "needsRetrieval": true,
    "queries": [],
    "answerStyle": "concise"
  },
  "retrievalJudge": {
    "verdict": "CORRECT",
    "confidence": 0.82,
    "reason": "...",
    "missingAspects": [],
    "shouldRetry": false
  },
  "traceId": "..."
}
```

说明：

- 当带 `pdfId` 时，Java 会先把当前用户消息写入 H2，再从 H2 拼出远端 `history`
- Python 优先检索当前论文，不足时才补内部文献库

### `GET /api/chat/history/{sessionId}`

获取某篇论文的聊天历史。

成功响应示例：

```json
{
  "status": "success",
  "sessionId": "example_pdf",
  "messageCount": 2,
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "......",
      "timestamp": "2026-06-10T12:00:00"
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "......",
      "timestamp": "2026-06-10T12:00:03"
    }
  ]
}
```

### `POST /api/explain`

术语或选中文本解释。

请求体：

```json
{
  "text": "cross-attention",
  "pdfId": "example_pdf",
  "pageNumber": 3,
  "context": "..."
}
```

或：

```json
{
  "term": "cross-attention",
  "context": "..."
}
```

成功响应字段：

- `term`
- `explanation`
- `rag_sources`
- `queryPlan`
- `retrievalJudge`
- `traceId`

说明：

- Java 会把 `text` 适配成 Python 需要的 `term`

### `POST /api/translate-page`

逐页翻译。

请求体：

```json
{
  "pdfId": "example_pdf",
  "pageIndex": 0,
  "pageText": "...",
  "paperSkeleton": {},
  "pageLayout": {}
}
```

成功响应字段依页面结构而定，通常包括：

- `translatedText`
- `blocks`
- `pageIndex`
- 其他页面翻译布局相关字段

### `POST /api/critical-reading/{pdfId}`

对当前论文做批判阅读。

成功响应示例：

```json
{
  "status": "success",
  "pdfId": "example_pdf",
  "analysis": {
    "status": "success",
    "claimed_contributions": "...",
    "evidence_based_contributions": "...",
    "inferred_real_contributions": "...",
    "weaknesses": [],
    "overclaim_risks": [],
    "missing_evidence": [],
    "critical_analysis": "...",
    "claims": [
      {
        "id": "claim-1",
        "claim": "作者声称 F1 提升 20%。",
        "supportLevel": "PARTIAL",
        "evidenceSourceIds": ["source-1"],
        "missingEvidence": ["缺少可自动核验的表格结构"],
        "reason": "当前证据能对应作者主张，但尚不足以完整证明该贡献。",
        "numericVerificationStatus": "insufficient_for_auto_verification",
        "numericEvidenceCandidates": [
          {
            "sourceId": "source-1",
            "text": "Table 2: Main results. The proposed method improves F1 by 20% over the baseline.",
            "pageIndex": 4,
            "sectionId": "section-results",
            "chunkIndex": 8,
            "label": "Table 2",
            "metrics": ["f1"],
            "numbers": ["20%"],
            "reason": "匹配到 Table 2；指标 f1；数值 20%。候选片段仍需人工对照原表或图。",
            "status": "candidate_found"
          }
        ]
      }
    ],
    "contributionScore": {
      "score": 86,
      "level": "high",
      "label": "可信度较高",
      "summary": "2/3 条主张获得直接证据支撑。",
      "factors": [],
      "basis": {}
    },
    "riskScore": {
      "score": 24,
      "level": "low",
      "label": "低风险",
      "summary": "检测到 0 条证据不足主张、1 条报告级缺失证据和 0 条夸大风险。",
      "factors": [],
      "basis": {}
    },
    "noveltyDimensions": [
      {
        "id": "claim_support",
        "label": "主张支撑",
        "score": 80,
        "status": "strong",
        "detail": "主张证据较充分。"
      }
    ],
    "numericEvidenceSummary": {
      "claimCount": 3,
      "numericClaimCount": 1,
      "candidateCount": 1,
      "status": "insufficient_for_auto_verification"
    },
    "citationGraph": null,
    "rag_sources": [],
    "sentenceSourceMap": {},
    "resolved_from": "pdf_id",
    "pdf_id": "example_pdf",
    "traceId": "..."
  }
}
```

失败时常见情况：

- `paper_not_indexed`
- `rag_index_unavailable`

说明：

- `contributionScore`、`riskScore` 和 `noveltyDimensions` 是规则型评分，不代表训练模型输出；评分依据来自 claim 支撑度、缺失证据、夸大风险以及方法/实验轴证据覆盖。
- `claims[*].numericEvidenceCandidates` 是表格/数值候选定位，不是自动表格 OCR 或严格数值核验；即使找到 `Table/Figure`、指标名和百分比片段，`numericVerificationStatus` 也可能是 `insufficient_for_auto_verification`，前端应提示需要人工核对原文。
- `numericEvidenceCandidates[*].sourceId` 必须来自同次响应的 `rag_sources[*].sourceId`；`pageIndex` 仍为 0-based，可用于前端跳回原文。
- `citationGraph` 是可选真实引用网络；没有真实 citation graph 时必须为 `null`，前端不得用模拟网络兜底。存在真实图时形态为 `{ "nodes": [], "links": [] }`，节点至少需要稳定 `id`，边至少需要 `source/target`。
- 旧客户端可忽略新增字段；缺少新增字段时前端会按旧版结构降级展示。

### `POST /api/background-knowledge`

生成背景补课内容。

请求体：

```json
{
  "pdfId": "example_pdf",
  "paperSkeleton": {},
  "paperStructure": {},
  "paper_topic": null,
  "user_knowledge_level": "一般"
}
```

成功响应通常包含：

- `background_knowledge`
- `graph`
- `learning_path`
- `learning_path_sections`
- `rag_sources`
- `confidence`
- `sourceCoverage`
- `traceId`

说明：

- `user_knowledge_level` 当前前端归一到 `入门`、`一般`、`进阶`

### `POST /api/socratic-questions`

旧式一次性生成问题接口。

请求体：

```json
{
  "paper_content": "...",
  "reading_progress": "..."
}
```

成功响应：

```json
{
  "status": "success",
  "questions": [],
  "rag_sources": []
}
```

### `POST /api/socratic-session/start`

启动固定 5 轮引导学习。

请求体：

```json
{
  "pdfId": "example_pdf",
  "paperSkeleton": {},
  "readingProgress": "我已经读完摘要和引言"
}
```

成功响应：

```json
{
  "status": "success",
  "intro": "...",
  "totalQuestions": 5,
  "currentIndex": 1,
  "currentQuestion": "..."
}
```

### `POST /api/socratic-session/answer`

提交当前轮回答。

请求体：

```json
{
  "pdfId": "example_pdf",
  "paperSkeleton": {},
  "readingProgress": "......",
  "currentIndex": 1,
  "currentQuestion": "...",
  "userAnswer": "...",
  "turns": []
}
```

中间轮成功响应：

```json
{
  "status": "success",
  "evaluation": {
    "masteryLevel": "一般",
    "feedback": "...",
    "hint": "...",
    "coveredAspects": [],
    "missingAspects": [],
    "evidenceQuality": {}
  },
  "nextQuestion": "...",
  "nextIndex": 2,
  "isComplete": false
}
```

最后一轮成功响应：

```json
{
  "status": "success",
  "evaluation": {
    "masteryLevel": "较好",
    "feedback": "...",
    "hint": "...",
    "coveredAspects": [],
    "missingAspects": [],
    "evidenceQuality": {}
  },
  "finalSummary": "...",
  "reviewSuggestions": [],
  "isComplete": true
}
```

### `POST /api/research-tasks/brief-preview`

生成深度研究前的 brief 预览。

请求体：

```json
{
  "question": "这篇论文的方法相比基线真正改进了什么？",
  "pdfId": "example_pdf",
  "paperSkeleton": {},
  "userConstraints": "只关注方法和实验，不展开背景综述"
}
```

成功响应：

```json
{
  "status": "success",
  "briefPreview": {
    "question": "...",
    "pdfId": "example_pdf",
    "brief": "...",
    "assumptions": [],
    "clarifyingQuestions": [],
    "suggestedSubQuestions": [],
    "needsClarification": false,
    "source": "..."
  }
}
```

### `POST /api/research-tasks`

创建深度研究任务。

请求体：

```json
{
  "question": "这篇论文的方法相比基线真正改进了什么？",
  "pdfId": "example_pdf",
  "paperSkeleton": {},
  "userConstraints": "只关注方法和实验",
  "briefPreview": {}
}
```

成功响应：

```json
{
  "status": "success",
  "task": {
    "taskId": "...",
    "traceId": "...",
    "status": "pending",
    "stage": "planning",
    "progress": 0.0,
    "question": "...",
    "pdfId": "example_pdf",
    "plan": [
      {
        "id": "initial-1",
        "question": "子问题 1",
        "kind": "initial",
        "status": "pending",
        "sourceQuestion": "",
        "sourceMissingAspects": []
      }
    ],
    "traceSummary": {},
    "findings": [],
    "report": "",
    "error": "",
    "createdAt": "...",
    "updatedAt": "..."
  }
}
```

### `GET /api/research-tasks/latest?pdfId=...`

读取某篇论文最近一次研究任务快照。

成功响应：

```json
{
  "status": "success",
  "task": {}
}
```

没有快照时返回 `404`。

### `GET /api/research-tasks/{taskId}`

按 `taskId` 查询任务状态。

成功响应：

```json
{
  "status": "success",
  "task": {}
}
```

### `POST /api/research-tasks/{taskId}/cancel`

取消任务。

成功响应：

```json
{
  "status": "success",
  "task": {}
}
```

说明：

- 已结束任务会直接返回当前快照
- 该接口是幂等的

### `GET /api/traces/{traceId}`

获取脱敏 trace 摘要。

成功响应：

```json
{
  "status": "success",
  "trace": {
    "traceId": "...",
    "taskType": "chat",
    "status": "success",
    "startedAt": "...",
    "finishedAt": "...",
    "durationMs": 1234,
    "requestMeta": {},
    "responseMeta": {},
    "counters": {
      "llmCalls": 1,
      "retrievalCalls": 2
    },
    "steps": []
  }
}
```

说明：

- trace 是脱敏摘要，不应假设能拿到完整 prompt 或全文上下文
- Deep Research 终态 trace summary 会随研究任务 SQLite 快照保存；服务重启后，`GET /api/traces/{traceId}` 可从已完成任务快照恢复 summary。
- 普通聊天、批判阅读、背景补课等短请求 trace 仍是进程内临时摘要；服务重启或内存清空后可能返回 `404`。
- deep research 的 judge step 可能在 `steps[*].meta` 中包含 `verdict/judgeScore/coverageScore/missingAspects/retryReason/decision`，用于说明当前子问题为什么停止、补查文献库或触发 retry。
- deep research 证据缺口触发最小动态重规划时，trace 会包含 `research_follow_up_planning` step。
- deep research 完成时，`responseMeta` 可能包含 `averageJudgeScore/retryFindingCount/insufficientFindingCount/followUpCount`，用于快速排查长路径任务的证据效用和 follow-up 次数。

## Java 到 Python 的转发关系

| Java API | Python API |
| --- | --- |
| `POST /api/upload` | `POST /api/analyze-pdf` |
| `POST /api/explain` | `POST /api/explain-term` |
| `POST /api/chat` | `POST /api/chat` |
| `POST /api/translate-page` | `POST /api/translate-page` |
| `POST /api/critical-reading/{pdfId}` | `POST /api/deep-analysis` |
| `POST /api/background-knowledge` | `POST /api/background-knowledge` |
| `POST /api/socratic-questions` | `POST /api/socratic-questions` |
| `POST /api/socratic-session/start` | `POST /api/socratic-session/start` |
| `POST /api/socratic-session/answer` | `POST /api/socratic-session/answer` |
| `POST /api/research-tasks` | `POST /api/research-tasks` |
| `POST /api/research-tasks/brief-preview` | `POST /api/research-tasks/brief-preview` |
| `GET /api/research-tasks/latest` | `GET /api/research-tasks/latest` |
| `GET /api/research-tasks/{taskId}` | `GET /api/research-tasks/{taskId}` |
| `POST /api/research-tasks/{taskId}/cancel` | `POST /api/research-tasks/{taskId}/cancel` |
| `GET /api/traces/{traceId}` | `GET /api/traces/{traceId}` |

## Python 直接暴露但前端当前未直接使用的接口

### `POST /api/rag/add-literature`

上传文献到 Python 内部文献库。

### `POST /api/rag/retrieve`

直接调用 Python RAG 检索。

这两个接口当前没有经过 Java 正式转发给浏览器使用。

## 关键数据结构

### Evidence Item

多个接口中的 `rag_sources`、`sources` 采用相近的证据结构，常见字段包括：

- `sourceId`
- `id` 兼容字段
- `sourceType`
- `text`
- `pdfId`
- `pageIndex`
- `sectionId`
- `chunkIndex`
- `metadata`
- `similarity`
- `score`

注意：

- `pageIndex` 是 0-based
- 前端展示页码时通常会做 `pageIndex + 1`
- 旧缓存或旧索引可能没有页码与章节锚点

### Research Task Snapshot

研究任务快照固定字段：

- `taskId`
- `traceId`
- `status`
- `stage`
- `progress`
- `question`
- `pdfId`
- `plan`
- `findings`
- `conflicts`
- `traceSummary`：Deep Research 终态脱敏 trace 摘要；旧快照或未结束任务可能为空对象。
- `report`
- `error`
- `createdAt`
- `updatedAt`

`plan[*]` 兼容两种形态：

- 旧快照可能是字符串子问题，前端会按 `kind=initial` 处理。
- 新快照优先使用对象计划项：`{ "id": "initial-1", "question": "...", "kind": "initial|follow_up", "status": "pending|running|done", "sourceQuestion": "", "sourceMissingAspects": [] }`。

动态重规划规则：

- 每个任务最多追加 1 个 `kind=follow_up` 计划项。
- 仅当某个 finding 的最终 `verdict` 为 `INCORRECT` 且 `missingAspects` 非空时触发。
- follow-up 仍只使用当前论文和内部文献库，不引入外部 Web 搜索。

`findings[*]` 兼容字段：

- `subQuestion`
- `summary`
- `verdict`
- `judgeScore`：`0-100` 的规则型证据效用分，不等同于模型概率。
- `coverage`：`{ "score": 0.0, "matchedAspects": 0, "totalAspects": 0, "evidenceCount": 0, "sourceTypes": [] }`，其中 `score` 为 `0-1`。
- `missingAspects`
- `retryReason`：触发 retry 时记录原因；未触发 retry 时为空字符串。
- `isFollowUp`：`true` 表示该 finding 来自动态追加的 follow-up 子问题。
- `followUpOf`：follow-up 来源子问题。
- `sourceMissingAspects`：生成 follow-up 时引用的缺失证据点。
- `sourceIds`
- `sources`

`conflicts[*]` 兼容字段：

- `id`
- `topic`
- `claim`
- `conflictType`：`numeric_mismatch` 表示同一指标附近出现不同数值，`opposing_conclusion` 表示同一主题附近出现正反结论。
- `severity`：`high|medium|low`，仅表示需要人工核查的优先级，不代表自动裁决结果。
- `summary`
- `sourceIds`
- `sources`：复用 evidence item 字段，包含 `sourceId/sourceType/text/pageIndex/sectionId/chunkIndex/pdfId` 等可用来源锚点。

冲突检测规则：

- 当前为规则型 MVP，不调用 LLM 额外判定。
- 只基于 Deep Research 已检索并绑定到 `findings[*].sources` 的证据片段检测，不额外发起检索。
- 检出冲突时报告会单独列出“证据冲突/需人工核查”；系统不会自动融合为单一结论。

### Retrieval Judge

常见字段：

- `verdict`
- `confidence`
- `reason`
- `missingAspects`
- `shouldRetry`
- `judgeScore`
- `coverage`
- `retryReason`

## 错误处理建议

- 前端应同时读取 HTTP 状态码和响应体中的 `status/message/errorCode`
- 对 `paper_not_indexed`、`rag_index_unavailable` 这种业务错误，应给用户“重新上传或重新解析”的引导
- 对 `404` 的研究任务/trace 查询，不要伪造本地恢复成功

## 调试建议

如果你要联调接口，优先检查：

1. `frontend` 是否指向 `http://localhost:8081/api`
2. Java `PYTHON_URL` 是否正确
3. GROBID 是否可用
4. Python RAG 是否成功初始化
5. 当前论文是否已经完成索引
