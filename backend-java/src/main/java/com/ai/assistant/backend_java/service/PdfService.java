package com.ai.assistant.backend_java.service;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.security.MessageDigest;
import java.util.HexFormat;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.web.server.ResponseStatusException;

import com.ai.assistant.backend_java.model.ChatMessage;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.ChatMessageRepository;
import com.ai.assistant.backend_java.repository.PaperRepository;

@Service
public class PdfService {

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    private PaperRepository paperRepository;

    @Autowired
    private ChatMessageRepository chatMessageRepository;

    @Autowired
    private TaskWorkspaceService taskWorkspaceService;

    @Value("${PYTHON_URL:http://localhost:8000/api}")
    private String PYTHON_SERVICE_URL;

    // ── PDF Upload ────────────────────────────────────────────────────────

    public synchronized Map<String, Object> analyzePdf(MultipartFile file) {
        final byte[] bytes;
        final String storageName;
        try {
            bytes = file.getBytes();
            storageName = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)) + ".pdf";
        } catch (Exception error) {
            throw new IllegalStateException("无法读取上传文件", error);
        }
        Paper existing = paperRepository.findById(storageName).orElse(null);
        if (existing != null && (List.of("queued", "parsing").contains(Objects.toString(existing.getProcessingStatus(), ""))
                || "running".equals(existing.getAiAnalysisStatus())))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "论文正在处理，请稍后重试");
        if (existing != null && existing.getAnalysisJson() != null
                && (existing.getAiAnalysisStatus() == null || "completed".equals(existing.getAiAnalysisStatus()))) {
            try { return new ObjectMapper().readValue(existing.getAnalysisJson(), new TypeReference<Map<String, Object>>() {}); }
            catch (IOException error) { throw new IllegalStateException("无法读取已保存解析结果", error); }
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new ByteArrayResource(bytes) {
            @Override public String getFilename() { return storageName; }
        });
        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        @SuppressWarnings("unchecked")
        Map<String, Object> response = restTemplate.postForObject(
                PYTHON_SERVICE_URL + "/analyze-pdf", requestEntity, Map.class);

        if (response != null && "success".equals(response.get("status"))) {
            String resolvedPdfId = Objects.toString(response.getOrDefault("pdfId", file.getOriginalFilename()));
            Paper paper = existing == null ? new Paper() : existing;
            paper.setId(resolvedPdfId);
            paper.setFileName(file.getOriginalFilename());
            response.put("pdfId", resolvedPdfId);
            paper.setPdfBytes(bytes);
            paper.setProcessingStatus(Boolean.TRUE.equals(response.get("ragIndexed")) ? "ready" : "degraded");
            paper.setAiAnalysisStatus(Objects.toString(response.get("aiAnalysisStatus"), "completed"));
            paper.setProcessingError(null);
            try { paper.setAnalysisJson(new ObjectMapper().writeValueAsString(response)); }
            catch (IOException error) { throw new IllegalStateException("无法保存解析结果", error); }
            paperRepository.save(paper);
        }
        return response;
    }

    // ── Chat ──────────────────────────────────────────────────────────────

    public Map<String, Object> chat(Map<String, Object> chatRequest) {
        String message = Objects.toString(chatRequest.get("message"), "");
        String pdfId = (String) chatRequest.get("pdfId");
        String taskId = Objects.toString(chatRequest.get("taskId"), "").trim();
        String sessionKey = taskId.isEmpty() ? pdfId : "task:" + taskId;

        if (!taskId.isEmpty()) {
            Map<String, Object> task = taskWorkspaceService.get(taskId);
            List<?> taskPapers = (List<?>) task.get("paperIds");
            Object requested = chatRequest.get("allowedPaperIds");
            if (requested == null) {
                chatRequest.put("allowedPaperIds", List.of());
            } else if (!(requested instanceof List<?> papers)
                    || papers.stream().anyMatch(id -> !(id instanceof String) || !taskPapers.contains(id))) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "指定材料不属于当前任务");
            }
        }

        if (sessionKey != null) {
            ChatMessage userMessage = new ChatMessage();
            userMessage.setPdfId(sessionKey);
            userMessage.setRole("user");
            userMessage.setContent(message);
            chatMessageRepository.save(userMessage);
            // Task clients supply history filtered by the current material snapshot.
            // Legacy database messages have no source provenance and must not replace it.
            if (taskId.isEmpty()) {
                chatRequest.put("history", buildHistoryPayload(sessionKey));
            } else if (!(chatRequest.get("history") instanceof List<?>)) {
                chatRequest.put("history", List.of());
            }
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> response = restTemplate.postForObject(PYTHON_SERVICE_URL + "/chat", chatRequest, Map.class);

        if (response != null && "success".equals(response.get("status")) && sessionKey != null) {
            ChatMessage aiMessage = new ChatMessage();
            aiMessage.setPdfId(sessionKey);
            aiMessage.setRole("ai");
            aiMessage.setContent(Objects.toString(response.get("message"), ""));
            chatMessageRepository.save(aiMessage);
        }
        return response;
    }

    public Map<String, Object> getChatHistory(String sessionId) {
        List<ChatMessage> history = chatMessageRepository.findByPdfIdOrderByTimestampAsc(sessionId);
        List<Map<String, Object>> messages = new ArrayList<>();
        for (ChatMessage message : history) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", message.getId());
            item.put("role", normalizeRoleForApi(message.getRole()));
            item.put("content", message.getContent());
            item.put("timestamp", message.getTimestamp());
            messages.add(item);
        }
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", "success");
        response.put("sessionId", sessionId);
        response.put("messageCount", messages.size());
        response.put("messages", messages);
        return response;
    }

    // ── Explain / Translate / Socratic / Background / Critical ────────────

    public Map<String, Object> explainTerm(Map<String, Object> request) {
        Map<String, Object> convertedRequest = new HashMap<>();
        Object text = request.getOrDefault("text", request.get("term"));
        convertedRequest.put("term", Objects.toString(text, ""));
        convertedRequest.put("context", Objects.toString(request.get("context"), ""));
        if (request.containsKey("pdfId")) convertedRequest.put("pdfId", request.get("pdfId"));
        if (request.containsKey("pageNumber")) convertedRequest.put("pageNumber", request.get("pageNumber"));
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/explain-term", convertedRequest, Map.class);
    }

    public Map<String, Object> translatePage(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/translate-page", request, Map.class);
    }

    public Map<String, Object> socraticQuestions(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/socratic-questions", request, Map.class);
    }

    public Map<String, Object> startSocraticSession(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/socratic-session/start", request, Map.class);
    }

    public Map<String, Object> answerSocraticSession(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/socratic-session/answer", request, Map.class);
    }

    public Map<String, Object> backgroundKnowledge(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/background-knowledge", request, Map.class);
    }

    public Map<String, Object> criticalReading(String pdfId) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("pdf_id", pdfId);
        Map<String, Object> pythonResponse;
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = restTemplate.postForObject(
                    PYTHON_SERVICE_URL + "/deep-analysis", payload, Map.class);
            pythonResponse = response;
        } catch (HttpStatusCodeException error) {
            pythonResponse = GatewayHelper.parsePythonErrorBody(error);
            pythonResponse.putIfAbsent("httpStatus", error.getStatusCode().value());
        }
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", pythonResponse != null ? pythonResponse.getOrDefault("status", "error") : "error");
        response.put("pdfId", pdfId);
        response.put("analysis", pythonResponse);
        if (pythonResponse == null) {
            response.put("message", "Python service returned no response.");
        } else if (pythonResponse.containsKey("message")) {
            response.put("message", pythonResponse.get("message"));
        }
        if (pythonResponse != null && pythonResponse.containsKey("errorCode")) {
            response.put("errorCode", pythonResponse.get("errorCode"));
        }
        return response;
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private ByteArrayResource toNamedPdfResource(MultipartFile file) {
        try {
            final String originalFilename = Objects.toString(file.getOriginalFilename(), "uploaded.pdf");
            return new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() { return originalFilename; }
            };
        } catch (IOException error) {
            throw new IllegalStateException("Failed to read uploaded PDF bytes.", error);
        }
    }

    private List<Map<String, String>> buildHistoryPayload(String pdfId) {
        List<ChatMessage> history = chatMessageRepository.findByPdfIdOrderByTimestampAsc(pdfId);
        List<Map<String, String>> historyList = new ArrayList<>();
        int lastIndex = history.size() - 1;
        for (int index = 0; index < history.size(); index++) {
            ChatMessage item = history.get(index);
            if (index == lastIndex && "user".equals(item.getRole())) continue;
            Map<String, String> message = new HashMap<>();
            message.put("role", normalizeRoleForApi(item.getRole()));
            message.put("content", item.getContent());
            historyList.add(message);
        }
        return historyList;
    }

    private String normalizeRoleForApi(String role) {
        return "ai".equals(role) ? "assistant" : role;
    }
}
