package com.ai.assistant.backend_java.controller;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import com.ai.assistant.backend_java.service.AiService;

@WebMvcTest(AcademicController.class)
class AcademicControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AiService aiService;

    @Test
    void getChatHistoryReturnsHistoryPayload() throws Exception {
        when(aiService.getChatHistory("session-1")).thenReturn(Map.of(
                "status", "success",
                "sessionId", "session-1",
                "messageCount", 1,
                "messages", List.of(Map.of("role", "user", "content", "hello"))));

        mockMvc.perform(get("/api/chat/history/session-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessionId").value("session-1"))
                .andExpect(jsonPath("$.messages[0].content").value("hello"));
    }

    @Test
    void criticalReadingReturnsWrappedAnalysis() throws Exception {
        when(aiService.criticalReading(eq("paper-1"))).thenReturn(Map.of(
                "status", "success",
                "pdfId", "paper-1",
                "analysis", Map.of("critical_analysis", "done")));

        mockMvc.perform(post("/api/critical-reading/paper-1").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.pdfId").value("paper-1"))
                .andExpect(jsonPath("$.analysis.critical_analysis").value("done"));
    }
}
