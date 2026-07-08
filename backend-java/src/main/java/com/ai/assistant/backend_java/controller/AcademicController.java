package com.ai.assistant.backend_java.controller;

import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.ai.assistant.backend_java.service.AiService;

@CrossOrigin(origins = "http://localhost:5173", allowCredentials = "true")
@RestController
@RequestMapping("/api")
public class AcademicController {

    @Autowired
    private AiService aiService;

    @PostMapping("/code-execution-artifacts")
    public ResponseEntity<Map<String, Object>> uploadCodeExecutionArtifact(@RequestParam("file") MultipartFile file) {
        return aiService.uploadCodeExecutionArtifact(file);
    }

    @PostMapping("/code-execution-jobs")
    public ResponseEntity<Map<String, Object>> createCodeExecutionJob(@RequestBody Map<String, Object> request) {
        return aiService.createCodeExecutionJob(request);
    }

    @GetMapping("/code-execution-jobs")
    public ResponseEntity<Map<String, Object>> listCodeExecutionJobs() {
        return aiService.listCodeExecutionJobs();
    }

    @GetMapping("/code-execution-jobs/{jobId}")
    public ResponseEntity<Map<String, Object>> getCodeExecutionJob(@PathVariable String jobId) {
        return aiService.getCodeExecutionJob(jobId);
    }

    @PostMapping("/code-execution-jobs/{jobId}/execution-review")
    public ResponseEntity<Map<String, Object>> reviewCodeExecution(
            @PathVariable String jobId, @RequestBody Map<String, Object> request) {
        return aiService.reviewCodeExecution(jobId, request);
    }

    @PostMapping("/code-execution-jobs/{jobId}/publication-review")
    public ResponseEntity<Map<String, Object>> reviewCodePublication(
            @PathVariable String jobId, @RequestBody Map<String, Object> request) {
        return aiService.reviewCodePublication(jobId, request);
    }

    @PostMapping("/upload")
    public Map<String, Object> uploadPdf(@RequestParam("file") MultipartFile file) {
        return aiService.analyzePdf(file);
    }

    @PostMapping("/explain")
    public Map<String, Object> explainTerm(@RequestBody Map<String, Object> request) {
        return aiService.explainTerm(request);
    }

    @PostMapping("/chat")
    public Map<String, Object> chat(@RequestBody Map<String, Object> chatRequest) {
        return aiService.chat(chatRequest);
    }

    @PostMapping("/translate-page")
    public Map<String, Object> translatePage(@RequestBody Map<String, Object> request) {
        return aiService.translatePage(request);
    }

    @GetMapping("/chat/history/{sessionId}")
    public Map<String, Object> getChatHistory(@PathVariable String sessionId) {
        return aiService.getChatHistory(sessionId);
    }

    @PostMapping("/critical-reading/{pdfId}")
    public Map<String, Object> criticalReading(@PathVariable String pdfId) {
        return aiService.criticalReading(pdfId);
    }

    @PostMapping("/socratic-questions")
    public Map<String, Object> socraticQuestions(@RequestBody Map<String, Object> request) {
        return aiService.socraticQuestions(request);
    }

    @PostMapping("/socratic-session/start")
    public Map<String, Object> startSocraticSession(@RequestBody Map<String, Object> request) {
        return aiService.startSocraticSession(request);
    }

    @PostMapping("/socratic-session/answer")
    public Map<String, Object> answerSocraticSession(@RequestBody Map<String, Object> request) {
        return aiService.answerSocraticSession(request);
    }

    @PostMapping("/background-knowledge")
    public Map<String, Object> backgroundKnowledge(@RequestBody Map<String, Object> request) {
        return aiService.backgroundKnowledge(request);
    }

    @PostMapping("/research-tasks")
    public ResponseEntity<Map<String, Object>> createResearchTask(@RequestBody Map<String, Object> request) {
        return aiService.createResearchTask(request);
    }

    @PostMapping("/research-tasks/brief-preview")
    public ResponseEntity<Map<String, Object>> previewResearchBrief(@RequestBody Map<String, Object> request) {
        return aiService.previewResearchBrief(request);
    }

    @GetMapping("/research-tasks/latest")
    public ResponseEntity<Map<String, Object>> getLatestResearchTask(@RequestParam String pdfId) {
        return aiService.getLatestResearchTask(pdfId);
    }

    @GetMapping("/research-tasks/{taskId}")
    public ResponseEntity<Map<String, Object>> getResearchTask(@PathVariable String taskId) {
        return aiService.getResearchTask(taskId);
    }

    @PostMapping("/research-tasks/{taskId}/cancel")
    public ResponseEntity<Map<String, Object>> cancelResearchTask(@PathVariable String taskId) {
        return aiService.cancelResearchTask(taskId);
    }

    @PostMapping("/research-tasks/{taskId}/plan-review")
    public ResponseEntity<Map<String, Object>> reviewResearchPlan(@PathVariable String taskId, @RequestBody Map<String, Object> request) {
        return aiService.reviewResearchPlan(taskId, request);
    }

    @PostMapping("/research-tasks/{taskId}/final-review")
    public ResponseEntity<Map<String, Object>> reviewResearchFinal(@PathVariable String taskId, @RequestBody Map<String, Object> request) {
        return aiService.reviewResearchFinal(taskId, request);
    }

    @GetMapping("/traces/{traceId}")
    public ResponseEntity<Map<String, Object>> getTrace(@PathVariable String traceId) {
        return aiService.getTrace(traceId);
    }

