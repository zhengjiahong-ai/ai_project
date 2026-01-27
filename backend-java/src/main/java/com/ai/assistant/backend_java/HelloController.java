package com.ai.assistant.backend_java;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

@RestController
public class HelloController {

    @GetMapping("/ask-ai")
    public String askAi() {
        // 这里的 ai-service 是你在 docker-compose 里定义的容器名
        String pythonUrl = "http://ai-service:8000/"; 
        RestTemplate restTemplate = new RestTemplate();
        String result = restTemplate.getForObject(pythonUrl, String.class);
        return "Java 后端收到请求，转发 Python AI 的结果是: " + result;
    }
}