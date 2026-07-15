package com.ai.assistant.backend_java.service;

import java.io.IOException;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

/**
 * Gateway for Agent projects, runs, tasks, traces, code execution,
 * research monitors, and paper draft generation.
 */
@Service
public class AgentGatewayService {

    @Autowired
    private RestTemplate restTemplate;

    @Value("${PYTHON_URL:http://localhost:8000/api}")
    private String PYTHON_SERVICE_URL;

    private ResponseEntity<Map<String, Object>> fwd(HttpMethod method, String path, Map<String, Object> payload) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, method, path, payload);
    }

    private ResponseEntity<Map<String, Object>> fwdGet(String path) {
        return fwd(HttpMethod.GET, path, null);
    }

    private ResponseEntity<Map<String, Object>> fwdPost(String path, Map<String, Object> payload) {
        return fwd(HttpMethod.POST, path, payload);
    }

    private String enc(String value) {
        return GatewayHelper.encode(value);
    }

    // ── Agent Projects ────────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> createAgentProject(Map<String, Object> request) {
        return fwdPost("/agent-projects", request);
    }

    public ResponseEntity<Map<String, Object>> listAgentProjects() {
        return fwdGet("/agent-projects");
    }

    public ResponseEntity<Map<String, Object>> getAgentProject(String projectId) {
        return fwdGet("/agent-projects/" + enc(projectId));
    }

    public ResponseEntity<Map<String, Object>> updateAgentProject(String projectId, Map<String, Object> request) {
        return fwd(HttpMethod.PATCH, "/agent-projects/" + enc(projectId), request);
    }

    public ResponseEntity<Map<String, Object>> deleteAgentProject(String projectId) {
        return fwd(HttpMethod.DELETE, "/agent-projects/" + enc(projectId), null);
    }

    public ResponseEntity<Map<String, Object>> addAgentProjectPapers(String projectId, Map<String, Object> request) {
        return fwdPost("/agent-projects/" + enc(projectId) + "/papers", request);
    }

    public ResponseEntity<Map<String, Object>> removeAgentProjectPaper(String projectId, String pdfId) {
        return fwd(HttpMethod.DELETE, "/agent-projects/" + enc(projectId) + "/papers/" + enc(pdfId), null);
    }

    // ── Agent Tasks / Runs ─────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> createAgentTask(String projectId, Map<String, Object> request) {
        return fwdPost("/agent-projects/" + enc(projectId) + "/tasks", request);
    }

    public ResponseEntity<Map<String, Object>> createAgentRun(String projectId, Map<String, Object> request) {
        return fwdPost("/agent-projects/" + enc(projectId) + "/runs", request);
    }

    public ResponseEntity<Map<String, Object>> getAgentWorkspace(String projectId) {
        return fwdGet("/agent-projects/" + enc(projectId) + "/workspace");
    }

    public ResponseEntity<Map<String, Object>> getLatestAgentTask(String projectId) {
        return fwdGet("/agent-projects/" + enc(projectId) + "/tasks/latest");
    }

    public ResponseEntity<Map<String, Object>> listAgentProjectTasks(String projectId, Integer limit) {
        String path = "/agent-projects/" + enc(projectId) + "/tasks";
        if (limit != null) path = path + "?limit=" + limit;
        return fwdGet(path);
    }

    public ResponseEntity<Map<String, Object>> getAgentTask(String taskId) {
        return fwdGet("/agent-tasks/" + enc(taskId));
    }

    public ResponseEntity<Map<String, Object>> getAgentRun(String runId) {
        return fwdGet("/agent-runs/" + enc(runId));
    }

    public ResponseEntity<Map<String, Object>> getAgentRunArtifacts(String runId) {
        return fwdGet("/agent-runs/" + enc(runId) + "/artifacts");
    }

    public ResponseEntity<Map<String, Object>> getAgentRunTimeline(String runId) {
        return fwdGet("/agent-runs/" + enc(runId) + "/timeline");
    }

    public ResponseEntity<Map<String, Object>> cancelAgentTask(String taskId) {
        return fwdPost("/agent-tasks/" + enc(taskId) + "/cancel", null);
    }

    public ResponseEntity<Map<String, Object>> reviewAgentRunPlan(String runId, Map<String, Object> request) {
        return fwdPost("/agent-runs/" + enc(runId) + "/plan-review", request);
    }

    public ResponseEntity<Map<String, Object>> reviewAgentPlan(String taskId, Map<String, Object> request) {
        return fwdPost("/agent-tasks/" + enc(taskId) + "/plan-review", request);
    }

    public ResponseEntity<Map<String, Object>> reviewAgentRunFinal(String runId, Map<String, Object> request) {
        return fwdPost("/agent-runs/" + enc(runId) + "/final-review", request);
    }

    public ResponseEntity<Map<String, Object>> reviewAgentFinal(String taskId, Map<String, Object> request) {
        return fwdPost("/agent-tasks/" + enc(taskId) + "/final-review", request);
    }

    public ResponseEntity<Map<String, Object>> getAgentTrace(String traceId) {
        return fwdGet("/agent-traces/" + enc(traceId));
    }

    public ResponseEntity<Map<String, Object>> answerAgentClarification(String runId, Map<String, Object> request) {
        return fwdPost("/agent-runs/" + enc(runId) + "/clarification", request);
    }

    // ── Code Execution ────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    public ResponseEntity<Map<String, Object>> uploadCodeExecutionArtifact(MultipartFile file) {
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return Objects.toString(file.getOriginalFilename(), "uploaded.csv");
                }
            });
            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
            ResponseEntity<Map> response = restTemplate.exchange(
                    PYTHON_SERVICE_URL + "/code-execution-artifacts",
                    HttpMethod.POST, requestEntity, Map.class);
            Map<String, Object> normalized = new java.util.LinkedHashMap<>();
            if (response.getBody() != null) {
                response.getBody().forEach((k, v) -> normalized.put(String.valueOf(k), v));
            }
            return ResponseEntity.status(response.getStatusCode()).body(normalized);
        } catch (IOException e) {
            return ResponseEntity.status(500).body(Map.of("status", "error", "message", "Failed to read artifact file."));
        } catch (Exception e) {
            return ResponseEntity.status(502).body(Map.of("status", "error", "message", "Failed to forward artifact."));
        }
    }

    public ResponseEntity<Map<String, Object>> createCodeExecutionJob(Map<String, Object> request) {
        return fwdPost("/code-execution-jobs", request);
    }

    public ResponseEntity<Map<String, Object>> listCodeExecutionJobs() {
        return fwdGet("/code-execution-jobs");
    }

    public ResponseEntity<Map<String, Object>> getCodeExecutionJob(String jobId) {
        return fwdGet("/code-execution-jobs/" + enc(jobId));
    }

    public ResponseEntity<Map<String, Object>> reviewCodeExecution(String jobId, Map<String, Object> request) {
        return fwdPost("/code-execution-jobs/" + enc(jobId) + "/execution-review", request);
    }

    public ResponseEntity<Map<String, Object>> reviewCodePublication(String jobId, Map<String, Object> request) {
        return fwdPost("/code-execution-jobs/" + enc(jobId) + "/publication-review", request);
    }

    // ── Paper Draft ───────────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> generatePaperDraft(Map<String, Object> request) {
        return fwdPost("/generate-paper-draft", request);
    }

    // ── Research Monitors ─────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> createResearchMonitor(Map<String, Object> request) {
        return fwdPost("/research-monitors", request);
    }

    public ResponseEntity<Map<String, Object>> listResearchMonitors() {
        return fwdGet("/research-monitors");
    }

    public ResponseEntity<Map<String, Object>> checkResearchMonitor(String monitorId) {
        return fwdGet("/research-monitors/" + enc(monitorId) + "/check");
    }

    public ResponseEntity<Map<String, Object>> getResearchMonitorDigest(String monitorId) {
        return fwdGet("/research-monitors/" + enc(monitorId) + "/digest");
    }

    public ResponseEntity<Map<String, Object>> deactivateResearchMonitor(String monitorId) {
        return fwd(HttpMethod.DELETE, "/research-monitors/" + enc(monitorId), null);
    }
}
