package com.ai.assistant.backend_java.controller;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.ai.assistant.backend_java.service.TaskLearningService;
import com.ai.assistant.backend_java.service.TaskResearchService;
import com.ai.assistant.backend_java.service.TaskOperationService;

@CrossOrigin(origins = {"http://localhost:5173", "http://127.0.0.1:5173"}, allowCredentials = "true")
@RestController
@RequestMapping("/api/task-workspaces")
public class TaskWorkspaceController {
    private final TaskWorkspaceService service;
    private final TaskLearningService learning;
    private final TaskResearchService research;
    private final TaskOperationService operations;

    public TaskWorkspaceController(TaskWorkspaceService service, TaskLearningService learning, TaskResearchService research, TaskOperationService operations) {
        this.service = service;
        this.learning = learning;
        this.research = research;
        this.operations = operations;
    }

    @GetMapping
    public List<Map<String, Object>> list() {
        return service.list();
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(@RequestBody Map<String, Object> task) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.createFromClient(task));
    }

    @GetMapping("/{id}")
    public Map<String, Object> get(@PathVariable String id) {
        return service.get(id);
    }

    @PutMapping("/{id}")
    public Map<String, Object> update(@PathVariable String id, @RequestBody Map<String, Object> task) {
        return service.updateFromClient(id, task);
    }

    @PostMapping("/{id}/operations")
    public Map<String, Object> startOperation(@PathVariable String id, @RequestBody Map<String, Object> input) { return operations.start(id, input); }
    @GetMapping("/{id}/operations")
    public List<Map<String, Object>> listOperations(@PathVariable String id) { return operations.list(id); }
    @GetMapping("/{id}/operations/{requestId}")
    public Map<String, Object> getOperation(@PathVariable String id, @PathVariable String requestId) { return operations.get(id, requestId); }
    @PostMapping("/{id}/operations/{requestId}/cancel")
    public Map<String, Object> cancelOperation(@PathVariable String id, @PathVariable String requestId,
            @RequestBody(required = false) Map<String, Object> intent) { return operations.cancel(id, requestId, intent); }
    @PostMapping("/{id}/operations/{requestId}/retry")
    public Map<String, Object> retryOperation(@PathVariable String id, @PathVariable String requestId) { return operations.retry(id, requestId); }
    @PostMapping("/{id}/operations/{requestId}/recover-result")
    public Map<String, Object> recoverOperationResult(@PathVariable String id, @PathVariable String requestId) {
        return operations.recoverResult(id, requestId);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id, @RequestParam long revision) {
        service.delete(id, revision);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{id}/learning/start")
    public Map<String, Object> startLearning(@PathVariable String id, @RequestBody Map<String, Object> input) {
        return learning.start(id, input);
    }

    @PostMapping("/{id}/learning/action")
    public Map<String, Object> learningAction(@PathVariable String id, @RequestBody Map<String, Object> input) {
        return learning.action(id, input);
    }

    // --- Unified Research Endpoints (engine-dispatched by stored run) ---

    @PostMapping("/{id}/research/start")
    public Map<String, Object> startResearch(@PathVariable String id, @RequestBody Map<String, Object> input) {
        return research.startUnified(id, input);
    }

    /** GET dispatches by stored engine version: legacy or v2. */
    @GetMapping("/{id}/research/{runId}")
    public Map<String, Object> getResearch(@PathVariable String id, @PathVariable String runId) {
        return research.getUnified(id, runId);
    }

    @PostMapping("/{id}/research/{runId}/resume")
    public Map<String, Object> resumeResearch(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.resumeUnified(id, runId, input);
    }

    @PostMapping("/{id}/research/{runId}/cancel")
    public Map<String, Object> cancelResearch(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.cancelUnified(id, runId, input);
    }

    @PostMapping("/{id}/research/{runId}/pause")
    public Map<String, Object> pauseResearch(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.pauseUnified(id, runId, input);
    }

    @PostMapping("/{id}/research/{runId}/clarify")
    public Map<String, Object> clarifyResearch(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.clarifyUnified(id, runId, input);
    }

    @PostMapping("/{id}/research/{runId}/plan")
    public Map<String, Object> planResearch(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.planUnified(id, runId, input);
    }

    @PostMapping("/{id}/research/{runId}/continue")
    public Map<String, Object> continueResearch(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.continueUnified(id, runId, input);
    }

    @GetMapping("/{id}/research/{runId}/sources")
    public Map<String, Object> getResearchSources(@PathVariable String id, @PathVariable String runId) {
        return research.getSourcesUnified(id, runId);
    }

    @GetMapping("/{id}/research/capabilities")
    public Map<String, Object> researchCapabilities(@PathVariable String id) {
        return research.capabilities(id);
    }

    @PostMapping("/{id}/research/{runId}/publication-sync")
    public Map<String, Object> syncResearchPublication(@PathVariable String id, @PathVariable String runId) {
        return research.syncPublication(id, runId);
    }

    @PostMapping("/{id}/research/{runId}/sources/{sourceId}/add")
    public Map<String, Object> addResearchSource(@PathVariable String id, @PathVariable String runId,
            @PathVariable String sourceId, @RequestBody Map<String, Object> input) {
        return research.addSource(id, runId, sourceId, input);
    }

    @GetMapping("/{id}/research/{runId}/events")
    public Map<String, Object> getResearchEvents(@PathVariable String id, @PathVariable String runId) {
        return research.getEventsUnified(id, runId);
    }

    /** Legacy review endpoints preserved for backward compatibility. */
    @PostMapping("/{id}/research/{runId}/plan-review")
    public Map<String, Object> reviewResearchPlan(@PathVariable String id, @PathVariable String runId, @RequestBody Map<String, Object> input) {
        return research.reviewPlan(id, runId, input);
    }

    @PostMapping("/{id}/research/{runId}/final-review")
    public Map<String, Object> reviewResearchFinal(@PathVariable String id, @PathVariable String runId, @RequestBody Map<String, Object> input) {
        return research.reviewFinal(id, runId, input);
    }

    // --- Internal scope-check endpoint for Python before model/retrieval ---
    @PostMapping("/{id}/research/{runId}/scope-check")
    public Map<String, Object> scopeCheck(@PathVariable String id, @PathVariable String runId,
            @RequestBody(required = false) Map<String, Object> input) {
        return research.scopeCheck(id, runId, input);
    }
}
