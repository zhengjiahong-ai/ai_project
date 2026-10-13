package com.ai.assistant.backend_java.service;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.ai.assistant.backend_java.model.TaskWorkspace;
import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class TaskWorkspaceService {
    private final TaskWorkspaceRepository repository;
    private final ObjectMapper mapper;
    @org.springframework.beans.factory.annotation.Autowired(required = false)
    private com.ai.assistant.backend_java.repository.PaperRepository researchPapers;

    public TaskWorkspaceService(TaskWorkspaceRepository repository, ObjectMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> list() {
        return repository.findAllByOrderByUpdatedAtDesc().stream().map(this::toResponse).toList();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> get(String id) {
        return toResponse(find(id));
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> addResearchSource(String taskId, String runId, String sourceId,
            Map<String, Object> input, Map<String, Object> source) {
        TaskWorkspace entity = repository.lockById(validId(taskId))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        Map<String, Object> task = toResponse(entity);
        if (!array(task.get("researchRuns"), "researchRuns").stream().anyMatch(value -> value instanceof Map<?, ?> run
                && runId.equals(run.get("runId")) && "deep-research-v2".equals(run.get("engineVersion")))) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "研究不属于当前任务");
        }
        String requestId = input.get("requestId") instanceof String value ? value : "";
        if (requestId.isBlank() || requestId.length() > 128) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "请提供有效请求 ID");
        }
        Map<String, Object> receipts = new LinkedHashMap<>(task.get("researchSourceReceipts") instanceof Map<?, ?> saved
                ? (Map<String, Object>) saved : Map.of());
        if (receipts.get(requestId) instanceof Map<?, ?> previous) {
            if (!runId.equals(previous.get("runId")) || !sourceId.equals(previous.get("sourceId"))) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "该请求 ID 已用于另一个来源");
            }
            return Map.of("status", "success", "workspace", task, "paperId", previous.get("paperId"));
        }
        requireRevision(input.get("expectedTaskRevision"), entity.getRevision());
        if (researchPapers == null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "论文存储不可用");
        String arxivId = source.get("arxivId") instanceof String value ? value : "";
        if (!arxivId.matches("(?:[0-9]{4}\\.[0-9]{4,5}|[a-z][a-z.-]+/[0-9]{7})(?:v[1-9][0-9]*)?")) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "学术来源标识无效");
        }
        byte[] pdf = null;
        String hash = source.get("contentHash") instanceof String value ? value : "";
        if (source.get("pdfBase64") instanceof String encoded) {
            if (encoded.length() > 12 * 1024 * 1024) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "全文过大");
            try {
                pdf = java.util.Base64.getDecoder().decode(encoded);
                if (pdf.length < 5 || pdf.length > 8 * 1024 * 1024
                        || !"%PDF-".equals(new String(pdf, 0, 5, java.nio.charset.StandardCharsets.US_ASCII))
                        || !hash.equals(java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(pdf)))) {
                    throw new IllegalArgumentException();
                }
            } catch (Exception error) { throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "全文内容校验失败"); }
        }
        String paperId = pdf != null ? hash + ".pdf" : "arxiv:" + arxivId;
        if (!researchPapers.existsById(paperId)) {
            var paper = new com.ai.assistant.backend_java.model.Paper();
            paper.setId(paperId);
            paper.setFileName(source.get("title") instanceof String title && !title.isBlank() ? title : arxivId);
            paper.setPdfBytes(pdf);
            paper.setProcessingStatus(pdf == null ? "metadata" : "pending");
            Map<String, Object> analysis = new LinkedHashMap<>();
            analysis.put("status", "success"); analysis.put("pdfId", paperId); analysis.put("title", paper.getFileName());
            analysis.put("externalSource", source.entrySet().stream().filter(entry -> !"pdfBase64".equals(entry.getKey()))
                    .collect(java.util.stream.Collectors.toMap(Map.Entry::getKey, entry -> entry.getValue() == null ? "" : entry.getValue())));
            try { paper.setAnalysisJson(mapper.writeValueAsString(analysis)); }
            catch (JsonProcessingException error) { throw new IllegalStateException(error); }
            researchPapers.saveAndFlush(paper);
        }
        List<String> ids = new ArrayList<>(paperIds(task.get("paperIds")));
        if (!ids.contains(paperId)) ids.add(paperId);
        task.put("paperIds", ids);
        receipts.put(requestId, Map.of("runId", runId, "sourceId", sourceId, "paperId", paperId));
        task.put("researchSourceReceipts", receipts);
        setContent(entity, task, taskId);
        return Map.of("status", "success", "workspace", toResponse(repository.saveAndFlush(entity)), "paperId", paperId);
    }

    @Transactional
    public Map<String, Object> create(Map<String, Object> input) {
        String id = input.get("id") == null ? "task:" + UUID.randomUUID() : validId(input.get("id"));
        if (repository.existsById(id)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已存在");
        }
        TaskWorkspace entity = new TaskWorkspace();
        entity.setId(id);
        Map<String, Object> initial = new LinkedHashMap<>(input);
        initial.put("researchRuns", List.of());
        setContent(entity, initial, id);
        return toResponse(repository.saveAndFlush(entity));
    }

    @Transactional
    public Map<String, Object> update(String id, Map<String, Object> input) {
        TaskWorkspace entity = find(id);
        if (input.containsKey("id") && !id.equals(validId(input.get("id")))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "任务 ID 与路径不一致");
        }
        requireRevision(input.get("revision"), entity.getRevision());
        Map<String, Object> protectedInput = new LinkedHashMap<>(input);
        protectedInput.put("researchRuns", toResponse(entity).getOrDefault("researchRuns", List.of()));
        if (!input.containsKey("archived")) protectedInput.put("archived", toResponse(entity).getOrDefault("archived", false));
        setContent(entity, protectedInput, id);
        return toResponse(repository.saveAndFlush(entity));
    }

    @Transactional
    public Map<String, Object> createFromClient(Map<String, Object> input) {
        Map<String, Object> safe = new LinkedHashMap<>(input);
        List<Object> history = new ArrayList<>(array(input.get("activityHistory"), "activityHistory"));
        if (input.get("activeActivity") instanceof Map<?, ?> activity) {
            Map<String, Object> imported = new LinkedHashMap<>();
            activity.forEach((key, value) -> imported.put(String.valueOf(key), value));
            imported.put("imported", true);
            history.add(imported);
        }
        safe.put("activeActivity", null);
        safe.put("activityHistory", history);
        safe.put("appliedRequestIds", List.of());
        safe.put("artifacts", protectCritiques(input.get("artifacts"), List.of(), true));
        safe.put("artifacts", protectResearchArtifacts(safe.get("artifacts"), List.of()));
        safe.put("messages", protectCritiques(input.get("messages"), List.of(), false));
        return create(safe);
    }

    /** Browser writes may not replace the server's activity, request receipts or run ownership. */
    @Transactional
    public Map<String, Object> updateFromClient(String id, Map<String, Object> input) {
        TaskWorkspace entity = find(id);
        requireRevision(input.get("revision"), entity.getRevision());
        Map<String, Object> authority = toResponse(entity);
        Map<String, Object> protectedInput = new LinkedHashMap<>(input);
        for (String field : List.of("activeActivity", "activityHistory", "appliedRequestIds", "researchRuns", "researchSourceReceipts", "legacyMigration", "legacyArchive")) {
            protectedInput.put(field, authority.get(field));
        }
        protectedInput.put("artifacts", protectCritiques(input.get("artifacts"), authority.get("artifacts"), true));
        protectedInput.put("artifacts", protectResearchArtifacts(protectedInput.get("artifacts"), authority.get("artifacts")));
        protectedInput.put("messages", protectCritiques(input.get("messages"), authority.get("messages"), false));
        // Removing materials cannot invalidate a saved activity or research snapshot.
        List<String> ids = paperIds(protectedInput.get("paperIds"));
        if (authority.get("activeActivity") instanceof Map<?, ?> activity
                && activity.get("pdfId") != null && !"finished".equals(activity.get("status")) && !ids.contains(activity.get("pdfId"))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "请先结束该论文的学习活动再移出材料");
        }
        return update(id, protectedInput);
    }

    /** Atomically merge a durable Python result; polling/replaying never publishes it twice. */
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> applyOperation(String id, Map<String, Object> operation) {
        TaskWorkspace entity = repository.lockById(validId(id))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        Map<String, Object> task = toResponse(entity);
        String requestId = (String) operation.get("requestId");
        List<Object> applied = new ArrayList<>(array(task.get("appliedRequestIds"), "appliedRequestIds"));
        if (applied.contains(requestId)) return task;
        Map<String, Object> payload = (Map<String, Object>) operation.get("input");
        Map<String, Object> upstream = (Map<String, Object>) payload.get("upstream");
        Map<String, Object> result = (Map<String, Object>) operation.get("result");
        String kind = (String) operation.get("kind");
        List<String> scope = paperIds(payload.get("paperIds"));
        if (!((List<?>) task.get("paperIds")).containsAll(scope)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "请求材料已移出任务，结果保留在请求记录中");
        }
        if (Integer.valueOf(1).equals(result.get("resultVersion"))) {
            if (!(result.get("materialScope") instanceof Map<?, ?> materialScope)
                    || !id.equals(materialScope.get("taskId")) || !scope.equals(materialScope.get("allowedPaperIds"))
                    || (materialScope.get("primaryPaperId") != null && !scope.contains(materialScope.get("primaryPaperId")))
                    || !(result.get("sources") instanceof List<?> sources)
                    || sources.stream().anyMatch(source -> !(source instanceof Map<?, ?> item) || !scope.contains(item.get("pdfId")))
                    || !(result.get("message") instanceof String message) || message.isBlank())
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "能力结果不符合任务材料快照");
        }
        if (kind.startsWith("learning.")) {
            Map<String, Object> old = task.get("activeActivity") instanceof Map<?, ?> value ? (Map<String, Object>) value : null;
            if (kind.equals("learning.action")) {
                if (old == null || !upstream.get("activityId").equals(old.get("activityId"))) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "学习活动已改变，原请求结果保留");
                }
                requireRevision(upstream.get("expectedRevision"), ((Number) old.get("revision")).longValue());
            } else if (old != null && !"finished".equals(old.get("status"))) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "已有未结束学习活动，请核对请求结果");
            }
            if (!(result.get("state") instanceof Map<?, ?> rawState)) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "学习结果缺少活动状态");
            }
            Map<String, Object> state = new LinkedHashMap<>((Map<String, Object>) rawState);
            long expectedRevision = kind.equals("learning.start") ? 0 : ((Number) upstream.get("expectedRevision")).longValue() + 1;
            if (!id.equals(state.get("taskId")) || !scope.getFirst().equals(state.get("pdfId"))
                    || !(state.get("activityId") instanceof String activityId) || activityId.isBlank()
                    || !(state.get("revision") instanceof Number revision) || revision.doubleValue() != expectedRevision
                    || (old != null && kind.equals("learning.action") && !old.get("activityId").equals(activityId))
                    || !List.of("active", "paused", "finished").contains(state.get("status"))) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "学习结果不符合任务快照");
            }
            state.put("id", activityId);
            state.put("paperIds", scope);
            state.put("primaryPaperId", scope.getFirst());
            state.put("strictScope", true);
            state.put("snapshot", Map.of("paperIds", scope, "primaryPaperId", scope.getFirst(), "strictScope", true));
            state.put("lastRequestId", requestId);
            List<Object> history = new ArrayList<>(array(task.get("activityHistory"), "activityHistory"));
            if (old != null) history.add(old);
            task.put("activityHistory", history);
            task.put("activeActivity", state);
            Map<String, Object> context = Map.of("taskId", id, "allowedPaperIds", scope,
                    "primaryPaperId", scope.getFirst(), "strictScope", true, "activityId", activityId);
            String content = String.valueOf(result.getOrDefault("message", ""));
            if (!Integer.valueOf(1).equals(result.get("resultVersion")) && "active".equals(state.get("status")) && result.get("question") instanceof String question) content += "\n\n" + question;
            List<Object> messages = new ArrayList<>(array(task.get("messages"), "messages"));
            String userText = String.valueOf(upstream.getOrDefault("text", upstream.getOrDefault("goal", "开始学习")));
            if (userText.isBlank()) userText = Map.of("hint", "给我一个提示", "skip", "跳过这个问题", "retry", "重新回答",
                    "pause", "暂停学习", "resume", "继续学习", "finish", "结束学习", "ask", "临时追问",
                    "remediate", "补充前置知识", "answer", "回答当前问题")
                    .getOrDefault(String.valueOf(upstream.get("action")), "继续学习");
            messages.add(Map.of("id", requestId + ":user", "role", "user", "content", userText, "context", context, "sourceRequestId", requestId));
            Map<String, Object> answer = new LinkedHashMap<>(Map.of("id", requestId + ":ai", "role", "ai", "content", content,
                    "context", context, "sourceRequestId", requestId));
            answer.put("rag_sources", result.getOrDefault("sources", List.of()));
            if (Integer.valueOf(1).equals(result.get("resultVersion"))) {
                answer.put("capability", result.get("capability"));
                answer.put("sentenceSourceMap", result.get("sentenceSourceMap"));
                if (result.get("artifact") instanceof Map<?, ?> artifact) {
                    if (!(artifact.get("text") instanceof String body) || body.isBlank() || !scope.equals(artifact.get("paperIds"))
                            || !result.get("sources").equals(artifact.get("sources")))
                        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "学习成果不符合材料快照");
                    String artifactId = requestId + ":artifact";
                    Map<String, Object> saved = new LinkedHashMap<>(Map.of("id", artifactId, "title", "学习成果", "text", body,
                            "paperIds", scope, "sources", artifact.get("sources"), "versions", List.of(), "sourceRequestId", requestId,
                            "createdAt", Instant.now().toString()));
                    saved.put("sentenceSourceMap", artifact.get("sentenceSourceMap"));
                    List<Object> artifacts = new ArrayList<>(array(task.get("artifacts"), "artifacts")); artifacts.add(saved);
                    task.put("artifacts", artifacts); answer.put("artifactId", artifactId);
                }
            }
            if (!Integer.valueOf(1).equals(result.get("resultVersion")) && result.get("evaluation") instanceof Map<?, ?> evaluation && evaluation.get("references") instanceof List<?> refs) {
                answer.put("sentenceSourceMap", refs.stream().filter(Map.class::isInstance).map(ref -> {
                    Map<?, ?> reference = (Map<?, ?>) ref;
                    return Map.of("target", "message", "sentence", result.getOrDefault("message", ""),
                            "sourceIds", List.of(String.valueOf(reference.get("sourceId"))), "quote", String.valueOf(reference.get("quote")));
                }).toList());
            }
            messages.add(answer);
            task.put("messages", messages);
        } else if (kind.equals("conversation.execute")) {
            if (!(result.get("materialScope") instanceof Map<?, ?> context) || !id.equals(context.get("taskId"))
                    || !scope.equals(context.get("allowedPaperIds"))
                    || !java.util.Objects.equals(upstream.get("primaryPaperId"), context.get("primaryPaperId"))
                    || !java.util.Objects.equals(upstream.get("strictScope"), context.get("strictScope"))
                    || !java.util.Objects.equals(upstream.get("capability"), result.get("capability"))
                    || !(result.get("message") instanceof String content) || content.isBlank()
                    || !(result.get("sources") instanceof List<?> sources)
                    || sources.stream().anyMatch(source -> !(source instanceof Map<?, ?> item) || !scope.contains(item.get("pdfId")))) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "对话结果不符合材料快照");
            }
            List<Object> messages = new ArrayList<>(array(task.get("messages"), "messages"));
            Map<?, ?> original = (Map<?, ?>) payload.get("original");
            Object displayText = original.get("displayText");
            messages.add(Map.of("id", requestId + ":user", "role", "user", "content",
                    displayText instanceof String text && !text.isBlank() ? text : upstream.get("message"),
                    "context", context, "sourceRequestId", requestId));
            Map<String, Object> answer = new LinkedHashMap<>(Map.of("id", requestId + ":ai", "role", "ai", "content", content,
                    "context", context, "sourceRequestId", requestId, "capability", result.get("capability")));
            answer.put("rag_sources", sources);
            answer.put("sentenceSourceMap", result.getOrDefault("sentenceSourceMap", List.of()));
            Map<?, ?> critique = CritiqueContract.validate(result.get("critique"), scope);
            if (critique != null) answer.put("critique", critique);
            if (result.get("artifact") instanceof Map<?, ?> artifact) {
                if (!(artifact.get("text") instanceof String body) || body.isBlank() || !scope.equals(artifact.get("paperIds"))
                        || !sources.equals(artifact.get("sources"))) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "成果不符合对话材料快照");
                String artifactId = requestId + ":artifact";
                Map<String, Object> saved = new LinkedHashMap<>(Map.of("id", artifactId, "title", "对话成果", "text", body,
                        "paperIds", scope, "sources", sources, "versions", List.of(), "sourceRequestId", requestId,
                        "createdAt", Instant.now().toString()));
                saved.put("sentenceSourceMap", artifact.getOrDefault("sentenceSourceMap", null));
                Map<?, ?> artifactCritique = CritiqueContract.validate(artifact.get("critique"), scope);
                if (artifactCritique != null && !artifactCritique.equals(critique))
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "成果与对话批判结构不一致");
                if (critique != null) { saved.put("critique", critique); saved.put("generatedText", body); saved.put("edited", false); }
                List<Object> artifacts = new ArrayList<>(array(task.get("artifacts"), "artifacts"));
                if (upstream.get("critiqueContext") instanceof Map<?, ?> prior && Boolean.TRUE.equals(prior.get("regenerate"))) {
                    int index = -1;
                    for (int i = 0; i < artifacts.size(); i++)
                        if (artifacts.get(i) instanceof Map<?, ?> old && java.util.Objects.equals(old.get("id"), prior.get("sourceArtifactId"))) index = i;
                    if (index < 0) throw new ResponseStatusException(HttpStatus.CONFLICT, "原成果已移出任务，新结果保留在请求记录中");
                    Map<?, ?> old = (Map<?, ?>) artifacts.get(index);
                    Object oldVersion = old.get("updatedAt") == null ? old.get("createdAt") : old.get("updatedAt");
                    if (!java.util.Objects.equals(String.valueOf(oldVersion), prior.get("version")))
                        throw new ResponseStatusException(HttpStatus.CONFLICT, "原成果已更新，新结果保留在请求记录中");
                    if (critique == null) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "重新核查结果缺少批判观点结构");
                    List<Object> versions = new ArrayList<>(array(old.get("versions"), "versions"));
                    Map<String, Object> snapshot = new LinkedHashMap<>();
                    for (String field : List.of("text", "critique", "generatedText", "edited", "sources", "paperIds", "sourceRequestId"))
                        if (old.containsKey(field)) snapshot.put(field, old.get(field));
                    snapshot.put("savedAt", oldVersion); snapshot.put("kind", "generated");
                    versions.add(snapshot);
                    artifactId = String.valueOf(old.get("id"));
                    saved.put("id", artifactId); saved.put("title", old.get("title"));
                    saved.put("createdAt", old.get("createdAt")); saved.put("updatedAt", Instant.now().toString());
                    saved.put("versions", versions);
                    artifacts.set(index, saved);
                } else artifacts.add(saved);
                task.put("artifacts", artifacts);
                answer.put("artifactId", artifactId);
            }
            messages.add(answer);
            task.put("messages", messages);
        } else if (kind.equals("research.start")) {
            if (!(result.get("task") instanceof Map<?, ?> research) || !(research.get("taskId") instanceof String researchId)) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究结果缺少任务标识");
            }
            List<Object> runs = new ArrayList<>(array(task.get("researchRuns"), "researchRuns"));
            runs.add(Map.of("researchId", researchId, "requestId", requestId, "paperIds", scope,
                    "primaryPaperId", upstream.get("pdfId"), "question", upstream.get("question"), "createdAt", operation.get("createdAt")));
            task.put("researchRuns", runs);
        } else {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "请求能力无效");
        }
        applied.add(requestId);
        task.put("appliedRequestIds", applied);
        setContent(entity, task, id);
        return toResponse(repository.saveAndFlush(entity));
    }

    /** Explicit recovery saves the generated text, without applying an obsolete learning state. */
    @Transactional
    public Map<String, Object> recoverOperationResult(String id, Map<String, Object> operation) {
        TaskWorkspace entity = repository.lockById(validId(id))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        Map<String, Object> task = toResponse(entity);
        String requestId = (String) operation.get("requestId");
        List<Object> applied = new ArrayList<>(array(task.get("appliedRequestIds"), "appliedRequestIds"));
        if (applied.contains(requestId)) return task;
        if (!id.equals(operation.get("taskId")) || !"succeeded".equals(operation.get("status"))
                || !List.of("conversation.execute", "learning.start", "learning.action").contains(operation.get("kind"))
                || !(operation.get("input") instanceof Map<?, ?> input)
                || !(operation.get("result") instanceof Map<?, ?> result))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "该请求没有可恢复的文字成果");
        List<String> scope = paperIds(input.get("paperIds"));
        if (!((List<?>) task.get("paperIds")).containsAll(scope))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "请先恢复原请求材料，再保存成果；已生成结果仍可查看");
        if (!(result.get("message") instanceof String message) || message.isBlank()
                || !(result.get("sources") instanceof List<?> sources)
                || sources.stream().anyMatch(source -> !(source instanceof Map<?, ?> item) || !scope.contains(item.get("pdfId")))
                || !(result.get("materialScope") instanceof Map<?, ?> context)
                || !id.equals(context.get("taskId")) || !scope.equals(context.get("allowedPaperIds"))
                || (context.get("primaryPaperId") != null && !scope.contains(context.get("primaryPaperId"))))
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "已生成结果不符合原材料快照");
        String body = message;
        if (result.get("artifact") instanceof Map<?, ?> artifact) {
            if (!(artifact.get("text") instanceof String text) || text.isBlank()
                    || !scope.equals(artifact.get("paperIds")) || !sources.equals(artifact.get("sources")))
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "成果不符合原材料快照");
            body = text;
        }
        String artifactId = requestId + ":artifact";
        Map<String, Object> artifact = new LinkedHashMap<>(Map.of("id", artifactId, "title", "恢复的成果",
                "text", body, "paperIds", scope, "sources", sources, "versions", List.of(),
                "sourceRequestId", requestId, "createdAt", Instant.now().toString()));
        artifact.put("sentenceSourceMap", result.containsKey("sentenceSourceMap") ? result.get("sentenceSourceMap") : List.of());
        Map<?, ?> critique = CritiqueContract.validate(result.get("critique"), scope);
        if (critique != null) { artifact.put("critique", critique); artifact.put("generatedText", body); artifact.put("edited", false); }
        List<Object> artifacts = new ArrayList<>(array(task.get("artifacts"), "artifacts"));
        artifacts.add(artifact); task.put("artifacts", artifacts);
        List<Object> messages = new ArrayList<>(array(task.get("messages"), "messages"));
        messages.add(Map.of("id", requestId + ":recovered", "role", "ai", "content", "已生成结果已保存为成果，当前学习位置保留。",
                "artifactId", artifactId, "sourceRequestId", requestId, "context", context,
                "rag_sources", sources, "timestamp", System.currentTimeMillis()));
        task.put("messages", messages); applied.add(requestId); task.put("appliedRequestIds", applied);
        setContent(entity, task, id);
        return toResponse(repository.saveAndFlush(entity));
    }

    /** Publish a completed research report under the task lock, without replacing client edits. */
    @Transactional
    public Map<String, Object> publishResearchResult(String id, String researchId, Map<?, ?> research) {
        TaskWorkspace entity = repository.lockById(validId(id))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        Map<String, Object> task = toResponse(entity);
        Map<?, ?> run = array(task.get("researchRuns"), "researchRuns").stream()
                .filter(value -> value instanceof Map<?, ?> item && researchId.equals(item.get("researchId")))
                .map(value -> (Map<?, ?>) value).findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "研究任务不属于当前任务"));
        if (!researchId.equals(research.get("taskId")))
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的任务不匹配");
        if (!"succeeded".equals(research.get("status"))) return task;
        String receipt = "research:" + researchId;
        List<Object> applied = new ArrayList<>(array(task.get("appliedRequestIds"), "appliedRequestIds"));
        if (applied.contains(receipt)) return task;
        List<String> scope = paperIds(run.get("paperIds"));
        if (!((List<?>) task.get("paperIds")).containsAll(scope))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "研究材料已移出任务，请恢复原材料后保存成果");
        if (!(research.get("report") instanceof String report) || report.isBlank())
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究报告为空，尚未保存成果");
        List<Object> sources = new ArrayList<>();
        List<String> conclusions = new ArrayList<>();
        for (Object raw : array(research.get("findings"), "findings")) {
            if (!(raw instanceof Map<?, ?> finding))
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究发现格式无效");
            if (finding.get("claims") instanceof List<?> claims && !claims.isEmpty()) {
                for (Object item : claims) {
                    if (conclusions.size() >= 3) break;
                    if (item instanceof Map<?, ?> claim && claim.get("summary") instanceof String summary && !summary.isBlank())
                        conclusions.add(summary.length() > 180 ? summary.substring(0, 180) + "…" : summary);
                }
            } else if (finding.get("summary") instanceof String summary && !summary.isBlank() && conclusions.size() < 3) {
                // Legacy findings can contain long internal source ids; sources remain available separately.
                String plain = summary.replaceAll("\\[[^\\]\\r\\n]*\\.pdf-chunk-[^\\]\\r\\n]*\\]", "").strip();
                conclusions.add(plain.length() > 180 ? plain.substring(0, 180) + "…" : plain);
            }
            for (Object evidence : array(finding.get("sources"), "sources")) {
                if (!(evidence instanceof Map<?, ?> source) || !(source.get("pdfId") instanceof String pdfId))
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究来源缺少论文标识");
                List<String> matches = scope.stream().filter(paper -> paper.equals(pdfId)
                        || paper.replaceFirst("(?i)\\.pdf$", "").equals(pdfId.replaceFirst("(?i)\\.pdf$", ""))).toList();
                if (matches.size() != 1)
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究来源超出材料快照或标识不明确");
                Map<String, Object> normalized = new LinkedHashMap<>();
                source.forEach((key, value) -> normalized.put(String.valueOf(key), value));
                normalized.put("pdfId", matches.getFirst());
                if (!sources.contains(normalized)) sources.add(normalized);
            }
        }
        String artifactId = receipt + ":artifact";
        String now = Instant.now().toString();
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("taskId", id); context.put("allowedPaperIds", scope);
        context.put("primaryPaperId", run.get("primaryPaperId")); context.put("strictScope", true);
        String preview = conclusions.isEmpty() ? "研究已完成。" : String.join("\n\n", conclusions);
        Map<String, Object> answer = new LinkedHashMap<>(Map.of("id", receipt + ":answer", "role", "ai",
                "content", preview + "\n\n完整报告已保存在成果中。", "capability", "research",
                "artifactId", artifactId, "sourceResearchId", researchId, "context", context,
                "rag_sources", sources, "sentenceSourceMap", List.of(), "timestamp", System.currentTimeMillis()));
        Map<String, Object> artifact = new LinkedHashMap<>(Map.of("id", artifactId, "title",
                run.get("question") instanceof String question && !question.isBlank() ? question : "研究成果",
                "text", report, "paperIds", scope, "sources", sources, "sourceResearchId", researchId,
                "versions", List.of(), "createdAt", now));
        List<Object> messages = new ArrayList<>(array(task.get("messages"), "messages"));
        List<Object> artifacts = new ArrayList<>(array(task.get("artifacts"), "artifacts"));
        // Existing client-published legacy results remain intact; mark them as already adopted.
        boolean saved = artifacts.stream().anyMatch(value -> value instanceof Map<?, ?> item
                && researchId.equals(item.get("sourceResearchId")));
        if (!saved) {
            artifacts.add(artifact);
            messages.add(answer);
        }
        task.put("messages", messages); task.put("artifacts", artifacts);
        applied.add(receipt); task.put("appliedRequestIds", applied);
        setContent(entity, task, id);
        return toResponse(repository.saveAndFlush(entity));
    }

    /** Research ownership can only be established after a successful upstream creation. */
    @Transactional
    public Map<String, Object> attachResearchRun(String id, Object revision, Map<String, Object> run) {
        TaskWorkspace entity = find(id);
        requireRevision(revision, entity.getRevision());
        Map<String, Object> input = toResponse(entity);
        List<Object> runs = new ArrayList<>(array(input.get("researchRuns"), "researchRuns"));
        runs.add(run);
        input.put("researchRuns", runs);
        setContent(entity, input, id);
        return toResponse(repository.saveAndFlush(entity));
    }

    /** V2: Publish completed research result with version protection. Immutable machine versions; user-edited artifacts never overwritten. */
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> publishV2ResearchResult(String taskId, String runId, Map<?, ?> research) {
        TaskWorkspace entity = repository.lockById(validId(taskId))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        Map<String, Object> task = toResponse(entity);

        // Atomic validation under lock: runId ownership, engine version, reportVersionId, revision numeric
        Map<?, ?> run = array(task.get("researchRuns"), "researchRuns").stream()
                .filter(value -> value instanceof Map<?, ?> item
                        && (runId.equals(item.get("runId")) || runId.equals(item.get("researchId"))))
                .map(value -> (Map<?, ?>) value).findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "研究运行不属于当前任务"));

        if (!taskId.equals(research.get("taskId"))) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的任务不匹配");
        }

        // Validate engine version under lock
        String storedEngine = run.get("engineVersion") instanceof String se ? se : null;
        if (!"deep-research-v2".equals(storedEngine)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "运行引擎版本不匹配");
        }

        // Validate incoming runId matches stored
        String returnedRunId = research.get("runId") instanceof String rr ? rr : null;
        if (returnedRunId != null && !runId.equals(returnedRunId)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的 runId 不匹配");
        }

        // Validate revision is numeric if present
        Object incomingRevision = research.get("runRevision");
        if (incomingRevision != null && !(incomingRevision instanceof Number)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的 runRevision 不是数字");
        }

        // Stale revision guard under lock
        Object storedRevision = run.get("runRevision");
        if (storedRevision instanceof Number storedRev && incomingRevision instanceof Number incomingRev) {
            if (incomingRev.longValue() < ((Number) storedRev).longValue()) {
                return task; // Stale, skip publication
            }
        }

        String status = research.get("status") instanceof String s ? s : null;
        if (!"completed".equals(status) && !"cancelled".equals(status) && !"failed".equals(status)) {
            return task;
        }

        Map<?, ?> report = research.get("report") instanceof Map<?, ?> r ? r : null;
        if (report == null || !(report.get("body") instanceof String body) || body.isBlank()) {
            return task;
        }

        // Validate reportVersionId is string if present
        Object rawReportVersionId = report.get("versionId");
        if (rawReportVersionId != null && !(rawReportVersionId instanceof String)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的 reportVersionId 不是字符串");
        }
        String reportVersionId = (String) rawReportVersionId;
        // Receipt keyed by runId + reportVersionId for proper dedup across versions
        String receipt = "v2-research:" + runId + ":" + (reportVersionId != null ? reportVersionId : "none");
        List<Object> applied = new ArrayList<>(array(task.get("appliedRequestIds"), "appliedRequestIds"));
        if (applied.contains(receipt)) return task;

        String origin = report.get("origin") instanceof String o ? o : "machine";
        List<?> sources = research.get("sources") instanceof List<?> s ? s : List.of();
        String summary = research.get("summary") instanceof String sum ? sum : "";
        String outcome = research.get("outcome") instanceof String out ? out : "complete";

        List<String> scope = paperIds(run.get("paperIds"));
        if (!((List<?>) task.get("paperIds")).containsAll(scope)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "研究材料已移出任务，请恢复原材料后保存成果");
        }

        String now = Instant.now().toString();
        List<Object> artifacts = new ArrayList<>(array(task.get("artifacts"), "artifacts"));
        List<Object> messages = new ArrayList<>(array(task.get("messages"), "messages"));

        // Check for existing machine version with same reportVersionId (immutable dedup)
        boolean machineVersionExists = artifacts.stream().anyMatch(value -> value instanceof Map<?, ?> item
                && runId.equals(item.get("sourceRunId"))
                && "machine".equals(item.get("origin"))
                && java.util.Objects.equals(reportVersionId, item.get("reportVersionId")));

        if (!machineVersionExists) {
            // Always save immutable machine version artifact
            String machineArtifactId = "v2-research:" + runId + ":" + (reportVersionId != null ? reportVersionId : "machine") + ":artifact";
            Map<String, Object> machineArtifact = new LinkedHashMap<>();
            machineArtifact.put("id", machineArtifactId);
            machineArtifact.put("title", research.get("title") instanceof String title && !title.isBlank() && title.length() <= 60 ? title
                    : run.get("question") instanceof String question && !question.isBlank() ? question : "研究成果");
            machineArtifact.put("text", body);
            machineArtifact.put("paperIds", scope);
            machineArtifact.put("sources", sources);
            machineArtifact.put("sourceRunId", runId);
            machineArtifact.put("sourceResearchId", runId); // frontend lookup alias
            machineArtifact.put("reportVersionId", reportVersionId);
            machineArtifact.put("origin", "machine");
            machineArtifact.put("outcome", outcome);
            machineArtifact.put("versions", List.of());
            machineArtifact.put("edited", false);
            machineArtifact.put("createdAt", now);
            artifacts.add(machineArtifact);
        }

        // Check if user has edited an artifact for this run.
        // Detect user edits via: edited=true, non-empty versions list, titleOrigin="user", or origin="user".
        boolean userEdited = artifacts.stream().anyMatch(value -> value instanceof Map<?, ?> item
                && runId.equals(item.get("sourceRunId")) && isUserModified(item));

        // Only create/update the "latest" (editable) artifact if user hasn't edited yet
        if (!userEdited) {
            String latestArtifactId = "v2-research:" + runId + ":latest:artifact";
            // Remove previous latest for this run (replace with new version)
            artifacts.removeIf(value -> value instanceof Map<?, ?> item
                    && runId.equals(item.get("sourceRunId"))
                    && latestArtifactId.equals(item.get("id")));

            Map<String, Object> latestArtifact = new LinkedHashMap<>();
            latestArtifact.put("id", latestArtifactId);
            latestArtifact.put("title", research.get("title") instanceof String title && !title.isBlank() && title.length() <= 60 ? title
                    : run.get("question") instanceof String question && !question.isBlank() ? question : "研究成果");
            latestArtifact.put("text", body);
            latestArtifact.put("paperIds", scope);
            latestArtifact.put("sources", sources);
            latestArtifact.put("sourceRunId", runId);
            latestArtifact.put("sourceResearchId", runId); // frontend lookup alias
            latestArtifact.put("reportVersionId", reportVersionId);
            latestArtifact.put("origin", "latest");
            latestArtifact.put("outcome", outcome);
            latestArtifact.put("versions", List.of());
            latestArtifact.put("edited", false);
            latestArtifact.put("createdAt", now);
            artifacts.add(latestArtifact);

            // Add/update answer message pointing to latest artifact
            String answerId = "v2-research:" + runId + ":latest:answer";
            messages.removeIf(value -> value instanceof Map<?, ?> item && answerId.equals(item.get("id")));

            Map<String, Object> context = new LinkedHashMap<>();
            context.put("taskId", taskId);
            context.put("allowedPaperIds", scope);
            context.put("strictScope", true);

            String preview = !summary.isBlank() ? summary : ("研究已完成（" + outcome + "）。");
            Map<String, Object> answer = new LinkedHashMap<>();
            answer.put("id", answerId);
            answer.put("role", "ai");
            answer.put("content", preview + "\n\n完整报告已保存在成果中。");
            answer.put("capability", "research");
            answer.put("artifactId", latestArtifactId);
            answer.put("sourceRunId", runId);
            answer.put("sourceResearchId", runId); // frontend lookup alias
            answer.put("context", context);
            answer.put("rag_sources", sources);
            answer.put("sentenceSourceMap", List.of());
            answer.put("timestamp", System.currentTimeMillis());
            messages.add(answer);
        }

        task.put("messages", messages);
        task.put("artifacts", artifacts);
        applied.add(receipt);
        task.put("appliedRequestIds", applied);
        if (incomingRevision instanceof Number revision) {
            ((Map<String, Object>) run).put("runRevision", revision.longValue());
            ((Map<String, Object>) run).put("status", status);
            ((Map<String, Object>) run).put("outcome", outcome);
        }
        setContent(entity, task, taskId);
        return toResponse(repository.saveAndFlush(entity));
    }

    /** V2: Update stored run revision atomically. Stale revisions ignored. */
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> updateV2RunRevision(String taskId, String runId, long revision, String status, String outcome) {
        TaskWorkspace entity = repository.lockById(validId(taskId))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        Map<String, Object> task = toResponse(entity);
        List<Object> runs = new ArrayList<>(array(task.get("researchRuns"), "researchRuns"));
        boolean updated = false;
        for (int i = 0; i < runs.size(); i++) {
            if (runs.get(i) instanceof Map<?, ?> run && runId.equals(run.get("runId"))) {
                Map<String, Object> mutable = new LinkedHashMap<>((Map<String, Object>) run);
                Object currentRev = mutable.get("runRevision");
                if (currentRev instanceof Number num && num.longValue() >= revision) {
                    return task; // Stale, ignore
                }
                mutable.put("runRevision", revision);
                if (status != null) mutable.put("status", status);
                if (outcome != null) mutable.put("outcome", outcome);
                runs.set(i, mutable);
                updated = true;
                break;
            }
        }
        if (!updated) return task;
        task.put("researchRuns", runs);
        setContent(entity, task, taskId);
        return toResponse(repository.saveAndFlush(entity));
    }

    @Transactional
    public void delete(String id, long revision) {
        TaskWorkspace entity = find(id);
        requireRevision(revision, entity.getRevision());
        repository.delete(entity);
        repository.flush();
    }

    private TaskWorkspace find(String id) {
        return repository.findById(validId(id))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
    }

    /** A browser may edit prose, but cannot manufacture server-grounded claims or material provenance. */
    private List<Object> protectResearchArtifacts(Object incoming, Object saved) {
        List<Object> output = new ArrayList<>();
        for (Object raw : array(incoming, "artifacts")) {
            Map<?, ?> item = (Map<?, ?>) raw;
            Map<?, ?> previous = array(saved, "artifacts").stream().filter(value -> value instanceof Map<?, ?> old
                    && java.util.Objects.equals(old.get("id"), item.get("id")) && old.get("sourceRunId") != null)
                    .map(value -> (Map<?, ?>) value).findFirst().orElse(null);
            if (previous != null && "machine".equals(previous.get("origin"))) {
                output.add(previous);
                continue;
            }
            Map<String, Object> copy = new LinkedHashMap<>();
            item.forEach((key, value) -> copy.put(String.valueOf(key), value));
            if (previous != null) {
                for (String field : List.of("sourceRunId", "sourceResearchId", "reportVersionId", "origin", "sources", "paperIds", "outcome", "createdAt")) {
                    if (previous.containsKey(field)) copy.put(field, previous.get(field));
                }
                if (!java.util.Objects.equals(item.get("text"), previous.get("text"))) copy.put("edited", true);
            } else if (copy.get("sourceRunId") != null || Set.of("machine", "latest").contains(java.util.Objects.toString(copy.get("origin"), ""))) {
                for (String field : List.of("sourceRunId", "sourceResearchId", "reportVersionId", "origin")) copy.remove(field);
                copy.put("edited", true);
            }
            output.add(copy);
        }
        // A stale/full workspace PUT must not erase immutable research history.
        for (Object raw : array(saved, "artifacts")) {
            if (raw instanceof Map<?, ?> item && "machine".equals(item.get("origin")) && item.get("sourceRunId") != null
                    && output.stream().noneMatch(value -> value instanceof Map<?, ?> candidate
                        && java.util.Objects.equals(candidate.get("id"), item.get("id")))) {
                Map<String, Object> retained = new LinkedHashMap<>();
                item.forEach((key, value) -> retained.put(String.valueOf(key), value));
                retained.put("hiddenFromLibrary", true);
                output.add(retained);
            }
        }
        return output;
    }

    private List<Object> protectCritiques(Object incoming, Object saved, boolean artifacts) {
        List<Object> output = new ArrayList<>();
        for (Object raw : array(incoming, artifacts ? "artifacts" : "messages")) {
            Map<?, ?> item = (Map<?, ?>) raw;
            Map<String, Object> copy = new LinkedHashMap<>(); item.forEach((key, value) -> copy.put(String.valueOf(key), value));
            Map<?, ?> previous = array(saved, "saved").stream().filter(value -> value instanceof Map<?, ?> old
                    && java.util.Objects.equals(old.get("id"), item.get("id")) && old.get("critique") instanceof Map<?, ?>)
                    .map(value -> (Map<?, ?>) value).findFirst().orElse(null);
            copy.remove("critique"); copy.remove("generatedText");
            if (previous != null) {
                for (String field : List.of("critique", "generatedText", "paperIds", "sources", "sourceRequestId", "createdAt", "context", "rag_sources"))
                    if (previous.containsKey(field)) copy.put(field, previous.get(field));
                if (artifacts) {
                    boolean changed = !java.util.Objects.equals(item.get("text"), previous.get("text"));
                    Map<?, ?> restored = array(previous.get("versions"), "versions").stream()
                            .filter(value -> value instanceof Map<?, ?> version && version.get("critique") instanceof Map<?, ?>
                                    && java.util.Objects.equals(version.get("text"), item.get("text")))
                            .map(value -> (Map<?, ?>) value).findFirst().orElse(null);
                    if (changed && restored != null)
                        for (String field : List.of("critique", "generatedText", "paperIds", "sources", "sourceRequestId"))
                            if (restored.containsKey(field)) copy.put(field, restored.get(field));
                    List<Object> versions = new ArrayList<>();
                    for (Object value : array(item.get("versions"), "versions")) {
                        Map<?, ?> version = (Map<?, ?>) value;
                        Map<String, Object> safeVersion = new LinkedHashMap<>();
                        version.forEach((key, content) -> safeVersion.put(String.valueOf(key), content));
                        safeVersion.remove("critique"); safeVersion.remove("generatedText");
                        Map<?, ?> authority = array(previous.get("versions"), "versions").stream()
                                .filter(old -> old instanceof Map<?, ?> oldVersion && java.util.Objects.equals(oldVersion.get("text"), version.get("text"))
                                        && java.util.Objects.equals(oldVersion.get("savedAt"), version.get("savedAt")))
                                .map(old -> (Map<?, ?>) old).findFirst().orElse(null);
                        if (authority == null && java.util.Objects.equals(previous.get("text"), version.get("text"))) authority = previous;
                        if (authority != null)
                            for (String field : List.of("critique", "generatedText", "edited", "paperIds", "sources", "sourceRequestId"))
                                if (authority.containsKey(field)) safeVersion.put(field, authority.get(field));
                        versions.add(safeVersion);
                    }
                    copy.put("versions", versions);
                    copy.put("edited", !java.util.Objects.equals(copy.get("text"), copy.get("generatedText")));
                    if (changed) copy.put("updatedAt", Instant.now().toString());
                    else if (previous.containsKey("updatedAt")) copy.put("updatedAt", previous.get("updatedAt"));
                }
            }
            output.add(copy);
        }
        return output;
    }

    private void setContent(TaskWorkspace entity, Map<String, Object> input, String id) {
        Map<String, Object> payload = normalize(input, id);
        Instant updatedAt = Instant.now().truncatedTo(java.time.temporal.ChronoUnit.MICROS);
        payload.put("updatedAt", updatedAt.toString());
        try {
            entity.setPayloadJson(mapper.writeValueAsString(payload));
        } catch (JsonProcessingException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "任务内容无法保存", exception);
        }
        entity.setUpdatedAt(updatedAt);
    }

    private Map<String, Object> normalize(Map<String, Object> input, String id) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", id);
        Object rawTitle = input.get("title");
        if (rawTitle != null && !(rawTitle instanceof String)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "任务标题必须是文字");
        }
        String title = rawTitle == null || ((String) rawTitle).isBlank()
                ? "未命名任务" : ((String) rawTitle).trim();
        if (title.length() > 500) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "任务标题过长");
        }
        payload.put("title", title);
        Object archived = input.get("archived");
        if (archived != null && !(archived instanceof Boolean)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "归档状态必须是布尔值");
        }
        payload.put("archived", Boolean.TRUE.equals(archived));
        List<String> paperIds = paperIds(input.get("paperIds"));
        payload.put("paperIds", paperIds);
        payload.put("messages", array(input.get("messages"), "messages"));
        payload.put("notes", array(input.get("notes"), "notes"));
        payload.put("artifacts", array(input.get("artifacts"), "artifacts"));
        payload.put("researchRuns", array(input.get("researchRuns"), "researchRuns"));
        payload.put("researchSourceReceipts", input.get("researchSourceReceipts") instanceof Map<?, ?> receipts ? receipts : Map.of());
        payload.put("activityHistory", array(input.get("activityHistory"), "activityHistory"));
        payload.put("appliedRequestIds", array(input.get("appliedRequestIds"), "appliedRequestIds"));
        for (String field : List.of("legacyMigration", "legacyArchive")) {
            if (input.get(field) != null && !(input.get(field) instanceof Map<?,?>))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " 必须是对象");
            if (input.get(field) != null) payload.put(field,input.get(field));
        }

        Object focusedPaper = input.get("focusedPaperId");
        if (focusedPaper != null && (!(focusedPaper instanceof String) || !paperIds.contains(focusedPaper))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "阅读焦点必须属于当前任务");
        }
        payload.put("focusedPaperId", focusedPaper);

        Object activeActivity = input.get("activeActivity");
        if (activeActivity != null && !(activeActivity instanceof Map<?, ?>)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "活动必须是对象");
        }
        payload.put("activeActivity", activeActivity);
        return payload;
    }

    private List<String> paperIds(Object value) {
        if (value == null) return List.of();
        if (!(value instanceof List<?> raw)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "论文 ID 必须是数组");
        }
        LinkedHashSet<String> unique = new LinkedHashSet<>();
        for (Object item : raw) {
            if (!(item instanceof String id) || id.isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "论文 ID 必须是非空文字");
            }
            unique.add(id);
        }
        return new ArrayList<>(unique);
    }

    private List<?> array(Object value, String field) {
        if (value == null) return List.of();
        if (!(value instanceof List<?> items)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " 必须是数组");
        }
        if (!field.equals("appliedRequestIds") && items.stream().anyMatch(item -> !(item instanceof Map<?, ?>))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " 的条目必须是对象");
        }
        return items;
    }

    /**
     * Detect whether an artifact has been modified by the user.
     * Signals: edited=true, non-empty versions list, titleOrigin="user", or origin="user".
     */
    @SuppressWarnings("unchecked")
    private boolean isUserModified(Map<?, ?> artifact) {
        if (Boolean.TRUE.equals(artifact.get("edited"))) return true;
        if ("user".equals(artifact.get("titleOrigin"))) return true;
        if ("user".equals(artifact.get("origin"))) return true;
        Object versions = artifact.get("versions");
        if (versions instanceof List<?> vList && !vList.isEmpty()) return true;
        return false;
    }

    private String validId(Object value) {
        if (!(value instanceof String id) || id.isBlank() || id.length() > 255) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "任务 ID 无效");
        }
        return id;
    }

    private void requireRevision(Object supplied, Long current) {
        if (!(supplied instanceof Number number) || number.doubleValue() != Math.rint(number.doubleValue())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "必须提供整数 revision");
        }
        if (current == null || number.longValue() != current) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已在其他位置更新");
        }
    }

    private Map<String, Object> toResponse(TaskWorkspace entity) {
        try {
            Map<String, Object> payload = mapper.readValue(entity.getPayloadJson(), new TypeReference<>() {});
            payload.put("id", entity.getId());
            payload.put("updatedAt", entity.getUpdatedAt().toString());
            payload.put("revision", entity.getRevision());
            return payload;
        } catch (IOException exception) {
            throw new IllegalStateException("无法读取已保存的任务", exception);
        }
    }
}
