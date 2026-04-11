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

    @Test
    void translatePageReturnsForwardedPayload() throws Exception {
        when(aiService.translatePage(eq(Map.of(
                "pdfId", "paper-1",
                "pageIndex", 0,
                "pageText", "source",
                "pageLayout", Map.of(
                        "viewport", Map.of("width", 600, "height", 800),
                        "blocks", List.of(Map.of("id", "block-1", "text", "source")),
                        "excludedZonesVersion", 1))))).thenReturn(Map.of(
                                "status", "success",
                                "pageIndex", 0,
                                "translatedText", "译文",
                                "renderMode", "overlay"));

        mockMvc.perform(post("/api/translate-page")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"pdfId":"paper-1","pageIndex":0,"pageText":"source","pageLayout":{"viewport":{"width":600,"height":800},"blocks":[{"id":"block-1","text":"source"}],"excludedZonesVersion":1}}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.pageIndex").value(0))
                .andExpect(jsonPath("$.translatedText").value("译文"))
                .andExpect(jsonPath("$.renderMode").value("overlay"));
    }

    @Test
    void backgroundKnowledgeReturnsForwardedPayload() throws Exception {
        when(aiService.backgroundKnowledge(eq(Map.of(
                "pdfId", "paper-1",
                "user_knowledge_level", "normal")))).thenReturn(Map.of(
                        "status", "success",
                        "pdfId", "paper-1",
                        "background_knowledge", List.of("RAG", "knowledge graph")));

        mockMvc.perform(post("/api/background-knowledge")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"pdfId":"paper-1","user_knowledge_level":"normal"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.pdfId").value("paper-1"))
                .andExpect(jsonPath("$.background_knowledge[0]").value("RAG"));
    }
}
