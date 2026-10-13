package com.ai.assistant.backend_java.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

import com.ai.assistant.backend_java.model.ChatMessage;
import com.ai.assistant.backend_java.repository.ChatMessageRepository;

@ExtendWith(MockitoExtension.class)
class PdfServiceTaskHistoryTest {
    @Mock RestTemplate restTemplate;
    @Mock ChatMessageRepository chatMessageRepository;
    @Mock TaskWorkspaceService taskWorkspaceService;
    @InjectMocks PdfService service;

    @BeforeEach
    void setup() {
        ReflectionTestUtils.setField(service, "PYTHON_SERVICE_URL", "http://test/api");
        when(restTemplate.postForObject(anyString(), any(), org.mockito.ArgumentMatchers.eq(Map.class)))
                .thenReturn(Map.of("status", "success", "message", "answer"));
    }

    @Test
    void preservesScopeFilteredHistoryForTaskRequests() {
        when(taskWorkspaceService.get("task-a")).thenReturn(Map.of("paperIds", List.of("a")));
        var history = new ArrayList<>(List.of(Map.of("role", "user", "content", "only paper A")));
        var request = new HashMap<String, Object>();
        request.put("taskId", "task-a");
        request.put("message", "continue");
        request.put("history", history);
        service.chat(request);
        assertSame(history, request.get("history"));
        verify(chatMessageRepository, never()).findByPdfIdOrderByTimestampAsc(anyString());
    }

    @Test
    void missingTaskHistoryDoesNotRecoverUnscopedDatabaseMessages() {
        when(taskWorkspaceService.get("task-a")).thenReturn(Map.of("paperIds", List.of("a")));
        var request = new HashMap<String, Object>();
        request.put("taskId", "task-a");
        request.put("message", "only A");
        service.chat(request);
        assertEquals(List.of(), request.get("history"));
        verify(chatMessageRepository, never()).findByPdfIdOrderByTimestampAsc(anyString());
    }

    @Test
    void legacyPaperRequestsStillRecoverDatabaseHistory() {
        ChatMessage previous = new ChatMessage();
        previous.setRole("ai");
        previous.setContent("previous answer");
        when(chatMessageRepository.findByPdfIdOrderByTimestampAsc("paper-a"))
                .thenReturn(List.of(previous));
        var request = new HashMap<String, Object>();
        request.put("pdfId", "paper-a");
        request.put("message", "continue");
        service.chat(request);
        assertEquals(List.of(Map.of("role", "assistant", "content", "previous answer")), request.get("history"));
    }

    @Test
    void rejectsOutsideTaskMaterialBeforeSavingOrCallingAi() {
        org.mockito.Mockito.reset(restTemplate);
        when(taskWorkspaceService.get("task-a")).thenReturn(Map.of("paperIds", List.of("a")));
        var request = new HashMap<String, Object>();
        request.put("taskId", "task-a");
        request.put("message", "read another task");
        request.put("allowedPaperIds", List.of("outside"));
        assertThrows(org.springframework.web.server.ResponseStatusException.class, () -> service.chat(request));
        verify(chatMessageRepository, never()).save(any());
        verify(restTemplate, never()).postForObject(anyString(), any(), org.mockito.ArgumentMatchers.eq(Map.class));
    }
}
