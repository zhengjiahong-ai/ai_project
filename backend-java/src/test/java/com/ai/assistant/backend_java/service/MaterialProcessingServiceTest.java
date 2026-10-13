package com.ai.assistant.backend_java.service;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.PaperRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.web.client.RestTemplate;

class MaterialProcessingServiceTest {
    PaperRepository papers;
    RestTemplate http;
    MaterialProcessingService service;
    Map<String, Paper> database;
    @BeforeEach void setup() {
        papers = mock(PaperRepository.class); http = mock(RestTemplate.class);
        database = new ConcurrentHashMap<>();
        when(papers.findById(anyString())).thenAnswer(call -> Optional.ofNullable(database.get(call.getArgument(0))));
        when(papers.saveAndFlush(any(Paper.class))).thenAnswer(call -> {
            Paper paper = call.getArgument(0); database.put(paper.getId(), paper); return paper;
        });
        service = new MaterialProcessingService(papers, new ObjectMapper(), http, "http://test/api");
    }
    @AfterEach void cleanup() { service.close(); }
    MockMultipartFile pdf() { return new MockMultipartFile("file", "paper.pdf", "application/pdf", "%PDF-test".getBytes()); }

    @Test void persistsFileBeforeParsingReturnsAndDeduplicatesPendingUploads() throws Exception {
        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        when(http.postForObject(eq("http://test/api/parse-pdf"), any(), eq(Map.class))).thenAnswer(call -> {
            assertEquals(1, database.size()); assertNotNull(database.values().iterator().next().getPdfBytes());
            entered.countDown(); assertTrue(release.await(3, TimeUnit.SECONDS));
            return Map.of("status", "success", "pdfId", "normalized", "ragIndexed", true, "aiAnalysisStatus", "not_requested");
        });
        Map<String, Object> result = service.upload(pdf());
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        assertEquals(true, result.get("readingReady")); assertEquals(false, result.get("questionReady"));
        assertEquals(result.get("pdfId"), service.upload(pdf()).get("pdfId"));
        assertEquals(result.get("pdfId"), service.request((String) result.get("pdfId"), false).get("pdfId"));
        verify(http, times(1)).postForObject(anyString(), any(), eq(Map.class));
        release.countDown();
        awaitState((String) result.get("pdfId"), "ready");
        assertEquals(true, service.status((String) result.get("pdfId")).get("questionReady"));
        assertEquals("not_requested", service.status((String) result.get("pdfId")).get("aiAnalysisStatus"));
    }

    @Test void failedParsingKeepsFileAndExplicitRetrySucceeds() throws Exception {
        when(http.postForObject(anyString(), any(), eq(Map.class))).thenThrow(new IllegalStateException("provider detail"))
                .thenReturn(Map.of("status", "success", "ragIndexed", true));
        String id = (String) service.upload(pdf()).get("pdfId");
        awaitState(id, "failed");
        assertEquals(true, service.status(id).get("readingReady"));
        assertFalse(service.status(id).get("processingError").toString().contains("provider detail"));
        service.request(id, false); awaitState(id, "ready");
        verify(http, times(2)).postForObject(eq("http://test/api/parse-pdf"), any(), eq(Map.class));
    }

    @Test void restartMarksOutstandingWorkWithoutReplayingModelAndPreservesFile() {
        Paper paper = new Paper(); paper.setId("a"); paper.setPdfBytes("%PDF-test".getBytes());
        paper.setProcessingStatus("ready"); paper.setAiAnalysisStatus("running"); paper.setProcessingAttemptId("old");
        paper.setAnalysisJson("{\"ragIndexed\":true}"); database.put("a", paper);
        when(papers.findByProcessingStatusInOrAiAnalysisStatusIn(any(), any())).thenReturn(List.of(paper));
        service.recoverInterrupted();
        assertEquals("interrupted", service.status("a").get("aiAnalysisStatus"));
        assertEquals(true, service.status("a").get("readingReady"));
        assertEquals(true, service.status("a").get("questionReady"));
        assertNotEquals("old", paper.getProcessingAttemptId()); verifyNoInteractions(http);
    }

    @Test void invalidFileIsRejectedBeforePersistenceOrProcessing() {
        assertThrows(org.springframework.web.server.ResponseStatusException.class, () -> service.upload(
                new MockMultipartFile("file", "fake.pdf", "application/pdf", "invalid".getBytes())));
        assertTrue(database.isEmpty()); verifyNoInteractions(http);
    }

    @Test void optionalOverviewIsNotAutomaticAndFailurePreservesParsedEvidence() throws Exception {
        when(http.postForObject(eq("http://test/api/parse-pdf"), any(), eq(Map.class)))
                .thenReturn(Map.of("status", "success", "ragIndexed", true, "title", "Original title"));
        String id = (String) service.upload(pdf()).get("pdfId"); awaitState(id, "ready");
        verify(http, never()).postForObject(eq("http://test/api/analyze-pdf"), any(), eq(Map.class));
        when(http.postForObject(eq("http://test/api/analyze-pdf"), any(), eq(Map.class)))
                .thenThrow(new IllegalStateException("model unavailable"));
        service.request(id, true);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (!"failed".equals(service.status(id).get("aiAnalysisStatus")) && System.nanoTime() < deadline) Thread.sleep(10);
        assertEquals("failed", service.status(id).get("aiAnalysisStatus"));
        assertEquals(true, service.status(id).get("questionReady"));
        assertEquals("Original title", service.status(id).get("title"));
    }
    void awaitState(String id, String state) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (System.nanoTime() < deadline) {
            if (state.equals(service.status(id).get("processingStatus"))) return;
            Thread.sleep(10);
        }
        fail("Did not reach " + state + ": " + service.status(id));
    }
}
