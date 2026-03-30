package com.ai.assistant.backend_java.controller;

import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.ai.assistant.backend_java.service.AiService;
@CrossOrigin(origins = "http://localhost:5173", allowCredentials = "true")
@RestController
@RequestMapping("/api") // 必须与 api.js 中的 API_BASE_URL 对应
public class AcademicController {

    @Autowired
    private AiService aiService;

    // 1. 处理 PDF 上传并调用 AI 分析
    @PostMapping("/upload")
    public Map<String, Object> uploadPdf(@RequestParam("file") MultipartFile file) {
        return aiService.analyzePdf(file);
    }

    // 2. 处理术语解释 (对应 main.py 的 /api/explain-term)
    @PostMapping("/explain")
    public Map<String, Object> explainTerm(@RequestBody Map<String, String> request) {
        return aiService.explainTerm(request);
    }

    // 3. 处理普通聊天对话
    @PostMapping("/chat")
    public Map<String, Object> chat(@RequestBody Map<String, Object> chatRequest) {
        return aiService.chat(chatRequest);
    }

    // 4. 处理引导式学习（苏格拉底式提问）
    @PostMapping("/socratic-questions")
    public Map<String, Object> socraticQuestions(@RequestBody Map<String, Object> request) {
        return aiService.socraticQuestions(request);
    }
}