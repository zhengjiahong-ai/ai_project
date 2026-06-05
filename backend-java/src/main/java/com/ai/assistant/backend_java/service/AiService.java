package com.ai.assistant.backend_java.service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.net.URLEncoder;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ai.assistant.backend_java.model.ChatMessage;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.ChatMessageRepository;
import com.ai.assistant.backend_java.repository.PaperRepository;

@Service
public class AiService {
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    private PaperRepository paperRepository;

    @Autowired
    private ChatMessageRepository chatMessageRepository;

    @Value("${PYTHON_URL:http://localhost:8000/api}")
    private String PYTHON_SERVICE_URL;

    public Map<String, Object> analyzePdf(MultipartFile file) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", toNamedPdfResource(file));

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        @SuppressWarnings("unchecked")
        Map<String, Object> response = restTemplate.postForObject(
                PYTHON_SERVICE_URL + "/analyze-pdf",
                requestEntity,
                Map.class);

        if (response != null && "success".equals(response.get("status"))) {
            String resolvedPdfId = Objects.toString(response.getOrDefault("pdfId", file.getOriginalFilename()));
            Paper paper = new Paper();
            paper.setId(resolvedPdfId);
            paper.setFileName(file.getOriginalFilename());
            paperRepository.save(paper);
            response.put("pdfId", resolvedPdfId);
        }

