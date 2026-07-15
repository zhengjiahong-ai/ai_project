package com.ai.assistant.backend_java.service;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class ResearchService {

    @Autowired
    private RestTemplate restTemplate;

    @Value("${PYTHON_URL:http://localhost:8000/api}")
    private String PYTHON_SERVICE_URL;

    public ResponseEntity<Map<String, Object>> createResearchTask(Map<String, Object> request) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.POST, "/research-tasks", request);
    }

    public ResponseEntity<Map<String, Object>> previewResearchBrief(Map<String, Object> request) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.POST, "/research-tasks/brief-preview", request);
    }

    public ResponseEntity<Map<String, Object>> getResearchTask(String taskId) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.GET, "/research-tasks/" + GatewayHelper.encode(taskId), null);
    }

    public ResponseEntity<Map<String, Object>> getLatestResearchTask(String pdfId) {
        String encodedPdfId = URLEncoder.encode(String.valueOf(pdfId), StandardCharsets.UTF_8).replace("+", "%20");
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.GET, "/research-tasks/latest?pdfId=" + encodedPdfId, null);
    }

    public ResponseEntity<Map<String, Object>> cancelResearchTask(String taskId) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.POST, "/research-tasks/" + GatewayHelper.encode(taskId) + "/cancel", null);
    }

    public ResponseEntity<Map<String, Object>> reviewResearchPlan(String taskId, Map<String, Object> request) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.POST, "/research-tasks/" + GatewayHelper.encode(taskId) + "/plan-review", request);
    }

    public ResponseEntity<Map<String, Object>> reviewResearchFinal(String taskId, Map<String, Object> request) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.POST, "/research-tasks/" + GatewayHelper.encode(taskId) + "/final-review", request);
    }

    public ResponseEntity<Map<String, Object>> getTrace(String traceId) {
        return GatewayHelper.forward(restTemplate, PYTHON_SERVICE_URL, HttpMethod.GET, "/traces/" + GatewayHelper.encode(traceId), null);
    }
}