    @PostMapping("/agent-projects")
    public ResponseEntity<Map<String, Object>> createAgentProject(@RequestBody Map<String, Object> request) {
        return aiService.createAgentProject(request);
    }

    @GetMapping("/agent-projects")
    public ResponseEntity<Map<String, Object>> listAgentProjects() {
        return aiService.listAgentProjects();
    }

    @GetMapping("/agent-projects/{projectId}")
    public ResponseEntity<Map<String, Object>> getAgentProject(@PathVariable String projectId) {
        return aiService.getAgentProject(projectId);
    }

    @PatchMapping("/agent-projects/{projectId}")
    public ResponseEntity<Map<String, Object>> updateAgentProject(
            @PathVariable String projectId,
            @RequestBody Map<String, Object> request) {
        return aiService.updateAgentProject(projectId, request);
    }

    @DeleteMapping("/agent-projects/{projectId}")
    public ResponseEntity<Map<String, Object>> deleteAgentProject(@PathVariable String projectId) {
        return aiService.deleteAgentProject(projectId);
    }

    @PostMapping("/agent-projects/{projectId}/papers")
    public ResponseEntity<Map<String, Object>> addAgentProjectPapers(
            @PathVariable String projectId,
            @RequestBody Map<String, Object> request) {
        return aiService.addAgentProjectPapers(projectId, request);
    }

    @DeleteMapping("/agent-projects/{projectId}/papers/{pdfId}")
    public ResponseEntity<Map<String, Object>> removeAgentProjectPaper(
            @PathVariable String projectId,
            @PathVariable String pdfId) {
        return aiService.removeAgentProjectPaper(projectId, pdfId);
    }

    @PostMapping("/agent-projects/{projectId}/tasks")
    public ResponseEntity<Map<String, Object>> createAgentTask(
            @PathVariable String projectId,
            @RequestBody Map<String, Object> request) {
        return aiService.createAgentTask(projectId, request);
    }

    @PostMapping("/agent-projects/{projectId}/runs")
    public ResponseEntity<Map<String, Object>> createAgentRun(
            @PathVariable String projectId,
            @RequestBody Map<String, Object> request) {
        return aiService.createAgentRun(projectId, request);
    }

    @GetMapping("/agent-projects/{projectId}/workspace")
    public ResponseEntity<Map<String, Object>> getAgentWorkspace(@PathVariable String projectId) {
        return aiService.getAgentWorkspace(projectId);
    }

    @GetMapping("/agent-projects/{projectId}/tasks/latest")
    public ResponseEntity<Map<String, Object>> getLatestAgentTask(@PathVariable String projectId) {
        return aiService.getLatestAgentTask(projectId);
    }

    @GetMapping("/agent-projects/{projectId}/tasks")
    public ResponseEntity<Map<String, Object>> listAgentProjectTasks(
            @PathVariable String projectId,
            @RequestParam(required = false) Integer limit) {
        return aiService.listAgentProjectTasks(projectId, limit);
    }

    @GetMapping("/agent-tasks/{taskId}")
    public ResponseEntity<Map<String, Object>> getAgentTask(@PathVariable String taskId) {
        return aiService.getAgentTask(taskId);
    }

    @GetMapping("/agent-runs/{runId}")
    public ResponseEntity<Map<String, Object>> getAgentRun(@PathVariable String runId) {
        return aiService.getAgentRun(runId);
    }

    @GetMapping("/agent-runs/{runId}/artifacts")
    public ResponseEntity<Map<String, Object>> getAgentRunArtifacts(@PathVariable String runId) {
        return aiService.getAgentRunArtifacts(runId);
    }

    @GetMapping("/agent-runs/{runId}/timeline")
    public ResponseEntity<Map<String, Object>> getAgentRunTimeline(@PathVariable String runId) {
        return aiService.getAgentRunTimeline(runId);
    }

    @PostMapping("/agent-tasks/{taskId}/cancel")
    public ResponseEntity<Map<String, Object>> cancelAgentTask(@PathVariable String taskId) {
        return aiService.cancelAgentTask(taskId);
    }

    @PostMapping("/agent-runs/{runId}/plan-review")
    public ResponseEntity<Map<String, Object>> reviewAgentRunPlan(@PathVariable String runId, @RequestBody Map<String, Object> request) {
        return aiService.reviewAgentRunPlan(runId, request);
    }

    @PostMapping("/agent-tasks/{taskId}/plan-review")
    public ResponseEntity<Map<String, Object>> reviewAgentPlan(@PathVariable String taskId, @RequestBody Map<String, Object> request) {
        return aiService.reviewAgentPlan(taskId, request);
    }

    @PostMapping("/agent-runs/{runId}/final-review")
    public ResponseEntity<Map<String, Object>> reviewAgentRunFinal(@PathVariable String runId, @RequestBody Map<String, Object> request) {
        return aiService.reviewAgentRunFinal(runId, request);
    }

    @PostMapping("/agent-tasks/{taskId}/final-review")
    public ResponseEntity<Map<String, Object>> reviewAgentFinal(@PathVariable String taskId, @RequestBody Map<String, Object> request) {
        return aiService.reviewAgentFinal(taskId, request);
    }

    @GetMapping("/agent-traces/{traceId}")
    public ResponseEntity<Map<String, Object>> getAgentTrace(@PathVariable String traceId) {
        return aiService.getAgentTrace(traceId);
    }
}
