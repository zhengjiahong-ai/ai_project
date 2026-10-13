package com.ai.assistant.backend_java.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.http.MediaType;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.ai.assistant.backend_java.repository.TaskDocumentTransferRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@AutoConfigureMockMvc
class TaskDocumentTransferControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired TaskWorkspaceService tasks;
    @Autowired TaskWorkspaceRepository workspaces;
    @Autowired TaskDocumentTransferRepository receipts;
    Map<String, Object> source, target;
    @BeforeEach void setup() {
        receipts.deleteAll(); workspaces.deleteAll();
        source = tasks.create(Map.of("id", "source", "paperIds", List.of("A.pdf"), "notes", List.of(Map.of(
            "id", "note-1", "text", "我的理解", "paperIds", List.of("A.pdf"),
            "sources", List.of(Map.of("pdfId", "A.pdf", "quote", "original evidence")),
            "versions", List.of(Map.of("text", "旧理解", "savedAt", "yesterday"))))));
        target = tasks.create(Map.of("id", "target", "paperIds", List.of("B.pdf")));
    }
    Map<String, Object> input() {
        return new LinkedHashMap<>(Map.of("targetTaskId", "target", "documentId", "note-1", "collection", "notes",
            "requestId", "move-1", "sourceRevision", source.get("revision"), "targetRevision", target.get("revision"),
            "includeMaterials", true));
    }
    void send(Map<String, Object> body, int statusCode) throws Exception {
        mvc.perform(post("/api/task-workspaces/source/documents/move").contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(body))).andExpect(status().is(statusCode));
    }
    @Test void preservesContentSourcesVersionsAndReplaysWithoutChangingRevisions() throws Exception {
        mvc.perform(post("/api/task-workspaces/source/documents/move").contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(input()))).andExpect(status().isOk())
            .andExpect(jsonPath("$.sourceTask.notes").isEmpty())
            .andExpect(jsonPath("$.targetTask.notes[0].text").value("我的理解"))
            .andExpect(jsonPath("$.targetTask.notes[0].versions[0].text").value("旧理解"))
            .andExpect(jsonPath("$.targetTask.notes[0].sources[0].pdfId").value("A.pdf"))
            .andExpect(jsonPath("$.targetTask.notes[0].transferHistory[0].sourceTaskId").value("source"))
            .andExpect(jsonPath("$.targetTask.paperIds[1]").value("A.pdf"));
        Object before = tasks.get("target").get("revision");
        send(input(), 200);
        assertEquals(before, tasks.get("target").get("revision"));
        assertEquals(1, ((List<?>) tasks.get("target").get("notes")).size());
        assertEquals(1, receipts.count());
        mvc.perform(get("/api/task-workspaces/source/documents/moves/move-1")).andExpect(status().isOk())
            .andExpect(jsonPath("$.targetTask.notes[0].text").value("我的理解"));
        mvc.perform(get("/api/task-workspaces/target/documents/moves/move-1")).andExpect(status().isNotFound());
    }
    @Test void requiresMaterialConsentWithoutPartialWrite() throws Exception {
        var body = input(); body.put("includeMaterials", false); send(body, 409);
        assertEquals(source, tasks.get("source")); assertEquals(target, tasks.get("target"));
        assertEquals(0, receipts.count());
    }
    @Test void staleTargetCannotRemoveSourceDocument() throws Exception {
        var changed = new LinkedHashMap<>(target); changed.put("title", "新版本"); tasks.update("target", changed);
        send(input(), 409);
        assertEquals(source, tasks.get("source")); assertEquals(0, receipts.count());
    }
    @Test void collisionOrMissingDocumentDoesNotOverwriteDestination() throws Exception {
        var changed = new LinkedHashMap<>(target); changed.put("notes", List.of(Map.of("id", "note-1", "text", "目标旧文")));
        target = tasks.update("target", changed); send(input(), 409);
        assertEquals(source, tasks.get("source")); assertEquals(target, tasks.get("target"));
        var body = input(); body.put("documentId", "missing"); send(body, 409);
        assertEquals(source, tasks.get("source"));
    }
    @Test void targetFailureAfterSourceSaveRollsBackBothTasksAndReceipt() throws Exception {
        var entity = workspaces.findById("target").orElseThrow();
        var damaged = mapper.readValue(entity.getPayloadJson(), Map.class); damaged.put("focusedPaperId", "not-in-task");
        entity.setPayloadJson(mapper.writeValueAsString(damaged)); workspaces.saveAndFlush(entity);
        target = tasks.get("target");
        var beforeSource = tasks.get("source"); var beforeTarget = tasks.get("target");
        send(input(),400);
        assertEquals(beforeSource,tasks.get("source")); assertEquals(beforeTarget,tasks.get("target"));
        assertEquals(0,receipts.count());
    }
    @Test void simultaneousSameIdentityMovesOnlyOnce() throws Exception {
        var pool = java.util.concurrent.Executors.newFixedThreadPool(2);
        var gate = new java.util.concurrent.CountDownLatch(1);
        var json = mapper.writeValueAsString(input());
        java.util.concurrent.Callable<Integer> call = () -> { gate.await();
            return mvc.perform(post("/api/task-workspaces/source/documents/move").contentType(MediaType.APPLICATION_JSON)
                .content(json)).andReturn().getResponse().getStatus(); };
        try {
            var first = pool.submit(call); var second = pool.submit(call); gate.countDown();
            assertEquals(200,first.get(10,java.util.concurrent.TimeUnit.SECONDS));
            assertEquals(200,second.get(10,java.util.concurrent.TimeUnit.SECONDS));
            assertEquals(1,receipts.count()); assertEquals(1,((List<?>)tasks.get("target").get("notes")).size());
            assertEquals(List.of(),tasks.get("source").get("notes"));
        } finally { pool.shutdownNow(); }
    }
    @Test void requestIdentityCannotBeReusedForAnotherDocument() throws Exception {
        send(input(), 200);
        var body = input(); body.put("documentId", "other"); send(body, 409);
        assertEquals(1, receipts.count());
    }
}
