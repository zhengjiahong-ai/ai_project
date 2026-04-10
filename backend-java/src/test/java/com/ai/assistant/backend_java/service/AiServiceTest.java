package com.ai.assistant.backend_java.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

import com.ai.assistant.backend_java.model.ChatMessage;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.ChatMessageRepository;
import com.ai.assistant.backend_java.repository.PaperRepository;

@ExtendWith(MockitoExtension.class)
class AiServiceTest {

    @Mock
    private RestTemplate restTemplate;

    @Mock
    private PaperRepository paperRepository;

    @Mock
    private ChatMessageRepository chatMessageRepository;

    @InjectMocks
    private AiService aiService;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(aiService, "PYTHON_SERVICE_URL", "http://python/api");
    }

    @Test
    void analyzePdfPersistsResolvedPdfId() {
        MockMultipartFile file = new MockMultipartFile("file", "Paper Name.pdf", "application/pdf", "pdf".getBytes());
        Map<String, Object> pythonResponse = new HashMap<>();
        pythonResponse.put("status", "success");
        pythonResponse.put("pdfId", "paper_name.pdf");

        when(restTemplate.postForObject(eq("http://python/api/analyze-pdf"), any(), eq(Map.class)))
                .thenReturn(pythonResponse);

        Map<String, Object> response = aiService.analyzePdf(file);

        ArgumentCaptor<Paper> captor = ArgumentCaptor.forClass(Paper.class);
        verify(paperRepository).save(captor.capture());
        assertEquals("paper_name.pdf", captor.getValue().getId());
        assertEquals("paper_name.pdf", response.get("pdfId"));
    }

    @Test
    void getChatHistoryReturnsOrderedMessages() {
        ChatMessage first = new ChatMessage();
        first.setId(1L);
        first.setPdfId("session-1");
        first.setRole("user");
        first.setContent("hello");
        first.setTimestamp(LocalDateTime.of(2026, 4, 4, 10, 0));

        ChatMessage second = new ChatMessage();
        second.setId(2L);
        second.setPdfId("session-1");
        second.setRole("ai");
        second.setContent("world");
        second.setTimestamp(LocalDateTime.of(2026, 4, 4, 10, 1));

        when(chatMessageRepository.findByPdfIdOrderByTimestampAsc("session-1"))
                .thenReturn(List.of(first, second));

        Map<String, Object> response = aiService.getChatHistory("session-1");

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) response.get("messages");
        assertEquals("success", response.get("status"));
        assertEquals(2, response.get("messageCount"));
        assertEquals("assistant", messages.get(1).get("role"));
        assertEquals("hello", messages.get(0).get("content"));
        assertEquals("world", messages.get(1).get("content"));
    }

    @Test
    void chatBuildsAssistantHistoryWithoutDuplicatingLatestUserMessage() {
        ChatMessage existingUser = new ChatMessage();
        existingUser.setRole("user");
        existingUser.setContent("older question");

        ChatMessage existingAi = new ChatMessage();
        existingAi.setRole("ai");
        existingAi.setContent("older answer");

        ChatMessage latestUser = new ChatMessage();
        latestUser.setRole("user");
        latestUser.setContent("new question");

        when(chatMessageRepository.findByPdfIdOrderByTimestampAsc("paper-1"))
                .thenReturn(List.of(existingUser, existingAi, latestUser));

        doAnswer(invocation -> invocation.getArgument(0)).when(chatMessageRepository).save(any(ChatMessage.class));

        when(restTemplate.postForObject(eq("http://python/api/chat"), any(), eq(Map.class)))
                .thenReturn(Map.of("status", "success", "message", "reply"));

        Map<String, Object> request = new HashMap<>();
        request.put("pdfId", "paper-1");
        request.put("message", "new question");

        aiService.chat(request);

        @SuppressWarnings("unchecked")
        List<Map<String, String>> history = (List<Map<String, String>>) request.get("history");
        assertEquals(2, history.size());
        assertEquals("assistant", history.get(1).get("role"));
        assertEquals("older answer", history.get(1).get("content"));
    }

    @Test
    void criticalReadingWrapsPythonResponse() {
        when(restTemplate.postForObject(eq("http://python/api/deep-analysis"), any(Map.class), eq(Map.class)))
                .thenReturn(Map.of("status", "success", "critical_analysis", "done"));

        Map<String, Object> response = aiService.criticalReading("paper-1");

        assertEquals("success", response.get("status"));
        assertEquals("paper-1", response.get("pdfId"));
        assertNotNull(response.get("analysis"));
    }

    @Test
    void translatePageForwardsRequestToPythonService() {
        Map<String, Object> request = new HashMap<>();
        request.put("pdfId", "paper-1");
        request.put("pageIndex", 2);
        request.put("pageText", "source text");
        request.put("pageLayout", Map.of(
                "viewport", Map.of("width", 600, "height", 800),
                "blocks", List.of(Map.of("id", "block-1", "text", "source text")),
                "excludedZonesVersion", 1));

        when(restTemplate.postForObject(eq("http://python/api/translate-page"), eq(request), eq(Map.class)))
                .thenReturn(Map.of(
                        "status", "success",
                        "pageIndex", 2,
                        "translatedText", "译文",
                        "renderMode", "overlay",
                        "translatedBlocks", List.of(Map.of("id", "block-1", "translatedText", "译文"))));

        Map<String, Object> response = aiService.translatePage(request);

        assertEquals("success", response.get("status"));
        assertEquals(2, response.get("pageIndex"));
        assertEquals("译文", response.get("translatedText"));
        assertEquals("overlay", response.get("renderMode"));
    }
}
