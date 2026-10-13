package com.ai.assistant.backend_java.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
class TaskLearningControllerTest {
    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper mapper;
    @Autowired private TaskWorkspaceService tasks;
    @Autowired private TaskWorkspaceRepository repository;
    @MockBean private RestTemplate upstream;
    private Map<String, Object> task;

    @BeforeEach
    void setup() {
        reset(upstream);
        repository.deleteAll();
        task = tasks.create(Map.of("id", "learning-task", "paperIds", List.of("A", "B"),
                "focusedPaperId", "A", "notes", List.of(Map.of("content", "personal note"))));
    }

    @Test
    void startsAndPersistsActivityWithFixedPaperAndNewTaskRevision() throws Exception {
        when(upstream.postForObject(eq("http://localhost:8000/api/adaptive-learning/start"), any(), eq(Map.class)))
                .thenReturn(result(state(0)));
        mvc.perform(post("/api/task-workspaces/learning-task/learning/start")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(Map.of(
                        "pdfId", "A", "mode", "read", "expectedTaskRevision", task.get("revision")))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.revision").value(1))
                .andExpect(jsonPath("$.task.activeActivity.activityId").value("activity-A"))
                .andExpect(jsonPath("$.task.activeActivity.snapshot.primaryPaperId").value("A"))
                .andExpect(jsonPath("$.result.state.revision").value(0));
        org.junit.jupiter.api.Assertions.assertEquals("A", ((Map<?, ?>) tasks.get("learning-task").get("activeActivity")).get("pdfId"));
    }

    @Test
    void rejectsOtherTaskPaperStaleTaskVersionAndReplacementOfUnfinishedActivity() throws Exception {
        mvc.perform(post("/api/task-workspaces/learning-task/learning/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("pdfId", "outside", "expectedTaskRevision", task.get("revision")))))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/api/task-workspaces/learning-task/learning/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("pdfId", "A", "expectedTaskRevision", 99))))
                .andExpect(status().isConflict());
        task.put("activeActivity", state(0));
        task = tasks.update("learning-task", task);
        mvc.perform(post("/api/task-workspaces/learning-task/learning/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("pdfId", "B", "expectedTaskRevision", task.get("revision")))))
                .andExpect(status().isConflict());
        verifyNoInteractions(upstream);
    }

    @Test
    void ignoresForgedClientStateAndReadingFocusAndUsesServerActivity() throws Exception {
        task.put("activeActivity", state(2));
        task.put("focusedPaperId", "B");
        task = tasks.update("learning-task", task);
        when(upstream.postForObject(eq("http://localhost:8000/api/adaptive-learning/action"), any(), eq(Map.class)))
                .thenAnswer(invocation -> {
                    Map<?, ?> body = invocation.getArgument(1);
                    Map<?, ?> authority = (Map<?, ?>) body.get("state");
                    org.junit.jupiter.api.Assertions.assertEquals("A", authority.get("pdfId"));
                    org.junit.jupiter.api.Assertions.assertEquals("original question", authority.get("currentConceptId"));
                    org.junit.jupiter.api.Assertions.assertEquals(2, body.get("expectedRevision"));
                    return result(state(3));
                });
        Map<String, Object> action = action(2);
        action.put("state", Map.of("pdfId", "outside", "currentConceptId", "forged"));
        mvc.perform(post("/api/task-workspaces/learning-task/learning/action").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(action)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.focusedPaperId").value("B"))
                .andExpect(jsonPath("$.task.activeActivity.pdfId").value("A"))
                .andExpect(jsonPath("$.task.activeActivity.revision").value(3));
    }

    @Test
    void providerResultCannotOverwriteConcurrentChatOrNotes() throws Exception {
        task.put("activeActivity", state(0));
        task = tasks.update("learning-task", task);
        when(upstream.postForObject(eq("http://localhost:8000/api/adaptive-learning/action"), any(), eq(Map.class)))
                .thenAnswer(invocation -> {
                    Map<String, Object> concurrent = tasks.get("learning-task");
                    concurrent.put("messages", List.of(Map.of("content", "concurrent answer")));
                    concurrent.put("notes", List.of(Map.of("content", "concurrent note")));
                    tasks.update("learning-task", concurrent);
                    return result(state(1));
                });
        mvc.perform(post("/api/task-workspaces/learning-task/learning/action").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(action(0))))
                .andExpect(status().isConflict());
        Map<String, Object> persisted = tasks.get("learning-task");
        org.junit.jupiter.api.Assertions.assertEquals(List.of(Map.of("content", "concurrent answer")), persisted.get("messages"));
        org.junit.jupiter.api.Assertions.assertEquals(List.of(Map.of("content", "concurrent note")), persisted.get("notes"));
        org.junit.jupiter.api.Assertions.assertEquals(0, ((Map<?, ?>) persisted.get("activeActivity")).get("revision"));
    }

    @Test
    void staleActivityAndProviderFailurePreserveSavedState() throws Exception {
        task.put("activeActivity", state(2));
        task = tasks.update("learning-task", task);
        mvc.perform(post("/api/task-workspaces/learning-task/learning/action").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(action(1))))
                .andExpect(status().isConflict());
        verifyNoInteractions(upstream);
        when(upstream.postForObject(eq("http://localhost:8000/api/adaptive-learning/action"), any(), eq(Map.class)))
                .thenThrow(new ResourceAccessException("private provider error"));
        mvc.perform(post("/api/task-workspaces/learning-task/learning/action").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(action(2))))
                .andExpect(status().isServiceUnavailable());
        org.junit.jupiter.api.Assertions.assertEquals(task, tasks.get("learning-task"));
    }

    @Test
    void rejectsUpstreamStateChangingActivityPaperOrVersion() throws Exception {
        Map<String, Object> invalid = state(0);
        invalid.put("pdfId", "B");
        when(upstream.postForObject(eq("http://localhost:8000/api/adaptive-learning/start"), any(), eq(Map.class)))
                .thenReturn(result(invalid));
        mvc.perform(post("/api/task-workspaces/learning-task/learning/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("pdfId", "A", "expectedTaskRevision", task.get("revision")))))
                .andExpect(status().isBadGateway());
        org.junit.jupiter.api.Assertions.assertEquals(task, tasks.get("learning-task"));
    }

    private Map<String, Object> action(int revision) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("activityId", "activity-A");
        value.put("expectedRevision", revision);
        value.put("expectedTaskRevision", task.get("revision"));
        value.put("action", "answer");
        value.put("text", "my answer");
        return value;
    }

    private Map<String, Object> state(int revision) {
        return new LinkedHashMap<>(Map.of("schemaVersion", 1, "taskId", "learning-task", "pdfId", "A",
                "activityId", "activity-A", "revision", revision, "status", "active", "currentConceptId", "original question"));
    }

    private Map<String, Object> result(Map<String, Object> state) {
        return Map.of("state", state, "message", "learning feedback", "sources", List.of());
    }
}