        return response;
    }

    private ByteArrayResource toNamedPdfResource(MultipartFile file) {
        try {
            final String originalFilename = Objects.toString(file.getOriginalFilename(), "uploaded.pdf");
            return new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return originalFilename;
                }
            };
        } catch (IOException error) {
            throw new IllegalStateException("Failed to read uploaded PDF bytes.", error);
        }
    }

    public Map<String, Object> explainTerm(Map<String, Object> request) {
        Map<String, Object> convertedRequest = new HashMap<>();
        Object text = request.getOrDefault("text", request.get("term"));
        convertedRequest.put("term", Objects.toString(text, ""));
        convertedRequest.put("context", Objects.toString(request.get("context"), ""));

        if (request.containsKey("pdfId")) {
            convertedRequest.put("pdfId", request.get("pdfId"));
        }
        if (request.containsKey("pageNumber")) {
            convertedRequest.put("pageNumber", request.get("pageNumber"));
        }

        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/explain-term", convertedRequest, Map.class);
    }

    public Map<String, Object> chat(Map<String, Object> chatRequest) {
        String message = Objects.toString(chatRequest.get("message"), "");
        String pdfId = (String) chatRequest.get("pdfId");

        if (pdfId != null) {
            ChatMessage userMessage = new ChatMessage();
            userMessage.setPdfId(pdfId);
            userMessage.setRole("user");
            userMessage.setContent(message);
            chatMessageRepository.save(userMessage);

            chatRequest.put("history", buildHistoryPayload(pdfId));
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> response = restTemplate.postForObject(PYTHON_SERVICE_URL + "/chat", chatRequest, Map.class);

        if (response != null && "success".equals(response.get("status")) && pdfId != null) {
            ChatMessage aiMessage = new ChatMessage();
            aiMessage.setPdfId(pdfId);
            aiMessage.setRole("ai");
            aiMessage.setContent(Objects.toString(response.get("message"), ""));
            chatMessageRepository.save(aiMessage);
        }

        return response;
    }

    public Map<String, Object> translatePage(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/translate-page", request, Map.class);
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

    public Map<String, Object> criticalReading(String pdfId) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("pdf_id", pdfId);

        Map<String, Object> pythonResponse;
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = restTemplate.postForObject(
                    PYTHON_SERVICE_URL + "/deep-analysis",
                    payload,
                    Map.class);
            pythonResponse = response;
        } catch (HttpStatusCodeException error) {
            pythonResponse = parsePythonErrorBody(error);
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

    public ResponseEntity<Map<String, Object>> createResearchTask(Map<String, Object> request) {
        return forwardResearchTask(HttpMethod.POST, "/research-tasks", request);
    }

    public ResponseEntity<Map<String, Object>> previewResearchBrief(Map<String, Object> request) {
        return forwardResearchTask(HttpMethod.POST, "/research-tasks/brief-preview", request);
    }

    public ResponseEntity<Map<String, Object>> getResearchTask(String taskId) {
        return forwardResearchTask(HttpMethod.GET, "/research-tasks/" + taskId, null);
    }

    public ResponseEntity<Map<String, Object>> getLatestResearchTask(String pdfId) {
        String encodedPdfId = URLEncoder.encode(String.valueOf(pdfId), StandardCharsets.UTF_8).replace("+", "%20");
        return forwardResearchTask(HttpMethod.GET, "/research-tasks/latest?pdfId=" + encodedPdfId, null);
    }

    public ResponseEntity<Map<String, Object>> cancelResearchTask(String taskId) {
        return forwardResearchTask(HttpMethod.POST, "/research-tasks/" + taskId + "/cancel", null);
    }

    public ResponseEntity<Map<String, Object>> getTrace(String traceId) {
        String encodedTraceId = URLEncoder.encode(String.valueOf(traceId), StandardCharsets.UTF_8).replace("+", "%20");
        return forwardReadOnlyTrace(HttpMethod.GET, "/traces/" + encodedTraceId);
    }

    private List<Map<String, String>> buildHistoryPayload(String pdfId) {
        List<ChatMessage> history = chatMessageRepository.findByPdfIdOrderByTimestampAsc(pdfId);
        List<Map<String, String>> historyList = new ArrayList<>();

        int lastIndex = history.size() - 1;
        for (int index = 0; index < history.size(); index++) {
            ChatMessage item = history.get(index);
            if (index == lastIndex && "user".equals(item.getRole())) {
                continue;
            }
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

    private ResponseEntity<Map<String, Object>> forwardResearchTask(
            HttpMethod method,
            String path,
            Map<String, Object> payload) {
        String url = PYTHON_SERVICE_URL + path;
        HttpEntity<?> entity = payload == null ? HttpEntity.EMPTY : new HttpEntity<>(payload);

        try {
            ResponseEntity<Map> response = restTemplate.exchange(url, method, entity, Map.class);
            return ResponseEntity.status(response.getStatusCode()).body(normalizeResearchTaskBody(response.getBody()));
        } catch (HttpStatusCodeException error) {
            return ResponseEntity.status(error.getStatusCode()).body(parsePythonErrorBody(error));
        }
    }

    private ResponseEntity<Map<String, Object>> forwardReadOnlyTrace(
            HttpMethod method,
            String path) {
        String url = PYTHON_SERVICE_URL + path;

        try {
            ResponseEntity<Map> response = restTemplate.exchange(url, method, HttpEntity.EMPTY, Map.class);
            return ResponseEntity.status(response.getStatusCode()).body(normalizeResearchTaskBody(response.getBody()));
        } catch (HttpStatusCodeException error) {
            return ResponseEntity.status(error.getStatusCode()).body(parsePythonErrorBody(error));
        }
    }

    private Map<String, Object> normalizeResearchTaskBody(Map<?, ?> body) {
        Map<String, Object> response = new LinkedHashMap<>();
        if (body != null) {
            for (Map.Entry<?, ?> entry : body.entrySet()) {
                response.put(String.valueOf(entry.getKey()), entry.getValue());
            }
        }
        if (!response.containsKey("status")) {
            response.put("status", "error");
            response.put("message", "Python service returned no response.");
        }
        return response;
    }

    private Map<String, Object> parsePythonErrorBody(HttpStatusCodeException error) {
        String rawBody = error.getResponseBodyAsString(StandardCharsets.UTF_8);
        if (rawBody != null && !rawBody.isBlank()) {
            try {
                return OBJECT_MAPPER.readValue(rawBody, new TypeReference<>() {
                });
            } catch (IOException ignored) {
                // Fall through to the generic error payload below.
            }
        }

        Map<String, Object> fallback = new LinkedHashMap<>();
        fallback.put("status", "error");
        fallback.put("message",
                (rawBody != null && !rawBody.isBlank()) ? rawBody : "Python service request failed.");
        return fallback;
    }
}
