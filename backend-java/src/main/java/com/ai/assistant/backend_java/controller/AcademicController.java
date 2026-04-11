package com.ai.assistant.backend_java.controller;

import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
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
}
