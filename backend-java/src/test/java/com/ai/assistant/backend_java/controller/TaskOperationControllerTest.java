package com.ai.assistant.backend_java.controller;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;
import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
class TaskOperationControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired TaskWorkspaceService tasks;
    @Autowired TaskWorkspaceRepository repository;
    @Autowired com.ai.assistant.backend_java.repository.PaperRepository materials;
    @MockBean RestTemplate upstream;
    Map<String,Object> task;
    String root = "/api/task-workspaces/operation-task";
    @BeforeEach void setup() {
        reset(upstream); repository.deleteAll(); materials.deleteAll();
        task = tasks.create(Map.of("id","operation-task","paperIds",List.of("A","B")));
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r1")),eq(Map.class))).thenThrow(new HttpClientErrorException(HttpStatus.NOT_FOUND));
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/operation-task")),eq(List.class))).thenReturn(List.of());
    }
    Map<String,Object> input() { return Map.of("pdfId","A","mode","read","goal","学习", "expectedTaskRevision",task.get("revision")); }
    @Test void commonLearningResultKeepsQuestionOnceAndSavesFullArtifactAtomically() throws Exception {
        Map<String, Object> operation = new LinkedHashMap<>(receipt("succeeded"));
        Map<String, Object> result = new LinkedHashMap<>((Map<String, Object>) operation.get("result"));
        result.put("resultVersion", 1); result.put("capability", "read"); result.put("message", "短解释\n\n原文问题");
        result.put("sources", List.of()); result.put("sentenceSourceMap", List.of());
        result.put("materialScope", Map.of("taskId", "operation-task", "allowedPaperIds", List.of("A"), "primaryPaperId", "A", "strictScope", true));
        result.put("artifact", Map.of("text", "完整学习解释", "paperIds", List.of("A"), "sources", List.of())); operation.put("result", result);
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r1")), eq(Map.class))).thenReturn(operation);
        for (int index = 0; index < 2; index++) mvc.perform(get(root + "/operations/r1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.task.messages[1].content").value("短解释\n\n原文问题"))
                .andExpect(jsonPath("$.task.messages[1].artifactId").value("r1:artifact"))
                .andExpect(jsonPath("$.task.artifacts.length()").value(1)).andExpect(jsonPath("$.task.artifacts[0].text").value("完整学习解释"));
    }
    @Test void unknownRequestCanBeStoppedBeforeALateSubmissionWithoutScheduling() throws Exception {
        Map<String, Object> original = Map.of("message", "question", "capability", "chat", "allowedPaperIds", List.of("A"), "expectedTaskRevision", task.get("revision"));
        Map<String, Object>[] saved = new Map[]{null};
        when(upstream.getForObject(any(java.net.URI.class), eq(Map.class))).thenAnswer(call -> {
            if (saved[0] == null) throw new HttpClientErrorException(HttpStatus.NOT_FOUND);
            return saved[0];
        });
        when(upstream.postForObject(any(java.net.URI.class), any(), eq(Map.class))).thenAnswer(call -> {
            org.junit.jupiter.api.Assertions.assertTrue(((java.net.URI)call.getArgument(0)).getPath().endsWith("/cancel-before-start"));
            saved[0] = new LinkedHashMap<>((Map<String, Object>)call.getArgument(1)); saved[0].put("status", "cancelled"); return saved[0];
        });
        mvc.perform(post(root + "/operations/r1/cancel").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("kind", "conversation.execute", "input", original))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("cancelled"));
        mvc.perform(post(root + "/operations").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("requestId", "r1", "kind", "conversation.execute", "input", original))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("cancelled"));
        verify(upstream, times(1)).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }
    @Test void retryUsesStableIdentityAndSavedScopeWhileExposingOnlyUserIntent() throws Exception {
        Map<String, Object> intent = Map.of("message", "original question", "capability", "chat", "expectedTaskRevision", task.get("revision"),
                "history", List.of(Map.of("content", "browser secret")));
        Map<String, Object> failed = Map.of("taskId", "operation-task", "requestId", "r1", "kind", "conversation.execute", "status", "failed",
                "input", Map.of("original", intent, "upstream", Map.of("primaryPaperId", "A", "history", List.of("provider secret")), "paperIds", List.of("A")));
        String replacementId = java.util.UUID.nameUUIDFromBytes("operation-task:r1:retry".getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
        Map<String, Map<String, Object>> receipts = new java.util.HashMap<>(); receipts.put("r1", failed);
        when(upstream.getForObject(any(java.net.URI.class), eq(Map.class))).thenAnswer(call -> {
            String path = ((java.net.URI) call.getArgument(0)).getPath();
            Map<String, Object> value = receipts.get(path.substring(path.lastIndexOf('/') + 1));
            if (value == null) throw new HttpClientErrorException(HttpStatus.NOT_FOUND);
            return value;
        });
        when(upstream.postForObject(any(java.net.URI.class), any(), eq(Map.class))).thenAnswer(call -> {
            Map<String, Object> submitted = call.getArgument(1);
            Map<String, Object> queued = new java.util.LinkedHashMap<>(submitted); queued.put("status", "queued");
            receipts.put((String) submitted.get("requestId"), queued); return queued;
        });
        mvc.perform(get(root + "/operations/r1")).andExpect(status().isOk())
                .andExpect(jsonPath("$.request.message").value("original question"))
                .andExpect(jsonPath("$.request.history").doesNotExist()).andExpect(jsonPath("$.input").doesNotExist());
        for (int index = 0; index < 2; index++) mvc.perform(post(root + "/operations/r1/retry"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.requestId").value(replacementId))
                .andExpect(jsonPath("$.retryOf").value("r1"))
                .andExpect(jsonPath("$.request.allowedPaperIds[0]").value("A"))
                .andExpect(jsonPath("$.request.allowedPaperIds.length()").value(1));
        verify(upstream, times(1)).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }

    @Test void retryCannotExpandSavedScopeOrReexecuteAnUnconfirmedRequest() throws Exception {
        Map<String, Object> saved = Map.of("original", Map.of("message", "question", "capability", "chat", "expectedTaskRevision", task.get("revision")),
                "upstream", Map.of(), "paperIds", List.of("outside"));
        when(upstream.getForObject(any(java.net.URI.class), eq(Map.class))).thenAnswer(call -> {
            if (((java.net.URI)call.getArgument(0)).getPath().endsWith("/r1"))
                return Map.of("taskId", "operation-task", "requestId", "r1", "kind", "conversation.execute", "status", "failed", "input", saved);
            throw new HttpClientErrorException(HttpStatus.NOT_FOUND);
        });
        mvc.perform(post(root + "/operations/r1/retry")).andExpect(status().isBadRequest());
        verify(upstream, never()).postForObject(any(java.net.URI.class), any(), eq(Map.class));
        when(upstream.getForObject(any(java.net.URI.class), eq(Map.class))).thenReturn(Map.of("taskId", "operation-task", "requestId", "r1", "kind", "conversation.execute", "status", "running"));
        mvc.perform(post(root + "/operations/r1/retry")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("running"));
        verify(upstream, never()).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }
    Map<String,Object> conversationReceipt(String sourcePaper) {
        Map<String,Object> context = Map.of("taskId", "operation-task", "allowedPaperIds", List.of("B"), "primaryPaperId", "B", "strictScope", true);
        List<?> sources = List.of(Map.of("sourceId", "s", "pdfId", sourcePaper, "text", "证据"));
        Map<String,Object> result = Map.of("capability", "critique", "materialScope", context, "message", "简短结果", "sources", sources,
                "artifact", Map.of("text", "完整成果", "paperIds", List.of("B"), "sources", sources));
        return Map.of("taskId", "operation-task", "requestId", "r2", "kind", "conversation.execute", "status", "succeeded",
                "input", Map.of("paperIds", List.of("B"), "original", Map.of("displayText", "/批判 B"), "upstream", Map.of("capability", "critique", "message", "批判 B", "primaryPaperId", "B", "strictScope", true)), "result", result);
    }
    Map<String,Object> groupedCritique() {
        return Map.of("schemaVersion", 2, "scope", Map.of("allowedPaperIds", List.of("B"), "targetPaperIds", List.of("B"), "primaryPaperId", "B"),
                "question", Map.of("text", "画质可信吗"),
                "claims", List.of(Map.of("id", "c1", "paperIds", List.of("B"), "kind", "inference", "text", "条件限制", "references", List.of())),
                "issues", List.of(Map.of("id", "i1", "paperIds", List.of("B"), "conclusionClaimId", "c1", "supportClaimIds", List.of(), "relatedPendingIds", List.of())),
                "pending", List.of(), "presentation", Map.of("leadClaimIds", List.of("c1"), "chatIssueIds", List.of("i1"), "artifactIssueIds", List.of("i1")));
    }
    void saveGroupedCritique() {
        Map<String,Object> operation = new LinkedHashMap<>(conversationReceipt("B"));
        Map<String,Object> result = new LinkedHashMap<>((Map<String,Object>)operation.get("result"));
        result.put("critique", groupedCritique()); operation.put("result", result);
        task = tasks.applyOperation("operation-task", operation);
    }
    Map<String,Object> regeneratedReceipt(String baseVersion) {
        Map<String,Object> operation = new LinkedHashMap<>(conversationReceipt("B"));
        operation.put("requestId", "r3");
        Map<String,Object> result = new LinkedHashMap<>((Map<String,Object>)operation.get("result"));
        result.put("critique", groupedCritique());
        result.put("artifact", Map.of("text", "新版成果", "paperIds", List.of("B"), "sources", result.get("sources"), "critique", groupedCritique()));
        operation.put("result", result);
        operation.put("input", Map.of("paperIds", List.of("B"), "original", Map.of("displayText", "重新核查"),
                "upstream", Map.of("capability", "critique", "message", "重新核查", "primaryPaperId", "B", "strictScope", true,
                        "critiqueContext", Map.of("regenerate", true, "sourceArtifactId", "r2:artifact", "version", baseVersion))));
        return operation;
    }
    @Test void regenerationCreatesOneVersionAndReplayingDoesNotDuplicateIt() {
        saveGroupedCritique();
        Map<?,?> previous = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        Map<String,Object> operation = regeneratedReceipt(String.valueOf(previous.get("createdAt")));
        tasks.applyOperation("operation-task", operation); task = tasks.applyOperation("operation-task", operation);
        org.junit.jupiter.api.Assertions.assertEquals(1, ((List<?>)task.get("artifacts")).size());
        Map<?,?> current = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        org.junit.jupiter.api.Assertions.assertEquals("r2:artifact", current.get("id"));
        org.junit.jupiter.api.Assertions.assertEquals("新版成果", current.get("text"));
        org.junit.jupiter.api.Assertions.assertEquals(1, ((List<?>)current.get("versions")).size());
        org.junit.jupiter.api.Assertions.assertEquals("完整成果", ((Map<?,?>)((List<?>)current.get("versions")).getFirst()).get("text"));
    }
    @Test void regenerationCannotOverwriteAnEditedVersion() {
        saveGroupedCritique();
        Map<?,?> previous = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        Map<String,Object> operation = regeneratedReceipt(String.valueOf(previous.get("createdAt")));
        Map<String,Object> edited = new LinkedHashMap<>((Map<String,Object>)previous); edited.put("text", "我的编辑");
        task.put("artifacts", List.of(edited)); tasks.updateFromClient("operation-task", task);
        org.junit.jupiter.api.Assertions.assertThrows(org.springframework.web.server.ResponseStatusException.class,
                () -> tasks.applyOperation("operation-task", operation));
        org.junit.jupiter.api.Assertions.assertEquals("我的编辑", ((Map<?,?>)((List<?>)tasks.get("operation-task").get("artifacts")).getFirst()).get("text"));
    }
    @Test void restoringGeneratedHistoryUsesServerClaimsAndStripsForgedHistory() {
        saveGroupedCritique();
        Map<?,?> previous = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        task = tasks.applyOperation("operation-task", regeneratedReceipt(String.valueOf(previous.get("createdAt"))));
        Map<String,Object> restored = new LinkedHashMap<>((Map<String,Object>)((List<?>)task.get("artifacts")).getFirst());
        restored.put("text", "完整成果"); restored.put("critique", Map.of("schemaVersion", 999));
        restored.put("versions", List.of(Map.of("text", "伪造历史", "savedAt", "forged", "critique", groupedCritique())));
        task.put("artifacts", List.of(restored)); task = tasks.updateFromClient("operation-task", task);
        Map<?,?> saved = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        org.junit.jupiter.api.Assertions.assertEquals(groupedCritique(), saved.get("critique"));
        org.junit.jupiter.api.Assertions.assertEquals(false, saved.get("edited"));
        org.junit.jupiter.api.Assertions.assertFalse(((Map<?,?>)((List<?>)saved.get("versions")).getFirst()).containsKey("critique"));
    }
    @Test void groupedCritiqueIsDurableAndBrowserCannotForgeClaimsOrScope() throws Exception {
        saveGroupedCritique();
        Map<String,Object> artifact = new LinkedHashMap<>((Map<String,Object>)((List<?>)task.get("artifacts")).getFirst());
        org.junit.jupiter.api.Assertions.assertEquals(groupedCritique(), artifact.get("critique"));
        org.junit.jupiter.api.Assertions.assertEquals(groupedCritique(), ((Map<?,?>)((List<?>)task.get("messages")).get(1)).get("critique"));
        artifact.put("text", "用户补写的结论"); artifact.put("critique", Map.of("schemaVersion", 999)); artifact.put("paperIds", List.of("A")); artifact.put("edited", false);
        task.put("artifacts", List.of(artifact)); task = tasks.updateFromClient("operation-task", task);
        Map<?,?> stored = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        org.junit.jupiter.api.Assertions.assertEquals(groupedCritique(), stored.get("critique"));
        org.junit.jupiter.api.Assertions.assertEquals(List.of("B"), stored.get("paperIds"));
        org.junit.jupiter.api.Assertions.assertEquals(true, stored.get("edited"));
    }
    @Test void followupUsesSavedVersionAndNeverAcceptsBrowserClaims() throws Exception {
        saveGroupedCritique();
        Map<?,?> artifact = (Map<?,?>)((List<?>)task.get("artifacts")).getFirst();
        when(upstream.postForObject(any(java.net.URI.class), any(), eq(Map.class))).thenAnswer(call -> {
            Map<?,?> payload = (Map<?,?>)((Map<?,?>)call.getArgument(1)).get("input");
            Map<?,?> input = (Map<?,?>)payload.get("upstream");
            Map<?,?> context = (Map<?,?>)input.get("critiqueContext");
            org.junit.jupiter.api.Assertions.assertEquals("i1", context.get("focusedIssueId"));
            org.junit.jupiter.api.Assertions.assertEquals(groupedCritique().get("claims"), context.get("claims"));
            org.junit.jupiter.api.Assertions.assertEquals(List.of("B"), input.get("targetPaperIds"));
            return Map.of("taskId", "operation-task", "requestId", "r1", "kind", "conversation.execute", "status", "queued");
        });
        Map<String,Object> original = Map.of("message", "解释第一点", "allowedPaperIds", List.of("B"), "expectedTaskRevision", task.get("revision"),
                "critiqueContext", Map.of("claims", List.of("forged")), "followup", Map.of("artifactId", "r2:artifact", "issueId", "i1", "version", artifact.get("createdAt")));
        mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(
                Map.of("requestId", "r1", "kind", "conversation.execute", "input", original)))).andExpect(status().isOk());
    }
    @Test void followupRejectsStaleVersionAndUnknownIssueWithoutScheduling() throws Exception {
        saveGroupedCritique();
        for (Map<String,Object> followup : List.of(Map.<String,Object>of("artifactId", "r2:artifact", "version", "stale"),
                Map.<String,Object>of("artifactId", "r2:artifact", "issueId", "unknown"))) {
            mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(
                    Map.of("requestId", "r1", "kind", "conversation.execute", "input", Map.of("message", "解释", "allowedPaperIds", List.of("B"),
                            "expectedTaskRevision", task.get("revision"), "followup", followup)))))
                    .andExpect(status().is(followup.containsKey("version") ? 409 : 400));
        }
        verify(upstream, never()).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }
    @Test void editedFollowupKeepsUserProseSeparateFromGroundedClaims() throws Exception {
        saveGroupedCritique();
        Map<String,Object> artifact = new LinkedHashMap<>((Map<String,Object>)((List<?>)task.get("artifacts")).getFirst());
        artifact.put("text", "用户的猜想"); task.put("artifacts", List.of(artifact));
        task = tasks.updateFromClient("operation-task", task);
        when(upstream.postForObject(any(java.net.URI.class), any(), eq(Map.class))).thenAnswer(call -> {
            Map<?,?> payload = (Map<?,?>)((Map<?,?>)call.getArgument(1)).get("input");
            Map<?,?> context = (Map<?,?>)((Map<?,?>)payload.get("upstream")).get("critiqueContext");
            org.junit.jupiter.api.Assertions.assertEquals(true, context.get("edited"));
            org.junit.jupiter.api.Assertions.assertEquals("用户的猜想", context.get("text"));
            org.junit.jupiter.api.Assertions.assertEquals(List.of(), context.get("claims"));
            org.junit.jupiter.api.Assertions.assertEquals(List.of(), context.get("issues"));
            return Map.of("taskId", "operation-task", "requestId", "r1", "kind", "conversation.execute", "status", "queued");
        });
        mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(
                Map.of("requestId", "r1", "kind", "conversation.execute", "input", Map.of("message", "解释", "allowedPaperIds", List.of("B"),
                        "expectedTaskRevision", task.get("revision"), "followup", Map.of("artifactId", "r2:artifact", "issueId", "i1"))))))
                .andExpect(status().isOk());
    }
    @Test void invalidCritiqueDependencyIsRejectedAtomically() {
        Map<String,Object> operation = new LinkedHashMap<>(conversationReceipt("B"));
        Map<String,Object> result = new LinkedHashMap<>((Map<String,Object>)operation.get("result"));
        Map<String,Object> critique = new LinkedHashMap<>(groupedCritique());
        critique.put("presentation", Map.of("leadClaimIds", List.of("unknown"), "chatIssueIds", List.of("i1"), "artifactIssueIds", List.of("i1")));
        result.put("critique", critique); operation.put("result", result);
        org.junit.jupiter.api.Assertions.assertThrows(org.springframework.web.server.ResponseStatusException.class, () -> tasks.applyOperation("operation-task", operation));
        org.junit.jupiter.api.Assertions.assertTrue(((List<?>)tasks.get("operation-task").get("messages")).isEmpty());
    }
    @Test void conversationCommitsMessageAndArtifactOnceWithoutChangingLesson() throws Exception {
        tasks.applyOperation("operation-task", receipt("succeeded"));
        Map<String,Object> current = tasks.get("operation-task");
        current.put("notes", List.of(Map.of("text", "已有笔记")));
        tasks.update("operation-task", current);
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r2")), eq(Map.class))).thenReturn(conversationReceipt("B"));
        for (int index=0; index<2; index++) mvc.perform(get(root+"/operations/r2"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.task.messages.length()").value(4))
            .andExpect(jsonPath("$.task.artifacts.length()").value(1))
            .andExpect(jsonPath("$.task.artifacts[0].text").value("完整成果"))
            .andExpect(jsonPath("$.task.messages[3].content").value("简短结果"))
            .andExpect(jsonPath("$.task.activeActivity.pdfId").value("A"))
            .andExpect(jsonPath("$.task.notes[0].text").value("已有笔记"));
    }
    @Test void conversationRejectsSourceOutsideSnapshotWithoutSavingAnything() throws Exception {
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r2")), eq(Map.class))).thenReturn(conversationReceipt("A"));
        mvc.perform(get(root+"/operations/r2")).andExpect(status().isBadGateway());
        Map<String,Object> current = tasks.get("operation-task");
        org.junit.jupiter.api.Assertions.assertTrue(((List<?>)current.get("messages")).isEmpty());
        org.junit.jupiter.api.Assertions.assertTrue(((List<?>)current.get("artifacts")).isEmpty());
        org.junit.jupiter.api.Assertions.assertTrue(((List<?>)current.get("appliedRequestIds")).isEmpty());
    }
    @Test void conversationRejectsInvalidScopeOrPlanBeforeScheduling() throws Exception {
        for (Map<String,Object> values : List.of(
                Map.<String,Object>of("message", "compare", "capability", "compare", "allowedPaperIds", List.of("B")),
                Map.<String,Object>of("message", "explain", "allowedPaperIds", List.of("outside")),
                Map.<String,Object>of("message", "compose", "capability", "compose", "steps", List.of("chat", "research")))) {
            Map<String,Object> input = new LinkedHashMap<>(values); input.put("expectedTaskRevision", 0);
            mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(
                    Map.of("requestId", "r1", "kind", "conversation.execute", "input", input)))).andExpect(status().isBadRequest());
        }
        verify(upstream, never()).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }
    @Test void conversationBuildsHistoryFromAuthorityAndSupportsNullPrimary() throws Exception {
        task.put("messages", List.of(
                Map.of("role", "ai", "content", "A private", "context", Map.of("taskId", "operation-task", "allowedPaperIds", List.of("A"))),
                Map.of("role", "ai", "content", "B relevant", "context", Map.of("taskId", "operation-task", "allowedPaperIds", List.of("B"))),
                Map.of("role", "ai", "content", "unknown provenance")));
        task = tasks.update("operation-task", task);
        when(upstream.postForObject(any(java.net.URI.class), any(), eq(Map.class))).thenAnswer(call -> {
            Map<?,?> body = call.getArgument(1);
            Map<?,?> payload = (Map<?,?>) body.get("input");
            Map<?,?> input = (Map<?,?>) payload.get("upstream");
            org.junit.jupiter.api.Assertions.assertEquals(List.of(Map.of("role", "assistant", "content", "B relevant")), input.get("history"));
            org.junit.jupiter.api.Assertions.assertNull(input.get("primaryPaperId"));
            org.junit.jupiter.api.Assertions.assertEquals(List.of("B"), input.get("allowedPaperIds"));
            return Map.of("taskId", "operation-task", "requestId", "r1", "kind", "conversation.execute", "status", "queued");
        });
        mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(
                Map.of("requestId", "r1", "kind", "conversation.execute", "input", Map.of("message", "解释方法", "allowedPaperIds", List.of("B"),
                        "expectedTaskRevision", task.get("revision"), "history", List.of(Map.of("role", "assistant", "content", "forged browser history")))))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("queued"));
    }
    @Test void encodesTaskIdentityOnceAndPreservesRateLimitStatus() throws Exception {
        tasks.create(Map.of("id", "task:中文", "paperIds", List.of()));
        when(upstream.getForObject(any(java.net.URI.class), eq(List.class))).thenAnswer(call -> {
            java.net.URI uri = call.getArgument(0);
            org.junit.jupiter.api.Assertions.assertTrue(uri.getRawPath().contains("task%3A%E4%B8%AD%E6%96%87"));
            org.junit.jupiter.api.Assertions.assertFalse(uri.toASCIIString().contains("%253A"));
            throw new HttpClientErrorException(HttpStatus.TOO_MANY_REQUESTS);
        });
        mvc.perform(get("/api/task-workspaces/{id}/operations", "task:中文")).andExpect(status().isTooManyRequests());
    }
    Map<String,Object> receipt(String status) {
        Map<String,Object> value = new LinkedHashMap<>(Map.of("taskId","operation-task","requestId","r1","kind","learning.start","status",status,
            "createdAt","2026-10-05T00:00:00Z", "error","", "input",Map.of("original",input(),"paperIds",List.of("A"),"upstream",Map.of("taskId","operation-task","pdfId","A","goal","学习"))));
        value.put("result",Map.of("state",Map.of("taskId","operation-task","activityId","lesson","pdfId","A","revision",0,"status","active"),"message","理解目标","question","原文问题","sources",List.of()));
        return value;
    }
    @Test void commitsOnceDespiteRepeatedPollsAndMergesConcurrentNotes() throws Exception {
        var completed = receipt("succeeded");
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r1")),eq(Map.class))).thenReturn(completed);
        task.put("notes",List.of(Map.of("text","其他客户端的笔记")));
        tasks.update("operation-task",task);
        mvc.perform(get(root+"/operations/r1")).andExpect(status().isOk()).andExpect(jsonPath("$.task.messages.length()").value(2));
        mvc.perform(get(root+"/operations/r1")).andExpect(status().isOk()).andExpect(jsonPath("$.task.messages.length()").value(2))
            .andExpect(jsonPath("$.task.notes[0].text").value("其他客户端的笔记"));
        mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(Map.of("requestId","r1","kind","learning.start","input",input()))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("succeeded"));
        verify(upstream,never()).postForObject(any(java.net.URI.class),any(),eq(Map.class));
    }
    @Test void rejectsChangedRequestAndOutsideMaterialsBeforeScheduling() throws Exception {
        mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(Map.of("requestId","r1","kind","learning.start","input",Map.of("pdfId","outside","expectedTaskRevision",0)))))
            .andExpect(status().isBadRequest());
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r1")),eq(Map.class))).thenReturn(receipt("running"));
        mvc.perform(post(root+"/operations").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(Map.of("requestId","r1","kind","learning.start","input",Map.of("pdfId","B","expectedTaskRevision",0)))))
            .andExpect(status().isConflict());
        verify(upstream,never()).postForObject(any(java.net.URI.class),any(),eq(Map.class));
    }
    @Test void browserCannotReplaceActivityOrOperationReceipt() throws Exception {
        var completed = receipt("succeeded");
        tasks.applyOperation("operation-task",completed);
        Map<String,Object> client = tasks.get("operation-task");
        client.put("activeActivity",Map.of("activityId","forged","pdfId","B","status","active"));
        client.put("appliedRequestIds",List.of("fake"));
        mvc.perform(put(root).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(client)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.activeActivity.activityId").value("lesson"))
            .andExpect(jsonPath("$.appliedRequestIds[0]").value("r1"));
        client = tasks.get("operation-task"); client.put("paperIds",List.of("B"));
        mvc.perform(put(root).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(client))).andExpect(status().isConflict());
    }
    @Test void recoversGeneratedResultOnceWithoutRestoringObsoleteLearningState() throws Exception {
        var completed = receipt("succeeded");
        Map<String, Object> result = new LinkedHashMap<>((Map<String, Object>) completed.get("result"));
        result.put("materialScope", Map.of("taskId", "operation-task", "allowedPaperIds", List.of("A"), "primaryPaperId", "A"));
        result.put("artifact", Map.of("text", "完整旧学习结果", "paperIds", List.of("A"), "sources", List.of()));
        completed.put("result", result);
        // Bind a different activity before the old request completes.
        var newer = receipt("succeeded"); newer.put("requestId", "newer");
        Map<String, Object> newerResult = new LinkedHashMap<>((Map<String, Object>) newer.get("result"));
        newerResult.put("state", Map.of("taskId", "operation-task", "activityId", "current-lesson", "pdfId", "A", "revision", 0, "status", "active"));
        newer.put("result", newerResult); tasks.applyOperation("operation-task", newer);
        when(upstream.getForObject(any(java.net.URI.class), eq(Map.class))).thenReturn(completed);
        mvc.perform(get(root + "/operations/r1")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("conflicted"));
        for (int index = 0; index < 2; index++) mvc.perform(post(root + "/operations/r1/recover-result"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("succeeded"))
                .andExpect(jsonPath("$.task.activeActivity.activityId").value("current-lesson"))
                .andExpect(jsonPath("$.task.artifacts.length()").value(1))
                .andExpect(jsonPath("$.task.artifacts[0].text").value("完整旧学习结果"));
        mvc.perform(get(root + "/operations/r1")).andExpect(status().isOk())
                .andExpect(jsonPath("$.task.activeActivity.activityId").value("current-lesson"));
        verify(upstream, never()).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }
    @Test void recoveryRefusesMissingMaterialsAndPublishesNothing() throws Exception {
        var completed = receipt("succeeded");
        when(upstream.getForObject(any(java.net.URI.class), eq(Map.class))).thenReturn(completed);
        task.put("paperIds", List.of("B")); tasks.update("operation-task", task);
        mvc.perform(post(root + "/operations/r1/recover-result")).andExpect(status().isConflict());
        org.junit.jupiter.api.Assertions.assertEquals(List.of(), tasks.get("operation-task").get("artifacts"));
        org.junit.jupiter.api.Assertions.assertEquals(List.of(), tasks.get("operation-task").get("messages"));
        verify(upstream, never()).postForObject(any(java.net.URI.class), any(), eq(Map.class));
    }
    @Test void completedResultIsRetainedWhenMaterialsWereRemoved() throws Exception {
        var completed = receipt("succeeded");
        task.put("paperIds",List.of("B")); tasks.update("operation-task",task);
        when(upstream.getForObject(argThat((java.net.URI uri) -> uri != null && uri.getRawPath().endsWith("/r1")),eq(Map.class))).thenReturn(completed);
        mvc.perform(get(root+"/operations/r1")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("conflicted"))
            .andExpect(jsonPath("$.result.question").value("原文问题"));
        task = tasks.get("operation-task"); task.put("paperIds",List.of("A","B")); tasks.update("operation-task",task);
        mvc.perform(get(root+"/operations/r1")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("succeeded"));
    }
}
