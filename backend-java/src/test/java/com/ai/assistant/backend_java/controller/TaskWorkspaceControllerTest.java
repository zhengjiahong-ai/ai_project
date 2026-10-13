package com.ai.assistant.backend_java.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
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
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
class TaskWorkspaceControllerTest {
    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper mapper;
    @Autowired private TaskWorkspaceRepository repository;

    @BeforeEach
    void clearTasks() {
        repository.deleteAll();
    }

    @Test
    void archivesAndRestoresWithoutLosingContentAndPreservesArchiveForOlderClients() throws Exception {
        String json = mvc.perform(post("/api/task-workspaces").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(task("archive-contract"))))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.archived").value(false))
                .andReturn().getResponse().getContentAsString();
        Map<String, Object> current = mapper.readValue(json, new TypeReference<>() {});
        current.put("archived", true);
        json = mvc.perform(put("/api/task-workspaces/archive-contract").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(current)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.archived").value(true))
                .andExpect(jsonPath("$.notes[0].content").value("我的理解"))
                .andReturn().getResponse().getContentAsString();
        current = mapper.readValue(json, new TypeReference<>() {});
        current.remove("archived");
        json = mvc.perform(put("/api/task-workspaces/archive-contract").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(current)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.archived").value(true))
                .andReturn().getResponse().getContentAsString();
        current = mapper.readValue(json, new TypeReference<>() {});
        current.put("archived", false);
        mvc.perform(put("/api/task-workspaces/archive-contract").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(current)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.archived").value(false));
        mvc.perform(get("/api/task-workspaces/archive-contract"))
                .andExpect(jsonPath("$.archived").value(false))
                .andExpect(jsonPath("$.artifacts[0].title").value("比较表"));
    }

    @Test
    void rejectsInvalidArchiveState() throws Exception {
        Map<String, Object> input = task("invalid-archive");
        input.put("archived", "true");
        mvc.perform(post("/api/task-workspaces").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input))).andExpect(status().isBadRequest());
    }

    @Test
    void persistsMaterialsMessagesActivityNotesAndArtifactsAcrossRequests() throws Exception {
        Map<String, Object> input = task("task-contract-1");
        String createdJson = mvc.perform(post("/api/task-workspaces")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(input)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.paperIds[1]").value("B"))
                .andExpect(jsonPath("$.messages[0].content").value("问题"))
                .andExpect(jsonPath("$.activityHistory[0].snapshot.primaryPaperId").value("A"))
                .andReturn().getResponse().getContentAsString();
        Map<String, Object> created = mapper.readValue(createdJson, new TypeReference<>() {});

        mvc.perform(get("/api/task-workspaces/task-contract-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.notes[0].content").value("我的理解"))
                .andExpect(jsonPath("$.artifacts[0].title").value("比较表"));
        mvc.perform(get("/api/task-workspaces"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("task-contract-1"));

        created.put("messages", List.of());
        created.put("title", "修改后的任务");
        mvc.perform(put("/api/task-workspaces/task-contract-1")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(created)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.messages").isEmpty())
                .andExpect(jsonPath("$.title").value("修改后的任务"));
        mvc.perform(get("/api/task-workspaces/task-contract-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.messages").isEmpty());
    }

    @Test
    void staleRevisionCannotOverwriteAnotherClient() throws Exception {
        String originalJson = mvc.perform(post("/api/task-workspaces")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(task("task-conflict"))))
                .andReturn().getResponse().getContentAsString();
        Map<String, Object> original = mapper.readValue(originalJson, new TypeReference<>() {});
        Map<String, Object> firstClient = new LinkedHashMap<>(original);
        firstClient.put("title", "已保存的新标题");
        mvc.perform(put("/api/task-workspaces/task-conflict")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(firstClient)))
                .andExpect(status().isOk());

        Map<String, Object> staleClient = new LinkedHashMap<>(original);
        staleClient.put("title", "过期写入");
        mvc.perform(put("/api/task-workspaces/task-conflict")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(staleClient)))
                .andExpect(status().isConflict());
        mvc.perform(get("/api/task-workspaces/task-conflict"))
                .andExpect(jsonPath("$.title").value("已保存的新标题"));
    }

    @Test
    void rejectsInvalidScopeAndPreservesExistingTaskOnDuplicateImport() throws Exception {
        mvc.perform(post("/api/task-workspaces")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(task("legacy:A"))))
                .andExpect(status().isCreated());
        mvc.perform(post("/api/task-workspaces")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(task("legacy:A"))))
                .andExpect(status().isConflict());
        Map<String, Object> invalid = task("bad-task");
        invalid.put("focusedPaperId", "another-task-paper");
        mvc.perform(post("/api/task-workspaces")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(invalid)))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/task-workspaces/bad-task")).andExpect(status().isNotFound());
    }

    @Test
    void deletionRequiresCurrentRevision() throws Exception {
        String createdJson = mvc.perform(post("/api/task-workspaces")
                .contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(task("task-delete"))))
                .andReturn().getResponse().getContentAsString();
        Map<String, Object> created = mapper.readValue(createdJson, new TypeReference<>() {});
        long revision = ((Number) created.get("revision")).longValue();
        mvc.perform(delete("/api/task-workspaces/task-delete").param("revision", String.valueOf(revision + 1)))
                .andExpect(status().isConflict());
        mvc.perform(delete("/api/task-workspaces/task-delete").param("revision", String.valueOf(revision)))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/task-workspaces/task-delete")).andExpect(status().isNotFound());
    }

    private Map<String, Object> task(String id) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("id", id);
        value.put("title", "阅读 A 和 B");
        value.put("paperIds", List.of("A", "B"));
        value.put("focusedPaperId", "A");
        value.put("messages", List.of(Map.of("id", "m-1", "role", "user", "content", "问题")));
        value.put("notes", List.of(Map.of("id", "n-1", "content", "我的理解")));
        value.put("artifacts", List.of(Map.of("id", "a-1", "title", "比较表")));
        value.put("activeActivity", Map.of("id", "reading-A", "snapshot", Map.of(
                "paperIds", List.of("A"), "primaryPaperId", "A", "strictScope", true)));
        return value;
    }
}
