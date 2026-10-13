package com.ai.assistant.backend_java.controller;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.http.MediaType;
import com.ai.assistant.backend_java.repository.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;
@SpringBootTest @AutoConfigureMockMvc
class TaskDocumentIdentityControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired TaskWorkspaceRepository tasks;
    @Autowired TaskMigrationSnapshotRepository backups;
    @BeforeEach void clear() { backups.deleteAll(); tasks.deleteAll(); }
    Map<String,Object> read(String text) throws Exception { return mapper.readValue(text, new TypeReference<>(){}); }
    Map<String,Object> create() throws Exception {
        return read(mvc.perform(post("/api/task-workspaces").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(Map.of(
            "id", "identity-test", "title", "旧任务", "paperIds", List.of("A"),
            "notes", List.of(Map.of("content", "相同正文", "versions", List.of(Map.of("text", "旧版")), "sources", List.of(Map.of("pdfId", "A"))),
                            Map.of("content", "相同正文")),
            "artifacts", List.of(Map.of("artifactId", "existing-artifact", "text", "完整成果"))
        )))).andExpect(status().isCreated()).andReturn().getResponse().getContentAsString());
    }
    @Test void preservesFullDocumentsAndBackupAndDoesNotWriteOnReplay() throws Exception {
        var original = create();
        var result = read(mvc.perform(post("/api/task-workspaces/identity-test/documents/identify").contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(Map.of("revision", original.get("revision")))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.identified").value(2)).andReturn().getResponse().getContentAsString());
        var updated = (Map<?,?>)result.get("task");
        var notes = (List<?>)updated.get("notes");
        assertNotEquals(((Map<?,?>)notes.get(0)).get("id"), ((Map<?,?>)notes.get(1)).get("id"));
        for (int index=0; index<2; index++) {
            var document = new LinkedHashMap<>((Map<?,?>)notes.get(index)); document.remove("id");
            assertEquals(((List<?>)original.get("notes")).get(index), document);
        }
        assertEquals(original.get("artifacts"), updated.get("artifacts"));
        mvc.perform(post("/api/task-workspaces/identity-test/documents/identify").contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(Map.of("revision", updated.get("revision")))))
            .andExpect(jsonPath("$.identified").value(0)).andExpect(jsonPath("$.task.revision").value(updated.get("revision")));
        var savedBackup = read(mvc.perform(get("/api/task-workspaces/identity-test/migration-backups/" + result.get("backupId")))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
        assertEquals(original, savedBackup);
        mvc.perform(get("/api/task-workspaces/wrong-task/migration-backups/" + result.get("backupId"))).andExpect(status().isNotFound());
        assertEquals(1, backups.count());
    }
    @Test void staleClientCannotChangeIdentityOrCreateBackup() throws Exception {
        var original = create();
        mvc.perform(post("/api/task-workspaces/identity-test/documents/identify").contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(Map.of("revision", ((Number)original.get("revision")).longValue()+1))))
            .andExpect(status().isConflict());
        assertEquals(0, backups.count());
        assertEquals(original, read(mvc.perform(get("/api/task-workspaces/identity-test")).andReturn().getResponse().getContentAsString()));
    }
    @Test void failureAfterBackupWriteRollsBackBackupAndIdentityTogether() throws Exception {
        create();
        var entity = tasks.findById("identity-test").orElseThrow();
        var damaged = read(entity.getPayloadJson()); damaged.put("focusedPaperId", "not-in-task");
        entity.setPayloadJson(mapper.writeValueAsString(damaged)); entity = tasks.saveAndFlush(entity);
        String before = entity.getPayloadJson();
        mvc.perform(post("/api/task-workspaces/identity-test/documents/identify").contentType(MediaType.APPLICATION_JSON)
            .content(mapper.writeValueAsString(Map.of("revision", entity.getRevision())))).andExpect(status().isBadRequest());
        assertEquals(0, backups.count());
        assertEquals(before, tasks.findById("identity-test").orElseThrow().getPayloadJson());
    }
}
