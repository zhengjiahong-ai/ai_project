package com.ai.assistant.backend_java.service;

import java.util.Map;

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
@Service

public class AiService {

    @Autowired
    private RestTemplate restTemplate;

    /**
     * 修改点 1：
     * 在 Docker 中，localhost 意为容器自身。
     * 必须改为 docker-compose.yml 中定义的 Python 服务名：ai-service
     */
    @Value("${PYTHON_URL:http://localhost:8000/api}")
    private String PYTHON_SERVICE_URL;

    // 转发 PDF 分析请求
    public Map<String, Object> analyzePdf(MultipartFile file) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        // 保持不变，getResource() 是转发文件流的标准写法
        body.add("file", file.getResource()); 

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
        
        // 调用 Python main.py 里的 /api/analyze-pdf
        // 这里的地址会解析为 http://ai-service:8000/api/analyze-pdf
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/analyze-pdf", requestEntity, Map.class);
    }

    // 转发术语解释请求
    public Map<String, Object> explainTerm(Map<String, String> request) {
        // 直接转发 JSON 给 Python 容器
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/explain-term", request, Map.class);
    }

    // 转发聊天请求
    public Map<String, Object> chat(Map<String, Object> chatRequest) {
        // 直接转发聊天内容给 Python 容器
        return restTemplate.postForObject(PYTHON_SERVICE_URL + "/chat", chatRequest, Map.class);
    }
}