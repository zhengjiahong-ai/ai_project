package com.ai.assistant.backend_java.service;

import java.util.Map;
import java.util.List;
import java.util.HashMap;
import java.util.ArrayList;

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

import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.model.ChatMessage;
import com.ai.assistant.backend_java.repository.PaperRepository;
import com.ai.assistant.backend_java.repository.ChatMessageRepository;

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

    // 转发 PDF 分析请求并持久化论文信息
    public Map<String, Object> analyzePdf(MultipartFile file) {
        String fileName = file.getOriginalFilename();
        
        // 持久化论文元数据
        Paper paper = new Paper();
        paper.setId(fileName); // 暂时使用文件名作为唯一标识
        paper.setFileName(fileName);
        paperRepository.save(paper);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", file.getResource()); 

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
        
        @SuppressWarnings("unchecked")
        Map<String, Object> response = restTemplate.postForObject(PYTHON_SERVICE_URL + "/analyze-pdf", requestEntity, Map.class);
        
        if (response != null && "success".equals(response.get("status"))) {
            response.put("pdfId", fileName);
        }
        
        return response;
    }

    // 转发术语解释请求
    public Map<String, Object> explainTerm(Map<String, String> request) {
        Map<String, String> convertedRequest = new HashMap<>();
        if (request.containsKey("text")) {
            convertedRequest.put("term", request.get("text"));
        }
        
        StringBuilder contextBuilder = new StringBuilder();
        if (request.containsKey("pdfId")) {
            contextBuilder.append("PDF ID: " + request.get("pdfId") + ". ");
        }
        if (request.containsKey("pageNumber")) {
            contextBuilder.append("Page Number: " + request.get("pageNumber") + ". ");
        }
        if (request.containsKey("context")) {
            contextBuilder.append(request.get("context"));
        }
        convertedRequest.put("context", contextBuilder.toString());
        
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/explain-term", convertedRequest, Map.class);
    }

    // 转发聊天请求并实现上下文持久化
    public Map<String, Object> chat(Map<String, Object> chatRequest) {
        String message = (String) chatRequest.get("message");
        String pdfId = (String) chatRequest.get("pdfId");

        // 1. 保存用户消息
        if (pdfId != null) {
            ChatMessage userMsg = new ChatMessage();
            userMsg.setPdfId(pdfId);
            userMsg.setRole("user");
            userMsg.setContent(message);
            chatMessageRepository.save(userMsg);
            
            // 2. 获取该 PDF 的历史记录并传给 Python (可选：这里可以做历史窗口剪裁)
            List<ChatMessage> history = chatMessageRepository.findByPdfIdOrderByTimestampAsc(pdfId);
            List<Map<String, String>> historyList = new ArrayList<>();
            for (ChatMessage m : history) {
                Map<String, String> mData = new HashMap<>();
                mData.put("role", m.getRole());
                mData.put("content", m.getContent());
                historyList.add(mData);
            }
            chatRequest.put("history", historyList);
        }

        // 3. 转发给 Python
        @SuppressWarnings("unchecked")
        Map<String, Object> response = restTemplate.postForObject(PYTHON_SERVICE_URL + "/chat", chatRequest, Map.class);

        // 4. 保存 AI 响应
        if (response != null && "success".equals(response.get("status")) && pdfId != null) {
            String aiReply = (String) response.get("message");
            ChatMessage aiMsg = new ChatMessage();
            aiMsg.setPdfId(pdfId);
            aiMsg.setRole("ai");
            aiMsg.setContent(aiReply);
            chatMessageRepository.save(aiMsg);
        }

        return response;
    }

    public Map<String, Object> socraticQuestions(Map<String, Object> request) {
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/socratic-questions", request, Map.class);
    }
}