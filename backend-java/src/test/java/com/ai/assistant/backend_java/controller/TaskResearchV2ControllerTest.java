package com.ai.assistant.backend_java.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
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
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;

import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.PaperRepository;
import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.ai.assistant.backend_java.service.ResearchService;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
class TaskResearchV2ControllerTest {
    @Autowired private MockMvc mvc;
    @Autowired private TaskWorkspaceService tasks;
    @Autowired private TaskWorkspaceRepository repository;
    @Autowired private PaperRepository paperRepository;
    @Autowired private ObjectMapper mapper;
    @MockBean private ResearchService research;
    private Map<String, Object> workspace;

    @BeforeEach
    void setup() {
        reset(research);
        repository.deleteAll();
        paperRepository.deleteAll();
        // Seed papers A, B, C with ready status and pdfBytes for scope-check and start tests
        for (String pid : List.of("A", "B", "C")) {
            Paper p = new Paper();
            p.setId(pid);
            p.setFileName("paper-" + pid + ".pdf");
            p.setProcessingStatus("ready");
            p.setPdfBytes(("pdf-content-" + pid).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            paperRepository.saveAndFlush(p);
        }
        workspace = tasks.create(Map.of("id", "work", "paperIds", List.of("A", "B", "C"), "focusedPaperId", "B"));
    }

    // === Unified start dispatches to v2 when v2 markers present ===

    @Test
    void retryLostStartResponseReturnsBoundRunBeforeOldTaskRevisionCheck() throws Exception {
        Map<String, Object> input = v2StartInput();
        when(research.createV2ResearchTask(any())).thenReturn(v2Success("run-replay", "queued", null, 0L));
        when(research.resumeV2ResearchTask(eq("run-replay"), any())).thenReturn(v2Success("run-replay", "running", null, 1L));
        when(research.getV2ResearchTask("run-replay")).thenReturn(v2Success("run-replay", "running", null, 1L));
        String body = mapper.writeValueAsString(input);
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk());
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.task.runId").value("run-replay"));
        org.mockito.Mockito.verify(research, org.mockito.Mockito.times(1)).createV2ResearchTask(any());
        org.mockito.Mockito.verify(research, org.mockito.Mockito.times(1)).resumeV2ResearchTask(eq("run-replay"), any());
        input.put("question", "同一请求却换了问题");
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input))).andExpect(status().isConflict());
    }

    @Test
    void unifiedStartDispatchesToV2WhenSourcePolicyPresent() throws Exception {
        when(research.createV2ResearchTask(any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(0);
            org.junit.jupiter.api.Assertions.assertEquals("deep-research-v2", body.get("engineVersion"));
            org.junit.jupiter.api.Assertions.assertEquals(2, body.get("contractVersion"));
            org.junit.jupiter.api.Assertions.assertEquals("work", body.get("workspaceTaskId"));
            org.junit.jupiter.api.Assertions.assertEquals(true, body.get("deferStart"));
            return v2Success("run-1", "queued", null);
        });
        when(research.resumeV2ResearchTask(eq("run-1"), any())).thenReturn(v2Success("run-1", "running", null, 1L));
        mvc.perform(post("/api/task-workspaces/work/research/start")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(v2StartInput())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("success"))
                .andExpect(jsonPath("$.workspace.id").value("work"))
                .andExpect(jsonPath("$.task.runId").value("run-1"))
                .andExpect(jsonPath("$.task.taskId").value("work"))
                .andExpect(jsonPath("$.task.contractVersion").value(2))
                .andExpect(jsonPath("$.task.engineVersion").value("deep-research-v2"));
    }

    @Test
    void unifiedStartDefaultsToLegacyWithoutV2Markers() throws Exception {
        when(research.createResearchTask(any())).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task",
                Map.of("taskId", "legacy-run", "status", "awaiting_plan_review"))));
        mvc.perform(post("/api/task-workspaces/work/research/start")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("question", "Legacy question",
                        "expectedTaskRevision", workspace.get("revision")))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result.task.taskId").value("legacy-run"));
    }

    // === Unified GET dispatches by stored engine ===

    @Test
    void unifiedGetDispatchesToV2ForV2Run() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-u1", 1L, "running"));
        when(research.getV2ResearchTask("run-u1")).thenReturn(v2Success("run-u1", "running", null, 2L));
        mvc.perform(get("/api/task-workspaces/work/research/run-u1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.workspace.id").value("work"))
                .andExpect(jsonPath("$.task.contractVersion").value(2))
                .andExpect(jsonPath("$.task.engineVersion").value("deep-research-v2"));
    }

    @Test
    void pollingKeepsConcurrentUserEditsWhileWaitingForResearchResponse() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-poll", 1L, "running"));
        when(research.getV2ResearchTask("run-poll")).thenAnswer(call -> {
            // Separate transaction commits after this HTTP request has read the workspace.
            try (var executor = java.util.concurrent.Executors.newSingleThreadExecutor()) {
                executor.submit(() -> {
                    Map<String, Object> edit = new LinkedHashMap<>(tasks.get("work"));
                    edit.put("title", "Concurrent user edit");
                    tasks.update("work", edit);
                }).get(5, java.util.concurrent.TimeUnit.SECONDS);
            }
            return v2Success("run-poll", "running", null, 2L);
        });
        mvc.perform(get("/api/task-workspaces/work/research/run-poll"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.runRevision").value(2))
                .andExpect(jsonPath("$.workspace.title").value("Concurrent user edit"));
        org.junit.jupiter.api.Assertions.assertEquals("Concurrent user edit", tasks.get("work").get("title"));
    }

    @Test
    void unifiedGetDispatchesToLegacyForLegacyRun() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "leg-1",
                "runId", "leg-1", "engineVersion", "legacy-v1",
                "paperIds", List.of("A"), "primaryPaperId", "A", "question", "old"));
        when(research.getResearchTask("leg-1")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task",
                Map.of("taskId", "leg-1", "status", "succeeded", "report", "报告", "findings",
                        List.of(Map.of("summary", "结论", "sources", List.of(Map.of("pdfId", "A"))))))));
        mvc.perform(get("/api/task-workspaces/work/research/leg-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.resultVersion").value(1));
    }

    // === researchId alias = runId for lookup ===

    @Test
    void researchIdAliasResolvesForV2Run() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-alias", 1L, "running"));
        when(research.getV2ResearchTask("run-alias")).thenReturn(v2Success("run-alias", "running", null, 2L));
        // Lookup by runId works
        mvc.perform(get("/api/task-workspaces/work/research/run-alias"))
                .andExpect(status().isOk());
    }

    // === Ownership on both runId and taskId ===

    @Test
    void unifiedGetRejectsForeignRunId() throws Exception {
        mvc.perform(get("/api/task-workspaces/work/research/foreign-run"))
                .andExpect(status().isNotFound());
        verifyNoInteractions(research);
    }

    @Test
    void unifiedGetRejectsMismatchedTaskIdInResponse() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-x", 1L, "running"));
        Map<String, Object> badState = new LinkedHashMap<>();
        badState.put("runId", "run-x"); badState.put("taskId", "other-task");
        badState.put("engineVersion", "deep-research-v2"); badState.put("runRevision", 2L);
        badState.put("status", "running");
        when(research.getV2ResearchTask("run-x")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", badState)));
        mvc.perform(get("/api/task-workspaces/work/research/run-x"))
                .andExpect(status().isBadGateway());
    }

    @Test
    void v2ActionsRejectForeignRunId() throws Exception {
        for (String action : List.of("pause", "clarify", "plan", "continue", "resume", "cancel")) {
            mvc.perform(post("/api/task-workspaces/work/research/foreign-run/" + action)
                    .contentType(MediaType.APPLICATION_JSON).content("{}"))
                    .andExpect(status().isNotFound());
        }
        verifyNoInteractions(research);
    }

    @Test
    void clarificationAndPlanKeepActualFrontendPayloads() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-edit", 1L, "waiting_user"));
        when(research.clarifyV2ResearchTask(eq("run-edit"), any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(1);
            org.junit.jupiter.api.Assertions.assertEquals("比较实验条件", body.get("answer"));
            return v2Success("run-edit", "running", null, 2L);
        });
        mvc.perform(post("/api/task-workspaces/work/research/run-edit/clarify")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"answer-1\",\"expectedRunRevision\":1,\"answer\":\"比较实验条件\"}"))
                .andExpect(status().isOk());
        List<Map<String, Object>> plan = List.of(Map.of("itemId", "one", "question", "固定哪些条件？"));
        when(research.planV2ResearchTask(eq("run-edit"), any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(1);
            org.junit.jupiter.api.Assertions.assertEquals(plan, body.get("plan"));
            return v2Success("run-edit", "paused", null, 3L);
        });
        mvc.perform(post("/api/task-workspaces/work/research/run-edit/plan")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(
                        Map.of("requestId", "plan-1", "expectedRunRevision", 2, "plan", plan))))
                .andExpect(status().isOk());
    }

    @Test
    void sourcesAndEventsRejectForeignRunId() throws Exception {
        mvc.perform(get("/api/task-workspaces/work/research/foreign-run/sources"))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/task-workspaces/work/research/foreign-run/events"))
                .andExpect(status().isNotFound());
        verifyNoInteractions(research);
    }

    // === Stale response ignored ===

    @Test
    void staleRevisionProjectionIgnored() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-stale", 5L, "running"));
        when(research.getV2ResearchTask("run-stale")).thenReturn(v2Success("run-stale", "running", null, 3L));
        mvc.perform(get("/api/task-workspaces/work/research/run-stale"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.runRevision").value(5))
                .andExpect(jsonPath("$.task.status").value("running"));
    }

    @Test
    void newerRevisionAccepted() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-newer", 2L, "running"));
        when(research.getV2ResearchTask("run-newer")).thenReturn(v2Success("run-newer", "completed", "partial", 7L));
        mvc.perform(get("/api/task-workspaces/work/research/run-newer"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.runRevision").value(7))
                .andExpect(jsonPath("$.task.outcome").value("partial"));
    }

    // === Duplicate publication idempotent (receipt keyed by runId+reportVersionId) ===

    @Test
    void duplicatePublicationIsIdempotent() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-dup", 1L, "running"));
        Map<String, Object> completedState = v2CompletedState("run-dup", "complete", "v-dup-1", "完成摘要", "报告内容");
        when(research.getV2ResearchTask("run-dup")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", completedState)));

        mvc.perform(get("/api/task-workspaces/work/research/run-dup")).andExpect(status().isOk());
        int artifactCount1 = ((List<?>) tasks.get("work").get("artifacts")).size();

        // Second poll - no duplicate artifacts
        mvc.perform(get("/api/task-workspaces/work/research/run-dup")).andExpect(status().isOk());
        int artifactCount2 = ((List<?>) tasks.get("work").get("artifacts")).size();
        org.junit.jupiter.api.Assertions.assertEquals(artifactCount1, artifactCount2);
    }

    @Test
    void differentReportVersionsCreateSeparateMachineArtifacts() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-mv", 1L, "running"));

        // Version 1
        Map<String, Object> state1 = v2CompletedState("run-mv", "complete", "v-mv-1", "摘要1", "报告1");
        state1.put("runRevision", 2L);
        when(research.getV2ResearchTask("run-mv")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state1)));
        mvc.perform(get("/api/task-workspaces/work/research/run-mv")).andExpect(status().isOk());

        // Version 2
        Map<String, Object> state2 = v2CompletedState("run-mv", "complete", "v-mv-2", "摘要2", "报告2");
        state2.put("runRevision", 3L);
        when(research.getV2ResearchTask("run-mv")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state2)));
        mvc.perform(get("/api/task-workspaces/work/research/run-mv")).andExpect(status().isOk());

        // Should have machine v1 + latest replaced by v2 = 2 machine artifacts + 1 latest
        List<?> artifacts = (List<?>) tasks.get("work").get("artifacts");
        long machineCount = artifacts.stream().filter(a -> a instanceof Map<?, ?> item && "machine".equals(item.get("origin"))).count();
        org.junit.jupiter.api.Assertions.assertEquals(2, machineCount, "Both machine versions preserved");
    }

    // === User edit protection: machine version preserved, latest not overwritten ===

    @Test
    void userEditedArtifactNotOverwrittenButMachineVersionPreserved() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-edit", 1L, "running"));

        // First publication
        Map<String, Object> state1 = v2CompletedState("run-edit", "complete", "v-e1", "初始摘要", "初始报告");
        state1.put("runRevision", 2L);
        when(research.getV2ResearchTask("run-edit")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state1)));
        mvc.perform(get("/api/task-workspaces/work/research/run-edit")).andExpect(status().isOk());

        // Simulate user edit on latest artifact
        Map<String, Object> current = tasks.get("work");
        @SuppressWarnings("unchecked")
        List<Object> artifacts = (List<Object>) current.get("artifacts");
        for (int i = 0; i < artifacts.size(); i++) {
            @SuppressWarnings("unchecked")
            Map<String, Object> a = (Map<String, Object>) artifacts.get(i);
            if ("run-edit".equals(a.get("sourceRunId")) && Boolean.FALSE.equals(a.get("edited"))
                    && !"machine".equals(a.get("origin"))) {
                Map<String, Object> mutable = new LinkedHashMap<>(a);
                mutable.put("text", "用户修改后的正文");
                mutable.put("edited", true);
                artifacts.set(i, mutable);
                break;
            }
        }
        tasks.update("work", current);

        // New version published
        Map<String, Object> state2 = v2CompletedState("run-edit", "complete", "v-e2", "更新摘要", "新版报告");
        state2.put("runRevision", 3L);
        when(research.getV2ResearchTask("run-edit")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state2)));
        mvc.perform(get("/api/task-workspaces/work/research/run-edit")).andExpect(status().isOk());

        // Verify: machine v1 still exists, machine v2 added, user-edited latest preserved
        Map<String, Object> after = tasks.get("work");
        @SuppressWarnings("unchecked")
        List<?> finalArtifacts = (List<?>) after.get("artifacts");
        boolean hasMachineV1 = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "machine".equals(item.get("origin")) && "v-e1".equals(item.get("reportVersionId")));
        boolean hasMachineV2 = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "machine".equals(item.get("origin")) && "v-e2".equals(item.get("reportVersionId")));
        boolean hasUserEdit = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && Boolean.TRUE.equals(item.get("edited")) && "用户修改后的正文".equals(item.get("text")));
        org.junit.jupiter.api.Assertions.assertTrue(hasMachineV1, "Machine v1 must be preserved");
        org.junit.jupiter.api.Assertions.assertTrue(hasMachineV2, "Machine v2 must be saved");
        org.junit.jupiter.api.Assertions.assertTrue(hasUserEdit, "User edit must be preserved");
    }

    @Test
    void userVersionsListProtectsLatestWithoutEditedFlag() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-ver", 1L, "running"));

        // First publication
        Map<String, Object> state1 = v2CompletedState("run-ver", "complete", "v-ver-1", "初始摘要", "初始报告");
        state1.put("runRevision", 2L);
        when(research.getV2ResearchTask("run-ver")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state1)));
        mvc.perform(get("/api/task-workspaces/work/research/run-ver")).andExpect(status().isOk());

        // Simulate frontend setting versions list (no edited flag) on latest artifact
        Map<String, Object> current = tasks.get("work");
        @SuppressWarnings("unchecked")
        List<Object> artifacts = (List<Object>) current.get("artifacts");
        for (int i = 0; i < artifacts.size(); i++) {
            @SuppressWarnings("unchecked")
            Map<String, Object> a = (Map<String, Object>) artifacts.get(i);
            if ("run-ver".equals(a.get("sourceRunId")) && !"machine".equals(a.get("origin"))) {
                Map<String, Object> mutable = new LinkedHashMap<>(a);
                mutable.put("text", "用户通过版本列表修改的正文");
                mutable.put("versions", List.of(Map.of("text", "初始报告", "savedAt", Instant.now().toString())));
                // No edited field set
                artifacts.set(i, mutable);
                break;
            }
        }
        tasks.update("work", current);

        // New version published
        Map<String, Object> state2 = v2CompletedState("run-ver", "complete", "v-ver-2", "更新摘要", "新版报告");
        state2.put("runRevision", 3L);
        when(research.getV2ResearchTask("run-ver")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state2)));
        mvc.perform(get("/api/task-workspaces/work/research/run-ver")).andExpect(status().isOk());

        // Verify: machine v2 added, but latest with versions list preserved (not overwritten)
        Map<String, Object> after = tasks.get("work");
        @SuppressWarnings("unchecked")
        List<?> finalArtifacts = (List<?>) after.get("artifacts");
        boolean hasMachineV2 = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "machine".equals(item.get("origin")) && "v-ver-2".equals(item.get("reportVersionId")));
        boolean hasUserVersions = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "用户通过版本列表修改的正文".equals(item.get("text"))
                && item.get("versions") instanceof List<?> v && !v.isEmpty());
        org.junit.jupiter.api.Assertions.assertTrue(hasMachineV2, "Machine v2 must be saved");
        org.junit.jupiter.api.Assertions.assertTrue(hasUserVersions, "User versions-list artifact must be preserved");
    }

    @Test
    void userTitleOriginProtectsLatestWithoutEditedFlag() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-title", 1L, "running"));

        // First publication
        Map<String, Object> state1 = v2CompletedState("run-title", "complete", "v-t1", "初始摘要", "初始报告");
        state1.put("runRevision", 2L);
        when(research.getV2ResearchTask("run-title")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state1)));
        mvc.perform(get("/api/task-workspaces/work/research/run-title")).andExpect(status().isOk());

        // Simulate rename setting titleOrigin=user (no edited flag)
        Map<String, Object> current = tasks.get("work");
        @SuppressWarnings("unchecked")
        List<Object> artifacts = (List<Object>) current.get("artifacts");
        for (int i = 0; i < artifacts.size(); i++) {
            @SuppressWarnings("unchecked")
            Map<String, Object> a = (Map<String, Object>) artifacts.get(i);
            if ("run-title".equals(a.get("sourceRunId")) && !"machine".equals(a.get("origin"))) {
                Map<String, Object> mutable = new LinkedHashMap<>(a);
                mutable.put("title", "用户自定义标题");
                mutable.put("titleOrigin", "user");
                artifacts.set(i, mutable);
                break;
            }
        }
        tasks.update("work", current);

        // New version published
        Map<String, Object> state2 = v2CompletedState("run-title", "complete", "v-t2", "更新摘要", "新版报告");
        state2.put("runRevision", 3L);
        when(research.getV2ResearchTask("run-title")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state2)));
        mvc.perform(get("/api/task-workspaces/work/research/run-title")).andExpect(status().isOk());

        // Verify: machine v2 added, but latest with titleOrigin=user preserved
        Map<String, Object> after = tasks.get("work");
        @SuppressWarnings("unchecked")
        List<?> finalArtifacts = (List<?>) after.get("artifacts");
        boolean hasMachineV2 = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "machine".equals(item.get("origin")) && "v-t2".equals(item.get("reportVersionId")));
        boolean hasUserTitle = finalArtifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "用户自定义标题".equals(item.get("title")) && "user".equals(item.get("titleOrigin")));
        org.junit.jupiter.api.Assertions.assertTrue(hasMachineV2, "Machine v2 must be saved");
        org.junit.jupiter.api.Assertions.assertTrue(hasUserTitle, "User-titled artifact must be preserved");
    }

    // === sourceResearchId stored for frontend lookup ===

    @Test
    void publishedArtifactStoresSourceResearchIdForFrontendLookup() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-srcid", 1L, "running"));
        Map<String, Object> state = v2CompletedState("run-srcid", "complete", "v-srcid-1", "摘要", "报告");
        when(research.getV2ResearchTask("run-srcid")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state)));
        mvc.perform(get("/api/task-workspaces/work/research/run-srcid")).andExpect(status().isOk());

        List<?> artifacts = (List<?>) tasks.get("work").get("artifacts");
        boolean hasSourceResearchId = artifacts.stream().anyMatch(a -> a instanceof Map<?, ?> item
                && "run-srcid".equals(item.get("sourceResearchId")));
        org.junit.jupiter.api.Assertions.assertTrue(hasSourceResearchId, "sourceResearchId must be stored");
    }

    // === No hardcoded status when missing ===

    @Test
    void missingStatusPassedThroughAsNull() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-nostatus", 1L, null));
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("runId", "run-nostatus"); state.put("taskId", "work");
        state.put("engineVersion", "deep-research-v2"); state.put("runRevision", 2L);
        // No status field
        when(research.getV2ResearchTask("run-nostatus")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state)));
        mvc.perform(get("/api/task-workspaces/work/research/run-nostatus"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.status").doesNotExist());
    }

    // === Partial/Inconclusive honest ===

    @Test
    void partialOutcomePublishedHonestly() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-partial", 1L, "running"));
        Map<String, Object> state = v2CompletedState("run-partial", "partial", "v-p1", "部分完成", "部分报告");
        when(research.getV2ResearchTask("run-partial")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state)));
        mvc.perform(get("/api/task-workspaces/work/research/run-partial"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.outcome").value("partial"));
    }

    // === Scope-check endpoint ===

    @Test
    void scopeCheckReturnsValidWhenMaterialsReady() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-sc", 1L, "running"));
        mvc.perform(post("/api/task-workspaces/work/research/run-sc/scope-check")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(true))
                .andExpect(jsonPath("$.taskId").value("work"))
                .andExpect(jsonPath("$.runId").value("run-sc"));
    }

    @Test
    void scopeCheckRejectsLegacyEngine() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "leg-sc",
                "runId", "leg-sc", "engineVersion", "legacy-v1",
                "paperIds", List.of("A"), "primaryPaperId", "A", "question", "old"));
        mvc.perform(post("/api/task-workspaces/work/research/leg-sc/scope-check")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void scopeCheckDetectsRemovedMaterials() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-scrm", 1L, "running"));
        // Remove paper A from task
        Map<String, Object> changed = tasks.get("work");
        changed.put("paperIds", List.of("B", "C"));
        tasks.update("work", changed);

        mvc.perform(post("/api/task-workspaces/work/research/run-scrm/scope-check")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false))
                .andExpect(jsonPath("$.reason").value("materials_removed"));
    }

    @Test
    void scopeCheckFailsWhenPaperRecordMissing() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-scmiss", 1L, "running"));
        // Delete paper A from repository so record is missing
        paperRepository.deleteById("A");
        paperRepository.flush();

        mvc.perform(post("/api/task-workspaces/work/research/run-scmiss/scope-check")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false))
                .andExpect(jsonPath("$.reason").value("material_record_missing"));
    }

    @Test
    void scopeCheckFailsWhenStatusPending() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-scpend", 1L, "running"));
        // Set paper A to pending status
        Paper p = paperRepository.findById("A").orElseThrow();
        p.setProcessingStatus("pending");
        paperRepository.saveAndFlush(p);

        mvc.perform(post("/api/task-workspaces/work/research/run-scpend/scope-check")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false))
                .andExpect(jsonPath("$.reason").value("material_not_ready"));
    }

    @Test
    void scopeCheckFailsWhenStatusAbsent() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-scabs", 1L, "running"));
        // Set paper A processingStatus to null
        Paper p = paperRepository.findById("A").orElseThrow();
        p.setProcessingStatus(null);
        paperRepository.saveAndFlush(p);

        mvc.perform(post("/api/task-workspaces/work/research/run-scabs/scope-check")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false))
                .andExpect(jsonPath("$.reason").value("material_status_absent"));
    }

    @Test
    void scopeCheckDetectsMaterialReplacementViaSnapshotHash() throws Exception {
        // Attach run with a snapshot hash computed from current state
        String originalHash = computeTestSnapshotHash(List.of("A"), List.of(), "task_only");
        Map<String, Object> runWithHash = v2RunBinding("run-screpl", 1L, "running");
        runWithHash.put("snapshotHash", originalHash);
        tasks.attachResearchRun("work", workspace.get("revision"), runWithHash);

        // Replace paper A content (different pdfBytes triggers contentHash change)
        Paper p = paperRepository.findById("A").orElseThrow();
        p.setPdfBytes("replaced-content-bytes".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        paperRepository.saveAndFlush(p);

        // Supply the original hash - should detect mismatch via contentHash
        mvc.perform(post("/api/task-workspaces/work/research/run-screpl/scope-check")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("snapshotHash", originalHash))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false))
                .andExpect(jsonPath("$.reason").value("snapshot_changed"));
    }

    // === Resume/cancel with optional body ===

    @Test
    void resumeAcceptsOptionalBody() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-resb", 2L, "paused"));
        when(research.resumeV2ResearchTask(eq("run-resb"), any())).thenReturn(v2Success("run-resb", "running", null, 3L));
        mvc.perform(post("/api/task-workspaces/work/research/run-resb/resume")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"req-r\",\"expectedRunRevision\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.status").value("running"));
    }

    @Test
    void cancelAcceptsOptionalBody() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-canb", 2L, "running"));
        when(research.cancelV2ResearchTask(eq("run-canb"), any())).thenReturn(v2Success("run-canb", "cancelled", null, 3L));
        mvc.perform(post("/api/task-workspaces/work/research/run-canb/cancel")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"req-c\",\"expectedRunRevision\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.status").value("cancelled"));
    }

    // === V2-only actions reject legacy runs ===

    @Test
    void pauseRejectsLegacyRun() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "leg-p",
                "runId", "leg-p", "engineVersion", "legacy-v1",
                "paperIds", List.of("A"), "primaryPaperId", "A", "question", "old"));
        mvc.perform(post("/api/task-workspaces/work/research/leg-p/pause")
                .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isBadRequest());
    }

    // === Continue binds child run ===

    @Test
    void continueBindsChildRunAndReturnsChildRunId() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-parent", 5L, "completed"));
        when(research.continueV2ResearchTask(eq("run-parent"), any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(1);
            org.junit.jupiter.api.Assertions.assertEquals(true, body.get("deferStart"));
            Map<String, Object> childTask = new LinkedHashMap<>();
            childTask.put("runId", "run-child"); childTask.put("taskId", "work");
            childTask.put("engineVersion", "deep-research-v2"); childTask.put("runRevision", 0L);
            childTask.put("status", "queued"); childTask.put("contractVersion", 2);
            return ResponseEntity.ok(Map.of("status", "success", "task", childTask));
        });
        when(research.resumeV2ResearchTask(eq("run-child"), any())).thenReturn(v2Success("run-child", "running", null, 1L));
        mvc.perform(post("/api/task-workspaces/work/research/run-parent/continue")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"req-cont\",\"question\":\"补充研究\"}"))
                .andExpect(status().isOk())
                // workspace included for frontend adoption
                .andExpect(jsonPath("$.workspace.id").value("work"))
                // task.runId MUST be child for frontend adoption
                .andExpect(jsonPath("$.task.runId").value("run-child"))
                // parentRunId is separate
                .andExpect(jsonPath("$.task.parentRunId").value("run-parent"))
                .andExpect(jsonPath("$.task.taskId").value("work"))
                .andExpect(jsonPath("$.task.status").value("running"));

        // Child run bound to workspace
        List<?> runs = (List<?>) tasks.get("work").get("researchRuns");
        boolean childFound = runs.stream().anyMatch(r -> r instanceof Map<?, ?> run && "run-child".equals(run.get("runId")));
        org.junit.jupiter.api.Assertions.assertTrue(childFound, "Child run must be bound");
        // Parent run still present
        boolean parentFound = runs.stream().anyMatch(r -> r instanceof Map<?, ?> run && "run-parent".equals(run.get("runId")));
        org.junit.jupiter.api.Assertions.assertTrue(parentFound, "Parent run must remain");
    }

    // === Legacy compatibility preserved ===

    @Test
    void legacyReviewEndpointsStillWork() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "leg-rev",
                "runId", "leg-rev", "engineVersion", "legacy-v1",
                "paperIds", List.of("A"), "primaryPaperId", "A", "question", "old"));
        when(research.reviewResearchPlan(eq("leg-rev"), any())).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task",
                Map.of("taskId", "leg-rev", "status", "running"))));
        mvc.perform(post("/api/task-workspaces/work/research/leg-rev/plan-review")
                .contentType(MediaType.APPLICATION_JSON).content("{\"subQuestions\":[\"Q1\"]}"))
                .andExpect(status().isOk());
    }

    // === Helpers ===

    @Test
    void externalOnlySelectionIsExplicitAndLocalPolicyRejectsIt() throws Exception {
        Map<String, Object> input = v2StartInput();
        input.put("materialSelection", Map.of("mode", "external_only"));
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input))).andExpect(status().isBadRequest());
        input.put("sourcePolicy", Map.of("mode", "academic_external"));
        when(research.createV2ResearchTask(any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(0);
            org.junit.jupiter.api.Assertions.assertEquals(List.of(), ((Map<?, ?>) body.get("materialSelection")).get("materialIds"));
            return v2Success("external-run", "queued", null);
        });
        when(research.resumeV2ResearchTask(eq("external-run"), any())).thenReturn(v2Success("external-run", "running", null, 1L));
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input))).andExpect(status().isOk());
    }

    @Test
    void savedExternalMetadataAddsOnceAndConflictingRequestCannotAddAnotherSource() throws Exception {
        Map<String, Object> run = v2RunBinding("external-run", 1L, "completed");
        run.put("sourcePolicy", Map.of("mode", "academic_external"));
        tasks.attachResearchRun("work", workspace.get("revision"), run);
        Map<String, Object> source = Map.of("sourceId", "s", "workId", "arxiv:2601.00001", "arxivId", "2601.00001v1",
                "versionId", "arxiv:2601.00001v1", "title", "A public paper", "contentHash", "a".repeat(64));
        when(research.exportV2Source("external-run", "s")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "source", source)));
        Map<String, Object> input = Map.of("requestId", "add-1", "expectedTaskRevision", tasks.get("work").get("revision"));
        for (int index = 0; index < 2; index++) {
            mvc.perform(post("/api/task-workspaces/work/research/external-run/sources/s/add")
                    .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(input)))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.paperId").value("arxiv:2601.00001v1"));
        }
        org.junit.jupiter.api.Assertions.assertEquals("metadata", paperRepository.findById("arxiv:2601.00001v1").orElseThrow().getProcessingStatus());
        org.junit.jupiter.api.Assertions.assertEquals(4, ((List<?>) tasks.get("work").get("paperIds")).size());
        Map<String, Object> changed = new LinkedHashMap<>(source); changed.put("sourceId", "other");
        when(research.exportV2Source("external-run", "other")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "source", changed)));
        mvc.perform(post("/api/task-workspaces/work/research/external-run/sources/other/add")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(input))).andExpect(status().isConflict());
    }

    @Test
    void backgroundPublicationSyncConfirmsDurableVersionWithoutDuplicateArtifacts() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("background", 1L, "running"));
        Map<String, Object> state = v2CompletedState("background", "complete", "v1", "摘要", "已核对的正文");
        when(research.getV2ResearchTask("background")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task", state)));
        for (int index = 0; index < 2; index++) {
            mvc.perform(post("/api/task-workspaces/work/research/background/publication-sync").contentType(MediaType.APPLICATION_JSON).content("{}"))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.reportVersionId").value("v1"));
        }
        org.junit.jupiter.api.Assertions.assertEquals(2, ((List<?>) tasks.get("work").get("artifacts")).size());
    }

    @Test
    void selectedNotesAreFrozenUnverifiedContextAndEditingRevokesTheOldSnapshot() throws Exception {
        Map<String, Object> withNote = new LinkedHashMap<>(tasks.get("work"));
        withNote.put("notes", List.of(Map.of("id", "n", "title", "我的猜想", "text", "尚未验证：任何压缩都不损失画质")));
        workspace = tasks.updateFromClient("work", withNote);
        when(research.createV2ResearchTask(any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(0);
            Map<?, ?> snapshot = (Map<?, ?>) body.get("materialSnapshot");
            List<?> contexts = (List<?>) snapshot.get("contextMaterials");
            Map<?, ?> context = (Map<?, ?>) contexts.getFirst();
            org.junit.jupiter.api.Assertions.assertEquals("unverified_context", context.get("accessLevel"));
            org.junit.jupiter.api.Assertions.assertEquals("note:n", context.get("ref"));
            org.junit.jupiter.api.Assertions.assertEquals(64, ((String) context.get("contentHash")).length());
            org.junit.jupiter.api.Assertions.assertFalse(((List<?>) snapshot.get("materialRefs")).contains("note:n"));
            return v2Success("run-context", "queued", null, 0L);
        });
        when(research.resumeV2ResearchTask(eq("run-context"), any())).thenReturn(v2Success("run-context", "running", null, 1L));
        Map<String, Object> input = v2StartInput(); input.put("contextRefs", List.of("note:n"));
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input))).andExpect(status().isOk());
        Map<String, Object> current = tasks.get("work");
        Map<?, ?> run = (Map<?, ?>) ((List<?>) current.get("researchRuns")).getFirst();
        String hash = (String) run.get("snapshotHash");
        mvc.perform(post("/api/task-workspaces/work/research/run-context/scope-check").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("snapshotHash", hash)))).andExpect(jsonPath("$.valid").value(true));
        current.put("notes", List.of(Map.of("id", "n", "title", "我的猜想", "text", "已修改目标")));
        tasks.updateFromClient("work", current);
        mvc.perform(post("/api/task-workspaces/work/research/run-context/scope-check").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("snapshotHash", hash)))).andExpect(jsonPath("$.valid").value(false));
    }

    @Test
    void foreignContextIsRejectedBeforeModelDispatch() throws Exception {
        Map<String, Object> input = v2StartInput(); input.put("contextRefs", List.of("note:foreign"));
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input))).andExpect(status().isConflict());
        verifyNoInteractions(research);
    }

    @Test
    void fullWorkspaceSaveCannotEraseImmutableMachineReport() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), v2RunBinding("run-keep", 1L, "running"));
        when(research.getV2ResearchTask("run-keep")).thenReturn(ResponseEntity.ok(Map.of("status", "success",
                "task", v2CompletedState("run-keep", "complete", "v-keep", "摘要", "保存的原稿"))));
        mvc.perform(get("/api/task-workspaces/work/research/run-keep")).andExpect(status().isOk());
        Map<String, Object> current = tasks.get("work"); current.put("artifacts", List.of());
        Map<String, Object> saved = tasks.updateFromClient("work", current);
        List<?> artifacts = (List<?>) saved.get("artifacts");
        org.junit.jupiter.api.Assertions.assertEquals(1, artifacts.size());
        Map<?, ?> machine = (Map<?, ?>) artifacts.getFirst();
        org.junit.jupiter.api.Assertions.assertEquals("machine", machine.get("origin"));
        org.junit.jupiter.api.Assertions.assertEquals("保存的原稿", machine.get("text"));
        org.junit.jupiter.api.Assertions.assertEquals(true, machine.get("hiddenFromLibrary"));
    }

    private Map<String, Object> v2StartInput() {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("requestId", "req-v2-" + System.nanoTime());
        input.put("expectedTaskRevision", workspace.get("revision"));
        input.put("question", "如何区分剪枝与SH降阶的质量影响？");
        input.put("sourcePolicy", Map.of("mode", "task_only"));
        input.put("budgetProfile", "standard");
        input.put("outputKind", "experiment_design");
        return input;
    }

    private Map<String, Object> v2RunBinding(String runId, long revision, String statusVal) {
        Map<String, Object> run = new LinkedHashMap<>();
        run.put("runId", runId);
        run.put("researchId", runId); // alias
        run.put("taskId", "work");
        run.put("contractVersion", 2);
        run.put("engineVersion", "deep-research-v2");
        run.put("runRevision", revision);
        run.put("status", statusVal);
        run.put("paperIds", List.of("A"));
        run.put("focusPaperIds", List.of());
        run.put("sourcePolicy", Map.of("mode", "task_only"));
        run.put("question", "测试问题");
        return run;
    }

    private Map<String, Object> v2CompletedState(String runId, String outcome, String versionId, String summary, String body) {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("runId", runId); state.put("taskId", "work");
        state.put("engineVersion", "deep-research-v2"); state.put("runRevision", 2L);
        state.put("status", "completed"); state.put("outcome", outcome);
        state.put("summary", summary);
        state.put("report", Map.of("body", body, "versionId", versionId, "origin", "machine"));
        state.put("sources", List.of());
        return state;
    }

    private ResponseEntity<Map<String, Object>> v2Success(String runId, String status, String outcome) {
        return v2Success(runId, status, outcome, 1L);
    }

    private ResponseEntity<Map<String, Object>> v2Success(String runId, String status, String outcome, long revision) {
        Map<String, Object> task = new LinkedHashMap<>();
        task.put("runId", runId);
        task.put("taskId", "work");
        task.put("contractVersion", 2);
        task.put("engineVersion", "deep-research-v2");
        task.put("runRevision", revision);
        task.put("status", status);
        if (outcome != null) task.put("outcome", outcome);
        return ResponseEntity.ok(Map.of("status", "success", "task", task));
    }

    /** Mirrors TaskResearchService.computeSnapshotHash for test fixture construction. */
    private String computeTestSnapshotHash(List<String> materialIds, List<String> focusIds, String policyMode) {
        StringBuilder sb = new StringBuilder();
        for (String mid : materialIds) {
            Paper paper = paperRepository.findById(mid).orElse(null);
            String fileName = paper != null && paper.getFileName() != null ? paper.getFileName() : "";
            String pStatus = paper != null && paper.getProcessingStatus() != null ? paper.getProcessingStatus() : "";
            String uploadTime = paper != null && paper.getUploadTime() != null ? paper.getUploadTime().toString() : "";
            String contentHash = computeTestContentHash(paper != null ? paper.getPdfBytes() : null);
            sb.append(mid).append(':').append(fileName).append(':').append(pStatus).append(':').append(uploadTime).append(':').append(contentHash).append(',');
        }
        sb.append('|');
        for (String f : focusIds) sb.append(f).append(',');
        sb.append('|').append(policyMode);
        try {
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(sb.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(hash);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private String computeTestContentHash(byte[] pdfBytes) {
        if (pdfBytes == null || pdfBytes.length == 0) return "";
        try {
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(pdfBytes);
            return java.util.HexFormat.of().formatHex(hash);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
