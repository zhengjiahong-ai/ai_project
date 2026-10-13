package com.ai.assistant.backend_java.controller;
import java.util.Map;
import org.springframework.web.bind.annotation.*;
import com.ai.assistant.backend_java.service.TaskDocumentIdentityService;
@CrossOrigin(origins={"http://localhost:5173", "http://127.0.0.1:5173"}, allowCredentials="true")
@RestController
@RequestMapping("/api/task-workspaces")
public class TaskDocumentIdentityController {
    private final TaskDocumentIdentityService service;
    public TaskDocumentIdentityController(TaskDocumentIdentityService service) { this.service = service; }
    @PostMapping("/{id}/documents/identify")
    public Map<String,Object> identify(@PathVariable String id, @RequestBody Map<String,Object> body) { return service.identify(id, body); }
    @GetMapping("/{id}/migration-backups/{backupId}")
    public Map<String,Object> backup(@PathVariable String id, @PathVariable String backupId) { return service.backup(id, backupId); }
}
