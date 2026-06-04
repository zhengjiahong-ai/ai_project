package com.ai.assistant.backend_java.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.LocalDateTime;
import java.nio.charset.StandardCharsets;
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
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.HttpClientErrorException;
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
    void explainTermForwardsSelectionPayloadWithPdfContext() {
        when(restTemplate.postForObject(eq("http://python/api/explain-term"), any(Map.class), eq(Map.class)))
                .thenReturn(Map.of("status", "success", "explanation", "解释"));

        Map<String, Object> request = new HashMap<>();
        request.put("text", "contrastive loss");
        request.put("pdfId", "paper-1");
        request.put("pageNumber", 4);
        request.put("context", "This page introduces contrastive learning.");

        aiService.explainTerm(request);

        @SuppressWarnings({"rawtypes", "unchecked"})
        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(restTemplate).postForObject(eq("http://python/api/explain-term"), captor.capture(), eq(Map.class));

        Map<String, Object> forwarded = captor.getValue();
        assertEquals("contrastive loss", forwarded.get("term"));
        assertEquals("paper-1", forwarded.get("pdfId"));
        assertEquals(4, forwarded.get("pageNumber"));
        assertEquals("This page introduces contrastive learning.", forwarded.get("context"));
    }

    @Test
    void explainTermKeepsLegacyTermContextPayload() {
        when(restTemplate.postForObject(eq("http://python/api/explain-term"), any(Map.class), eq(Map.class)))
                .thenReturn(Map.of("status", "success", "explanation", "解释"));

        Map<String, Object> request = new HashMap<>();
        request.put("term", "attention");
        request.put("context", "Legacy context");

        aiService.explainTerm(request);

        @SuppressWarnings({"rawtypes", "unchecked"})
        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(restTemplate).postForObject(eq("http://python/api/explain-term"), captor.capture(), eq(Map.class));

        Map<String, Object> forwarded = captor.getValue();
        assertEquals("attention", forwarded.get("term"));
        assertEquals("Legacy context", forwarded.get("context"));
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
                .thenReturn(Map.of(
                        "status", "success",
                        "critical_analysis", "done",
                        "claims", List.of(Map.of(
                                "id", "claim-1",
                                "claim", "作者提出新的检索排序方法。",
                                "supportLevel", "SUPPORTED"))));

        Map<String, Object> response = aiService.criticalReading("paper-1");

        assertEquals("success", response.get("status"));
        assertEquals("paper-1", response.get("pdfId"));
        @SuppressWarnings("unchecked")
        Map<String, Object> analysis = (Map<String, Object>) response.get("analysis");
        assertNotNull(analysis);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> claims = (List<Map<String, Object>>) analysis.get("claims");
        assertEquals("SUPPORTED", claims.get(0).get("supportLevel"));
    }

    @Test
    void criticalReadingWrapsPythonIndexErrorResponse() {
        String errorBody = """
                {"status":"error","errorCode":"paper_not_indexed","message":"当前论文尚未完成全文索引，请重新上传或重新解析后再试。"}
                """;
        when(restTemplate.postForObject(eq("http://python/api/deep-analysis"), any(Map.class), eq(Map.class)))
                .thenThrow(new HttpClientErrorException(
                        HttpStatus.CONFLICT,
                        "Conflict",
                        errorBody.getBytes(StandardCharsets.UTF_8),
                        StandardCharsets.UTF_8));

        Map<String, Object> response = aiService.criticalReading("paper-1");

        assertEquals("error", response.get("status"));
        assertEquals("paper_not_indexed", response.get("errorCode"));
        assertEquals("paper-1", response.get("pdfId"));
        assertEquals("当前论文尚未完成全文索引，请重新上传或重新解析后再试。", response.get("message"));
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

    @Test
    void backgroundKnowledgeForwardsRequestToPythonService() {
        Map<String, Object> request = new HashMap<>();
        request.put("pdfId", "paper-1");
        request.put("user_knowledge_level", "normal");

        when(restTemplate.postForObject(eq("http://python/api/background-knowledge"), eq(request), eq(Map.class)))
                .thenReturn(Map.of(
                        "status", "success",
                        "pdfId", "paper-1",
                        "background_knowledge", List.of("RAG", "knowledge graph")));

        Map<String, Object> response = aiService.backgroundKnowledge(request);

        assertEquals("success", response.get("status"));
        assertEquals("paper-1", response.get("pdfId"));
    }

    @Test
    void createResearchTaskForwardsRequestToPythonService() {
        Map<String, Object> request = new HashMap<>();
        request.put("question", "研究问题");
        request.put("pdfId", "paper-1");
        request.put("paperSkeleton", Map.of("abstract", "summary"));

        when(restTemplate.exchange(
                eq("http://python/api/research-tasks"),
                eq(HttpMethod.POST),
                any(HttpEntity.class),
                eq(Map.class))).thenReturn(ResponseEntity.ok(Map.of(
                        "status", "success",
                        "task", Map.of(
                                "taskId", "task-1",
                                "status", "pending",
                                "stage", "planning",
                                "progress", 0.0,
                                "question", "研究问题",
                                "pdfId", "paper-1",
                                "plan", List.of(),
                                "findings", List.of(),
                                "report", "",
                                "error", ""))));

        ResponseEntity<Map<String, Object>> response = aiService.createResearchTask(request);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("success", response.getBody().get("status"));
    }

    @Test
    void getResearchTaskForwardsGetRequestToPythonService() {
        when(restTemplate.exchange(
                eq("http://python/api/research-tasks/task-1"),
                eq(HttpMethod.GET),
                eq(HttpEntity.EMPTY),
                eq(Map.class))).thenReturn(ResponseEntity.ok(Map.of(
                        "status", "success",
                        "task", Map.of(
                                "taskId", "task-1",
                                "status", "running",
                                "stage", "retrieving",
                                "progress", 0.4,
                                "question", "研究问题",
                                "pdfId", "paper-1",
                                "plan", List.of("Q1"),
                                "findings", List.of(),
                                "report", "",
                                "error", ""))));

        ResponseEntity<Map<String, Object>> response = aiService.getResearchTask("task-1");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        @SuppressWarnings("unchecked")
        Map<String, Object> task = (Map<String, Object>) response.getBody().get("task");
        assertEquals("running", task.get("status"));
    }

    @Test
    void getLatestResearchTaskForwardsGetRequestWithEncodedPdfId() {
        when(restTemplate.exchange(
                eq("http://python/api/research-tasks/latest?pdfId=paper%201"),
                eq(HttpMethod.GET),
                eq(HttpEntity.EMPTY),
                eq(Map.class))).thenReturn(ResponseEntity.ok(Map.of(
                        "status", "success",
                        "task", Map.of(
                                "taskId", "task-latest",
                                "status", "succeeded",
                                "stage", "done",
                                "progress", 1.0,
                                "question", "最近任务",
                                "pdfId", "paper 1",
                                "plan", List.of("Q1"),
                                "findings", List.of(),
                                "report", "report",
                                "error", ""))));

        ResponseEntity<Map<String, Object>> response = aiService.getLatestResearchTask("paper 1");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        @SuppressWarnings("unchecked")
        Map<String, Object> task = (Map<String, Object>) response.getBody().get("task");
        assertEquals("task-latest", task.get("taskId"));
    }

    @Test
    void getLatestResearchTaskPropagatesPythonNotFoundStatusAndMessage() {
        HttpClientErrorException error = HttpClientErrorException.create(
                HttpStatus.NOT_FOUND,
                "Not Found",
                HttpHeaders.EMPTY,
                "{\"status\":\"error\",\"message\":\"Research task not found.\"}".getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8);

        when(restTemplate.exchange(
                eq("http://python/api/research-tasks/latest?pdfId=missing-paper"),
                eq(HttpMethod.GET),
                eq(HttpEntity.EMPTY),
                eq(Map.class))).thenThrow(error);

        ResponseEntity<Map<String, Object>> response = aiService.getLatestResearchTask("missing-paper");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("error", response.getBody().get("status"));
        assertEquals("Research task not found.", response.getBody().get("message"));
    }

    @Test
    void cancelResearchTaskPropagatesPythonNotFoundStatusAndMessage() {
        HttpClientErrorException error = HttpClientErrorException.create(
                HttpStatus.NOT_FOUND,
                "Not Found",
                HttpHeaders.EMPTY,
                "{\"status\":\"error\",\"message\":\"Research task not found.\"}".getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8);

        when(restTemplate.exchange(
                eq("http://python/api/research-tasks/task-missing/cancel"),
                eq(HttpMethod.POST),
                eq(HttpEntity.EMPTY),
                eq(Map.class))).thenThrow(error);

        ResponseEntity<Map<String, Object>> response = aiService.cancelResearchTask("task-missing");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("error", response.getBody().get("status"));
        assertEquals("Research task not found.", response.getBody().get("message"));
    }

    @Test
    void getTraceForwardsGetRequestToPythonService() {
        when(restTemplate.exchange(
                eq("http://python/api/traces/trace-1"),
                eq(HttpMethod.GET),
                eq(HttpEntity.EMPTY),
                eq(Map.class))).thenReturn(ResponseEntity.ok(Map.of(
                        "status", "success",
                        "trace", Map.of(
                                "traceId", "trace-1",
                                "taskType", "deep_research",
                                "status", "success",
                                "counters", Map.of("llmCalls", 1),
                                "steps", List.of(Map.of("name", "research_build_plan"))))));

        ResponseEntity<Map<String, Object>> response = aiService.getTrace("trace-1");

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        @SuppressWarnings("unchecked")
        Map<String, Object> trace = (Map<String, Object>) response.getBody().get("trace");
        assertEquals("trace-1", trace.get("traceId"));
    }

    @Test
    void getTracePropagatesPythonNotFoundStatusAndMessage() {
        HttpClientErrorException error = HttpClientErrorException.create(
                HttpStatus.NOT_FOUND,
                "Not Found",
                HttpHeaders.EMPTY,
                "{\"status\":\"error\",\"message\":\"Trace not found.\"}".getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8);

        when(restTemplate.exchange(
                eq("http://python/api/traces/missing-trace"),
                eq(HttpMethod.GET),
                eq(HttpEntity.EMPTY),
                eq(Map.class))).thenThrow(error);

        ResponseEntity<Map<String, Object>> response = aiService.getTrace("missing-trace");

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("error", response.getBody().get("status"));
        assertEquals("Trace not found.", response.getBody().get("message"));
    }
}
