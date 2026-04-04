package com.ai.assistant.backend_java.service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import com.ai.assistant.backend_java.model.ChatMessage;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.ChatMessageRepository;
import com.ai.assistant.backend_java.repository.PaperRepository;

@Service
public class AiService {

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
        body.add("file", file.getResource());

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

    public Map<String, Object> explainTerm(Map<String, String> request) {
        Map<String, String> convertedRequest = new HashMap<>();
        if (request.containsKey("text")) {
            convertedRequest.put("term", request.get("text"));
        }

        StringBuilder contextBuilder = new StringBuilder();
        if (request.containsKey("pdfId")) {
            contextBuilder.append("PDF ID: ").append(request.get("pdfId")).append(". ");
        }
        if (request.containsKey("pageNumber")) {
            contextBuilder.append("Page Number: ").append(request.get("pageNumber")).append(". ");
        }
        if (request.containsKey("context")) {
            contextBuilder.append(request.get("context"));
        }
        convertedRequest.put("context", contextBuilder.toString());

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

    public Map<String, Object> getChatHistory(String sessionId) {
        List<ChatMessage> history = chatMessageRepository.findByPdfIdOrderByTimestampAsc(sessionId);
        List<Map<String, Object>> messages = new ArrayList<>();

        for (ChatMessage message : history) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", message.getId());
            item.put("role", message.getRole());
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

        @SuppressWarnings("unchecked")
        Map<String, Object> pythonResponse = restTemplate.postForObject(
                PYTHON_SERVICE_URL + "/deep-analysis",
                payload,
                Map.class);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", pythonResponse != null ? pythonResponse.getOrDefault("status", "error") : "error");
        response.put("pdfId", pdfId);
        response.put("analysis", pythonResponse);

        if (pythonResponse == null) {
            response.put("message", "Python service returned no response.");
        } else if (pythonResponse.containsKey("message")) {
            response.put("message", pythonResponse.get("message"));
        }

        return response;
    }

    public Map<String, Object> socraticQuestions(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/socratic-questions", request, Map.class);
    }

    private List<Map<String, String>> buildHistoryPayload(String pdfId) {
        List<ChatMessage> history = chatMessageRepository.findByPdfIdOrderByTimestampAsc(pdfId);
        List<Map<String, String>> historyList = new ArrayList<>();

        for (ChatMessage item : history) {
            Map<String, String> message = new HashMap<>();
            message.put("role", item.getRole());
            message.put("content", item.getContent());
            historyList.add(message);
        }

        return historyList;
    }
}
