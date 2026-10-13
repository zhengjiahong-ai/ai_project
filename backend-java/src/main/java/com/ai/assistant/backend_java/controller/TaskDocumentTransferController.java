package com.ai.assistant.backend_java.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.*;
import com.ai.assistant.backend_java.service.TaskDocumentTransferService;

@CrossOrigin(origins = {"http://localhost:5173", "http://127.0.0.1:5173"}, allowCredentials = "true")
@RestController
@RequestMapping("/api/task-workspaces")
public class TaskDocumentTransferController {
    private final TaskDocumentTransferService transfers;
    public TaskDocumentTransferController(TaskDocumentTransferService transfers) { this.transfers = transfers; }
    @PostMapping("/{id}/documents/move")
    public Map<String, Object> move(@PathVariable String id, @RequestBody Map<String, Object> input) {
        return transfers.move(id, input);
    }
    @GetMapping("/{id}/documents/moves/{requestId}")
    public Map<String, Object> get(@PathVariable String id, @PathVariable String requestId) { return transfers.get(id, requestId); }
}
