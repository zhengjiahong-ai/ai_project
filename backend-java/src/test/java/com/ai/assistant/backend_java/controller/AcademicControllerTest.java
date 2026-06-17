package com.ai.assistant.backend_java.controller;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
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
                "user_knowledge_level", "normal",
                "reader_profile", Map.of(
                        "selfAssessedFamiliarity", "一般",
                        "preferredDepth", "深入"),
                "behavior_signals", Map.of(
                        "questionCount", 2))))).thenReturn(Map.of(
                        "status", "success",
                        "pdfId", "paper-1",
                        "background_knowledge", List.of("RAG", "knowledge graph")));

        mockMvc.perform(post("/api/background-knowledge")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"pdfId":"paper-1","user_knowledge_level":"normal","reader_profile":{"selfAssessedFamiliarity":"一般","preferredDepth":"深入"},"behavior_signals":{"questionCount":2}}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.pdfId").value("paper-1"))
                .andExpect(jsonPath("$.background_knowledge[0]").value("RAG"));
    }

    @Test
    void createResearchTaskReturnsNestedTaskSnapshot() throws Exception {
        when(aiService.createResearchTask(eq(Map.of(
                "question", "研究问题",
                "pdfId", "paper-1",
                "paperSkeleton", Map.of("abstract", "summary"))))).thenReturn(ResponseEntity.ok(Map.of(
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

        mockMvc.perform(post("/api/research-tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"question":"研究问题","pdfId":"paper-1","paperSkeleton":{"abstract":"summary"}}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.taskId").value("task-1"))
                .andExpect(jsonPath("$.task.status").value("pending"));
    }

    @Test
    void previewResearchBriefReturnsBriefPreview() throws Exception {
        when(aiService.previewResearchBrief(eq(Map.of(
                "question", "研究问题",
                "pdfId", "paper-1",
                "paperSkeleton", Map.of("abstract", "summary"),
                "userConstraints", "重点看实验")))).thenReturn(ResponseEntity.ok(Map.of(
                        "status", "success",
                        "briefPreview", Map.of(
                                "question", "研究问题",
                                "pdfId", "paper-1",
                                "brief", "聚焦实验设计。",
                                "assumptions", List.of("优先检查当前论文"),
                                "clarifyingQuestions", List.of(),
                                "suggestedSubQuestions", List.of("实验设置是什么？"),
                                "needsClarification", false,
                                "source", "llm"))));

        mockMvc.perform(post("/api/research-tasks/brief-preview")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"question":"研究问题","pdfId":"paper-1","paperSkeleton":{"abstract":"summary"},"userConstraints":"重点看实验"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.briefPreview.brief").value("聚焦实验设计。"))
                .andExpect(jsonPath("$.briefPreview.needsClarification").value(false));
    }

    @Test
    void getResearchTaskPropagatesNotFoundStatus() throws Exception {
        when(aiService.getResearchTask("task-missing")).thenReturn(ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                "status", "error",
                "message", "Research task not found.")));

        mockMvc.perform(get("/api/research-tasks/task-missing"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("Research task not found."));
    }

    @Test
    void getLatestResearchTaskReturnsSnapshotForPdf() throws Exception {
        when(aiService.getLatestResearchTask("paper-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "task", Map.of(
                        "taskId", "task-latest",
                        "status", "succeeded",
                        "stage", "done",
                        "progress", 1.0,
                        "question", "最近任务",
                        "pdfId", "paper-1",
                        "plan", List.of("Q1"),
                        "findings", List.of(),
                        "report", "report",
                        "error", ""))));

        mockMvc.perform(get("/api/research-tasks/latest").param("pdfId", "paper-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.taskId").value("task-latest"))
                .andExpect(jsonPath("$.task.status").value("succeeded"));
    }

    @Test
    void cancelResearchTaskReturnsCancelledSnapshot() throws Exception {
        when(aiService.cancelResearchTask("task-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "task", Map.of(
                        "taskId", "task-1",
                        "status", "cancelled",
                        "stage", "done",
                        "progress", 0.4,
                        "question", "研究问题",
                        "pdfId", "paper-1",
                        "plan", List.of("Q1"),
                        "findings", List.of(),
                        "report", "",
                        "error", ""))));

        mockMvc.perform(post("/api/research-tasks/task-1/cancel").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.status").value("cancelled"))
                .andExpect(jsonPath("$.task.taskId").value("task-1"));
    }

    @Test
    void getTraceReturnsForwardedPayload() throws Exception {
        when(aiService.getTrace("trace-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "trace", Map.of(
                        "traceId", "trace-1",
                        "taskType", "deep_research",
                        "status", "success",
                        "counters", Map.of("llmCalls", 1),
                        "steps", List.of(Map.of("name", "research_build_plan"))))));

        mockMvc.perform(get("/api/traces/trace-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.trace.traceId").value("trace-1"))
                .andExpect(jsonPath("$.trace.taskType").value("deep_research"));
    }

    @Test
    void getTracePropagatesNotFoundStatus() throws Exception {
        when(aiService.getTrace("missing-trace")).thenReturn(ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                "status", "error",
                "message", "Trace not found.")));

        mockMvc.perform(get("/api/traces/missing-trace"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("Trace not found."));
    }

    @Test
    void createAgentProjectReturnsProjectPayload() throws Exception {
        when(aiService.createAgentProject(eq(Map.of(
                "title", "Agent 项目",
                "goal", "比较方法",
                "paperIds", List.of("paper-1", "paper-2"))))).thenReturn(ResponseEntity.ok(Map.of(
                        "status", "success",
                        "project", Map.of(
                                "projectId", "project-1",
                                "title", "Agent 项目",
                                "goal", "比较方法",
                                "paperIds", List.of("paper-1", "paper-2")))));

        mockMvc.perform(post("/api/agent-projects")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"title":"Agent 项目","goal":"比较方法","paperIds":["paper-1","paper-2"]}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.project.projectId").value("project-1"));
    }

    @Test
    void listAgentProjectsReturnsForwardedPayload() throws Exception {
        when(aiService.listAgentProjects()).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "projects", List.of(Map.of("projectId", "project-1", "title", "Agent 项目")))));

        mockMvc.perform(get("/api/agent-projects"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projects[0].projectId").value("project-1"));
    }

    @Test
    void updateAgentProjectReturnsForwardedPayload() throws Exception {
        when(aiService.updateAgentProject(eq("project-1"), eq(Map.of("goal", "新目标")))).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "project", Map.of("projectId", "project-1", "goal", "新目标"))));

        mockMvc.perform(patch("/api/agent-projects/project-1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"goal":"新目标"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.project.goal").value("新目标"));
    }

    @Test
    void addAgentProjectPapersReturnsForwardedPayload() throws Exception {
        when(aiService.addAgentProjectPapers(eq("project-1"), eq(Map.of("paperIds", List.of("paper-3"))))).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "project", Map.of("projectId", "project-1", "paperIds", List.of("paper-1", "paper-3")))));

        mockMvc.perform(post("/api/agent-projects/project-1/papers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"paperIds":["paper-3"]}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.project.paperIds[1]").value("paper-3"));
    }

    @Test
    void removeAgentProjectPaperReturnsForwardedPayload() throws Exception {
        when(aiService.removeAgentProjectPaper("project-1", "paper-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "project", Map.of("projectId", "project-1", "paperIds", List.of()))));

        mockMvc.perform(delete("/api/agent-projects/project-1/papers/paper-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.project.projectId").value("project-1"));
    }

    @Test
    void deleteAgentProjectReturnsForwardedPayload() throws Exception {
        when(aiService.deleteAgentProject("project-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "projectId", "project-1")));

        mockMvc.perform(delete("/api/agent-projects/project-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projectId").value("project-1"));
    }

    @Test
    void createAgentTaskReturnsForwardedPayload() throws Exception {
        when(aiService.createAgentTask(eq("project-1"), eq(Map.of("prompt", "比较方法差异")))).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "task", Map.of("taskId", "agent-task-1", "status", "succeeded"))));

        mockMvc.perform(post("/api/agent-projects/project-1/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"prompt":"比较方法差异"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.taskId").value("agent-task-1"));
    }

    @Test
    void getLatestAgentTaskReturnsForwardedPayload() throws Exception {
        when(aiService.getLatestAgentTask("project-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "task", Map.of("taskId", "agent-task-1", "status", "succeeded"))));

        mockMvc.perform(get("/api/agent-projects/project-1/tasks/latest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.taskId").value("agent-task-1"));
    }

    @Test
    void listAgentProjectTasksReturnsForwardedPayload() throws Exception {
        when(aiService.listAgentProjectTasks("project-1", 10)).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "projectId", "project-1",
                "limit", 10,
                "tasks", List.of(Map.of("taskId", "agent-task-2", "status", "succeeded")))));

        mockMvc.perform(get("/api/agent-projects/project-1/tasks").param("limit", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tasks[0].taskId").value("agent-task-2"));
    }

    @Test
    void listAgentProjectTasksPropagatesNotFoundStatus() throws Exception {
        when(aiService.listAgentProjectTasks("missing-project", null)).thenReturn(ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                "status", "error",
                "message", "Agent project not found.")));

        mockMvc.perform(get("/api/agent-projects/missing-project/tasks"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("Agent project not found."));
    }

    @Test
    void getAgentTaskReturnsForwardedPayload() throws Exception {
        when(aiService.getAgentTask("agent-task-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "task", Map.of("taskId", "agent-task-1", "status", "succeeded"))));

        mockMvc.perform(get("/api/agent-tasks/agent-task-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.taskId").value("agent-task-1"));
    }

    @Test
    void cancelAgentTaskReturnsForwardedPayload() throws Exception {
        when(aiService.cancelAgentTask("agent-task-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "task", Map.of("taskId", "agent-task-1", "status", "cancelled"))));

        mockMvc.perform(post("/api/agent-tasks/agent-task-1/cancel"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task.status").value("cancelled"));
    }

    @Test
    void getAgentTraceReturnsForwardedPayload() throws Exception {
        when(aiService.getAgentTrace("trace-1")).thenReturn(ResponseEntity.ok(Map.of(
                "status", "success",
                "trace", Map.of("traceId", "trace-1", "taskType", "agent_research"))));

        mockMvc.perform(get("/api/agent-traces/trace-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.trace.taskType").value("agent_research"));
    }
}
