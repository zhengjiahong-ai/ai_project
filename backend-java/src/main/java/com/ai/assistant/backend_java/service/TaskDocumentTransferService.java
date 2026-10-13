package com.ai.assistant.backend_java.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import com.ai.assistant.backend_java.model.TaskDocumentTransfer;
import com.ai.assistant.backend_java.repository.TaskDocumentTransferRepository;
import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Both task writes and the replay receipt commit together. */
@Service
public class TaskDocumentTransferService {
    private final TaskWorkspaceService tasks;
    private final TaskWorkspaceRepository workspaces;
    private final TaskDocumentTransferRepository receipts;
    private final ObjectMapper mapper;
    public TaskDocumentTransferService(TaskWorkspaceService tasks, TaskWorkspaceRepository workspaces,
            TaskDocumentTransferRepository receipts, ObjectMapper mapper) {
        this.tasks = tasks; this.workspaces = workspaces; this.receipts = receipts; this.mapper = mapper;
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> move(String sourceId, Map<String, Object> input) {
        String targetId = text(input.get("targetTaskId"));
        String requestId = text(input.get("requestId"));
        String documentId = text(input.get("documentId"));
        String collection = text(input.get("collection"));
        if (sourceId.equals(targetId) || !List.of("notes", "artifacts").contains(collection))
            throw error(HttpStatus.BAD_REQUEST, "请选择其他任务和有效文档类型");
        // Stable order prevents two opposite transfers from deadlocking.
        for (String id : List.of(sourceId, targetId).stream().sorted().toList())
            workspaces.lockById(id).orElseThrow(() -> error(HttpStatus.NOT_FOUND, "任务不存在"));
        String identity;
        try { identity = mapper.writeValueAsString(List.of(sourceId, targetId, collection, documentId)); }
        catch (Exception failure) { throw new IllegalStateException(failure); }
        var old = receipts.findById(requestId);
        if (old.isPresent()) {
            if (!identity.equals(old.get().getIdentity())) throw error(HttpStatus.CONFLICT, "请求标识已用于另一移动");
            return response(sourceId, targetId, requestId);
        }
        Map<String, Object> source = tasks.get(sourceId), target = tasks.get(targetId);
        revision(input.get("sourceRevision"), source.get("revision"));
        revision(input.get("targetRevision"), target.get("revision"));
        List<Object> originals = new ArrayList<>((List<Object>) source.get(collection));
        List<Object> destination = new ArrayList<>((List<Object>) target.get(collection));
        var matches = originals.stream().filter(Map.class::isInstance).map(x -> (Map<?, ?>) x)
            .filter(x -> documentId.equals(x.get("id")) || documentId.equals(x.get("artifactId"))).toList();
        if (matches.size() != 1) throw error(HttpStatus.CONFLICT, "文档已移动或标识不明确，请刷新");
        if (destination.stream().anyMatch(x -> x instanceof Map<?, ?> item &&
                (documentId.equals(item.get("id")) || documentId.equals(item.get("artifactId")))))
            throw error(HttpStatus.CONFLICT, "目标任务存在同名标识文档，请先核对");
        Map<String, Object> moved = new LinkedHashMap<>((Map<String, Object>) matches.getFirst());
        LinkedHashSet<String> materials = new LinkedHashSet<>((List<String>) target.get("paperIds"));
        LinkedHashSet<String> required = new LinkedHashSet<>();
        if (moved.get("paperIds") instanceof List<?> ids) for (Object id : ids) required.add(text(id));
        for (String field : List.of("sources", "rag_sources")) {
            if (moved.get(field) instanceof List<?> sources) for (Object raw : sources)
                if (raw instanceof Map<?, ?> item) {
                    Object paper = item.get("pdfId") == null ? item.get("sourcePdfId") : item.get("pdfId");
                    if (paper == null && item.get("metadata") instanceof Map<?,?> metadata) paper = metadata.get("id");
                    if (paper != null) required.add(text(paper));
                }
        }
        if (moved.get("sourcePdfId") != null) required.add(text(moved.get("sourcePdfId")));
        List<String> added = required.stream().filter(id -> !materials.contains(id)).toList();
        if (!added.isEmpty() && !Boolean.TRUE.equals(input.get("includeMaterials")))
            throw error(HttpStatus.CONFLICT, "目标任务缺少来源论文，请确认一并加入材料");
        materials.addAll(required);
        List<Object> history = new ArrayList<>(moved.get("transferHistory") instanceof List<?> list ? list : List.of());
        history.add(Map.of("sourceTaskId", sourceId, "targetTaskId", targetId, "requestId", requestId,
            "movedAt", Instant.now().toString()));
        moved.put("transferHistory", history);
        originals.remove(matches.getFirst()); destination.add(moved);
        source.put(collection, originals); target.put(collection, destination); target.put("paperIds", new ArrayList<>(materials));
        tasks.update(sourceId, source); tasks.update(targetId, target);
        TaskDocumentTransfer receipt = new TaskDocumentTransfer(); receipt.setId(requestId); receipt.setIdentity(identity);
        receipts.saveAndFlush(receipt);
        return response(sourceId, targetId, requestId);
    }

    private Map<String, Object> response(String source, String target, String request) {
        return Map.of("requestId", request, "status", "succeeded", "sourceTask", tasks.get(source), "targetTask", tasks.get(target));
    }
    @Transactional(readOnly = true)
    public Map<String, Object> get(String sourceId, String requestId) {
        var receipt = receipts.findById(text(requestId)).orElseThrow(() -> error(HttpStatus.NOT_FOUND, "移动请求尚未完成"));
        try {
            List<?> identity = mapper.readValue(receipt.getIdentity(), List.class);
            if (!sourceId.equals(identity.get(0))) throw error(HttpStatus.NOT_FOUND, "移动请求不属于该任务");
            return response(sourceId, (String) identity.get(1), requestId);
        } catch (ResponseStatusException failure) { throw failure; }
        catch (Exception failure) { throw new IllegalStateException(failure); }
    }
    private String text(Object raw) {
        if (!(raw instanceof String value) || value.isBlank() || value.length() > 255)
            throw error(HttpStatus.BAD_REQUEST, "移动标识无效");
        return value;
    }
    private void revision(Object supplied, Object actual) {
        if (!(supplied instanceof Number number) || number.doubleValue() != Math.rint(number.doubleValue()))
            throw error(HttpStatus.BAD_REQUEST, "必须提供双方整数版本");
        if (number.longValue() != ((Number) actual).longValue()) throw error(HttpStatus.CONFLICT, "任务已有新版本，请刷新后移动");
    }
    private ResponseStatusException error(HttpStatus status, String message) { return new ResponseStatusException(status, message); }
}
