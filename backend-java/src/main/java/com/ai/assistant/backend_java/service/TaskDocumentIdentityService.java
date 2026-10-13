package com.ai.assistant.backend_java.service;
import java.util.*;
import java.nio.charset.StandardCharsets;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import com.ai.assistant.backend_java.model.TaskMigrationSnapshot;
import com.ai.assistant.backend_java.repository.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;
@Service
public class TaskDocumentIdentityService {
    private final TaskWorkspaceRepository repository;
    private final TaskMigrationSnapshotRepository backups;
    private final TaskWorkspaceService tasks;
    private final ObjectMapper mapper;
    public TaskDocumentIdentityService(TaskWorkspaceRepository repository, TaskMigrationSnapshotRepository backups,
            TaskWorkspaceService tasks, ObjectMapper mapper) {
        this.repository = repository; this.backups = backups; this.tasks = tasks; this.mapper = mapper;
    }
    @Transactional
    public Map<String,Object> identify(String id, Map<String,Object> input) {
        var entity = repository.lockById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "任务不存在"));
        var original = tasks.get(id);
        if (!(input.get("revision") instanceof Number n) || n.doubleValue() != n.longValue())
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "必须提供整数 revision");
        if (n.longValue() != entity.getRevision()) throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已更新，请刷新后重试");
        var patched = new LinkedHashMap<String,Object>(original);
        int changed = 0;
        for (String field : List.of("notes", "artifacts")) {
            var documents = new ArrayList<Object>();
            for (Object raw : (List<?>) original.getOrDefault(field, List.of())) {
                var document = new LinkedHashMap<String,Object>();
                ((Map<?,?>)raw).forEach((key,value) -> document.put(String.valueOf(key), value));
                Object identity = document.get("id"), artifactId = document.get("artifactId");
                if (!(identity instanceof String text && !text.isBlank())
                        && !(artifactId instanceof String artifactText && !artifactText.isBlank())) {
                    if (identity != null) document.put("legacyId", identity);
                    document.put("id", "document:" + UUID.randomUUID());
                    changed++;
                }
                documents.add(document);
            }
            patched.put(field, documents);
        }
        if (changed == 0) return Map.of("task", original, "identified", 0);
        String backupId = "document-identities:" + UUID.nameUUIDFromBytes((id + ":" + entity.getRevision()).getBytes(StandardCharsets.UTF_8));
        var backup = new TaskMigrationSnapshot(); backup.setId(backupId); backup.setTaskId(id);
        try { backup.setPayloadJson(mapper.writeValueAsString(original)); }
        catch (Exception error) { throw new IllegalStateException("无法备份原任务", error); }
        backups.saveAndFlush(backup);
        return Map.of("task", tasks.update(id, patched), "identified", changed, "backupId", backupId);
    }
    @Transactional(readOnly=true)
    public Map<String,Object> backup(String taskId, String backupId) {
        var record = backups.findById(backupId).filter(item -> item.getTaskId().equals(taskId))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "备份不存在"));
        try { return mapper.readValue(record.getPayloadJson(), new TypeReference<>() {}); }
        catch (Exception error) { throw new IllegalStateException("无法读取迁移备份", error); }
    }
}
