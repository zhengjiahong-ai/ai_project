package com.ai.assistant.backend_java.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;

import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.ai.assistant.backend_java.service.ResearchService;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
class TaskResearchControllerTest {
    @Autowired private MockMvc mvc;
    @Autowired private TaskWorkspaceService tasks;
    @Autowired private TaskWorkspaceRepository repository;
    @Autowired private ObjectMapper mapper;
    @MockBean private ResearchService research;
    private Map<String, Object> workspace;

    @BeforeEach
    void setup() {
        reset(research);
        repository.deleteAll();
        workspace = tasks.create(Map.of("id", "work", "paperIds", List.of("A", "B"), "focusedPaperId", "B"));
    }

    @Test
    void publishesConciseAnswerAndFullReportExactlyOnceWithoutReplacingUserEdits() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "owned",
                "paperIds", List.of("A"), "primaryPaperId", "A", "question", "研究问题"));
        Map<String, Object> current = tasks.get("work");
        current.put("notes", List.of(Map.of("content", "保留并发笔记")));
        tasks.update("work", current);
        String report = "完整研究报告\n".repeat(300);
        when(research.getResearchTask("owned")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task",
                Map.of("taskId", "owned", "status", "succeeded", "report", report, "findings",
                        List.of(Map.of("summary", "主要结论", "sources", List.of(Map.of("pdfId", "A.pdf", "quote", "原文证据"))))))));
        mvc.perform(get("/api/task-workspaces/work/research/owned")).andExpect(status().isOk())
                .andExpect(jsonPath("$.resultVersion").value(1))
                .andExpect(jsonPath("$.capability").value("research"))
                .andExpect(jsonPath("$.materialScope.taskId").value("work"))
                .andExpect(jsonPath("$.materialScope.allowedPaperIds[0]").value("A"))
                .andExpect(jsonPath("$.artifact.id").value("research:owned:artifact"))
                .andExpect(jsonPath("$.workspace.messages[0].artifactId").value("research:owned:artifact"))
                .andExpect(jsonPath("$.workspace.messages[0].content").value("主要结论\n\n完整报告已保存在成果中。"))
                .andExpect(jsonPath("$.workspace.artifacts[0].text").value(report))
                .andExpect(jsonPath("$.workspace.artifacts[0].sources[0].pdfId").value("A"))
                .andExpect(jsonPath("$.workspace.notes[0].content").value("保留并发笔记"));
        current = tasks.get("work");
        ((Map<String, Object>) ((List<?>) current.get("artifacts")).getFirst()).put("text", "用户修订正文");
        tasks.update("work", current);
        Object revision = tasks.get("work").get("revision");
        mvc.perform(get("/api/task-workspaces/work/research/owned")).andExpect(status().isOk())
                .andExpect(jsonPath("$.workspace.artifacts.length()").value(1))
                .andExpect(jsonPath("$.workspace.messages.length()").value(1))
                .andExpect(jsonPath("$.workspace.artifacts[0].text").value("用户修订正文"))
                .andExpect(jsonPath("$.workspace.revision").value(revision));
    }

    @Test
    void rejectsOutsideEvidenceWithoutPublishingAnyPartialResult() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "owned", "paperIds", List.of("A")));
        when(research.getResearchTask("owned")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task",
                Map.of("taskId", "owned", "status", "succeeded", "report", "报告", "findings",
                        List.of(Map.of("summary", "结论", "sources", List.of(Map.of("pdfId", "B"))))))));
        mvc.perform(get("/api/task-workspaces/work/research/owned")).andExpect(status().isBadGateway());
        org.junit.jupiter.api.Assertions.assertEquals(List.of(), tasks.get("work").get("artifacts"));
        org.junit.jupiter.api.Assertions.assertEquals(List.of(), tasks.get("work").get("messages"));
    }

    @Test
    void publishesClaimSummariesWithoutInternalSourceIdsAndKeepsFullReport() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "owned", "paperIds", List.of("A")));
        String report = "完整报告 [A.pdf-chunk-13]";
        when(research.getResearchTask("owned")).thenReturn(ResponseEntity.ok(Map.of("status", "success", "task",
                Map.of("taskId", "owned", "status", "succeeded", "report", report, "findings",
                        List.of(Map.of("summary", "内部摘要 [A.pdf-chunk-13]", "claims",
                                List.of(Map.of("summary", "四因素包含透射率。"), Map.of("summary", "恢复训练5000次。")),
                                "sources", List.of(Map.of("pdfId", "A"))))))));
        mvc.perform(get("/api/task-workspaces/work/research/owned")).andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("四因素包含透射率。\n\n恢复训练5000次。\n\n完整报告已保存在成果中。"))
                .andExpect(jsonPath("$.artifact.text").value(report));
    }

    @Test
    void createsWithAllTaskMaterialsAndPersistsImmutableRunBinding() throws Exception {
        when(research.createResearchTask(any())).thenAnswer(call -> {
            Map<?, ?> body = call.getArgument(0);
            org.junit.jupiter.api.Assertions.assertEquals(List.of("A", "B"), body.get("allowedPaperIds"));
            org.junit.jupiter.api.Assertions.assertEquals("B", body.get("pdfId"));
            org.junit.jupiter.api.Assertions.assertEquals(false, body.get("allowExternalSearch"));
            org.junit.jupiter.api.Assertions.assertEquals(false, body.get("allowWebSearch"));
            return success("run-1");
        });
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(start())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.revision").value(1))
                .andExpect(jsonPath("$.task.researchRuns[0].researchId").value("run-1"))
                .andExpect(jsonPath("$.task.researchRuns[0].paperIds[1]").value("B"))
                .andExpect(jsonPath("$.result.task.taskId").value("run-1"));
        workspace = tasks.get("work");
        workspace.put("title", "new title");
        workspace.put("researchRuns", List.of(Map.of("researchId", "forged")));
        Map<String, Object> saved = tasks.update("work", workspace);
        org.junit.jupiter.api.Assertions.assertEquals("run-1", ((Map<?, ?>) ((List<?>) saved.get("researchRuns")).getFirst()).get("researchId"));
        verifyNoInteractionsBeyondCreate();
    }

    @Test
    void resumesOnlyOwnedResearchWithItsOriginalMaterials() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "owned", "paperIds", List.of("A")));
        when(research.resumeResearchTask("owned")).thenReturn(success("owned"));
        mvc.perform(post("/api/task-workspaces/work/research/owned/resume")).andExpect(status().isOk());
        mvc.perform(post("/api/task-workspaces/work/research/outside/resume")).andExpect(status().isNotFound());
        verify(research).resumeResearchTask("owned");
        reset(research);
        Map<String, Object> changed = tasks.get("work");
        changed.put("paperIds", List.of("B"));
        tasks.update("work", changed);
        mvc.perform(post("/api/task-workspaces/work/research/owned/resume")).andExpect(status().isConflict());
        mvc.perform(post("/api/task-workspaces/work/research/owned/plan-review")
                .contentType(MediaType.APPLICATION_JSON).content("{\"subQuestions\":[\"question\"]}"))
                .andExpect(status().isConflict());
        verifyNoInteractions(research);
    }

    @Test
    void rejectsOutOfTaskMaterialInvalidPrimaryAndExternalSearchBeforeCreating() throws Exception {
        for (Map<String, Object> patch : List.of(Map.<String, Object>of("allowedPaperIds", List.of("outside")),
                Map.<String, Object>of("allowedPaperIds", List.of("A"), "pdfId", "B"),
                Map.<String, Object>of("allowExternalSearch", true), Map.<String, Object>of("allowedPaperIds", List.of()))) {
            Map<String, Object> input = start();
            input.putAll(patch);
            mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                    .content(mapper.writeValueAsString(input))).andExpect(status().isBadRequest());
        }
        verifyNoInteractions(research);
    }

    @Test
    void checksOwnershipForEveryReadAndActionAndPreservesExplicitReviewPayload() throws Exception {
        tasks.attachResearchRun("work", workspace.get("revision"), Map.of("researchId", "owned", "paperIds", List.of("A")));
        when(research.getResearchTask("owned")).thenReturn(success("owned"));
        when(research.reviewResearchPlan(eq("owned"), any())).thenReturn(success("owned"));
        when(research.reviewResearchFinal(eq("owned"), any())).thenReturn(success("owned"));
        when(research.cancelResearchTask("owned")).thenReturn(success("owned"));
        mvc.perform(get("/api/task-workspaces/work/research/owned")).andExpect(status().isOk());
        mvc.perform(post("/api/task-workspaces/work/research/owned/plan-review").contentType(MediaType.APPLICATION_JSON)
                .content("{\"subQuestions\":[\"Q1\"],\"reviewNotes\":\"approved by user\",\"autoApprove\":true}"))
                .andExpect(status().isOk());
        mvc.perform(post("/api/task-workspaces/work/research/owned/final-review").contentType(MediaType.APPLICATION_JSON)
                .content("{\"reviewNotes\":\"manual\",\"riskReviews\":[{\"riskId\":\"r1\",\"reviewStatus\":\"confirmed\"}]}"))
                .andExpect(status().isOk());
        mvc.perform(post("/api/task-workspaces/work/research/owned/cancel")).andExpect(status().isOk());
        verify(research).reviewResearchPlan("owned", Map.of("subQuestions", List.of("Q1"), "reviewNotes", "approved by user"));
        verify(research).reviewResearchFinal("owned", Map.of("reviewNotes", "manual", "riskReviews", List.of(Map.of("riskId", "r1", "reviewStatus", "confirmed"))));
        reset(research);
        mvc.perform(get("/api/task-workspaces/work/research/foreign")).andExpect(status().isNotFound());
        for (String action : List.of("cancel", "plan-review", "final-review")) {
            mvc.perform(post("/api/task-workspaces/work/research/foreign/" + action).contentType(MediaType.APPLICATION_JSON).content("{}"))
                    .andExpect(status().isNotFound());
        }
        verifyNoInteractions(research);
    }

    @Test
    void cancelsCreatedJobIfConcurrentWorkspaceWritePreventsBinding() throws Exception {
        when(research.createResearchTask(any())).thenAnswer(call -> {
            Map<String, Object> concurrent = tasks.get("work");
            concurrent.put("notes", List.of(Map.of("content", "concurrent note")));
            tasks.update("work", concurrent);
            return success("orphan");
        });
        when(research.cancelResearchTask("orphan")).thenReturn(success("orphan"));
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(start()))).andExpect(status().isConflict());
        verify(research).cancelResearchTask("orphan");
        Map<String, Object> saved = tasks.get("work");
        org.junit.jupiter.api.Assertions.assertEquals(List.of(), saved.get("researchRuns"));
        org.junit.jupiter.api.Assertions.assertEquals(List.of(Map.of("content", "concurrent note")), saved.get("notes"));
    }

    @Test
    void publicCreateCannotForgeOwnershipAndUpstreamFailureDoesNotBindRun() throws Exception {
        Map<String, Object> created = tasks.create(Map.of("id", "forged-work", "researchRuns", List.of(Map.of("researchId", "stolen"))));
        org.junit.jupiter.api.Assertions.assertEquals(List.of(), created.get("researchRuns"));
        when(research.createResearchTask(any())).thenReturn(ResponseEntity.status(503).body(Map.of("status", "error", "message", "private error")));
        mvc.perform(post("/api/task-workspaces/work/research/start").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(start()))).andExpect(status().isServiceUnavailable());
        org.junit.jupiter.api.Assertions.assertEquals(workspace, tasks.get("work"));
    }

    private void verifyNoInteractionsBeyondCreate() {
        org.mockito.Mockito.verify(research, org.mockito.Mockito.never()).reviewResearchPlan(any(), any());
        org.mockito.Mockito.verify(research, org.mockito.Mockito.never()).reviewResearchFinal(any(), any());
    }

    private Map<String, Object> start() {
        return new LinkedHashMap<>(Map.of("question", "Compare methods", "expectedTaskRevision", workspace.get("revision")));
    }

    private ResponseEntity<Map<String, Object>> success(String researchId) {
        return ResponseEntity.ok(Map.of("status", "success", "task", Map.of("taskId", researchId, "status", "awaiting_plan_review")));
    }
}
