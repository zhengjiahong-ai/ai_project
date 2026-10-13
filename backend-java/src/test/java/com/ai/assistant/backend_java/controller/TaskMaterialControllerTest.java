package com.ai.assistant.backend_java.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.mockito.Mockito.*;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.RestTemplate;
import org.springframework.mock.web.MockMultipartFile;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.PaperRepository;
import com.ai.assistant.backend_java.repository.TaskWorkspaceRepository;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.ai.assistant.backend_java.service.PdfService;

@SpringBootTest
@AutoConfigureMockMvc
class TaskMaterialControllerTest {
    @Autowired MockMvc mvc;
    @Autowired PaperRepository papers;
    @Autowired TaskWorkspaceRepository tasks;
    @Autowired TaskWorkspaceService workspace;
    @Autowired PdfService pdf;
    @MockBean RestTemplate provider;
    @BeforeEach void setup() { tasks.deleteAll(); papers.deleteAll(); reset(provider); }

    @Test void fileAndAnalysisPersistAndRemainTaskScoped() throws Exception {
        Paper paper = new Paper();
        paper.setId("A"); paper.setFileName("title.pdf"); paper.setPdfBytes("%PDF-test".getBytes());
        paper.setAnalysisJson("{\"pdfId\":\"A\",\"title\":\"Title\"}");
        papers.saveAndFlush(paper);
        workspace.create(Map.of("id", "task", "paperIds", List.of("A")));
        workspace.create(Map.of("id", "other", "paperIds", List.of()));
        mvc.perform(get("/api/task-workspaces/task/materials")).andExpect(status().isOk()).andExpect(jsonPath("$[0].fileAvailable").value(true));
        mvc.perform(get("/api/task-workspaces/task/materials/A/file")).andExpect(status().isOk()).andExpect(content().bytes("%PDF-test".getBytes()));
        mvc.perform(get("/api/task-workspaces/task/materials/A/analysis")).andExpect(status().isOk()).andExpect(jsonPath("$.title").value("Title"));
        mvc.perform(get("/api/task-workspaces/other/materials/A/file")).andExpect(status().isNotFound());
        mvc.perform(get("/api/task-workspaces/other/materials/A/analysis")).andExpect(status().isNotFound());
        verifyNoInteractions(provider);
    }

    @Test void duplicateUploadReusesAnalysisAndSameFilenameDifferentContentHasDifferentIdentity() throws Exception {
        when(provider.postForObject(anyString(), any(), eq(Map.class))).thenAnswer(call -> {
            var entity = (org.springframework.http.HttpEntity<?>) call.getArgument(1);
            var body = (org.springframework.util.MultiValueMap<?, ?>) entity.getBody();
            var file = (org.springframework.core.io.ByteArrayResource) body.get("file").getFirst();
            return new java.util.LinkedHashMap<>(Map.of("status", "success", "pdfId", file.getFilename()));
        });
        var one = new MockMultipartFile("file", "same.pdf", "application/pdf", "%PDF-one".getBytes());
        var two = new MockMultipartFile("file", "same.pdf", "application/pdf", "%PDF-two".getBytes());
        var first = pdf.analyzePdf(one);
        org.junit.jupiter.api.Assertions.assertEquals(first, pdf.analyzePdf(one));
        org.junit.jupiter.api.Assertions.assertNotEquals(first.get("pdfId"), pdf.analyzePdf(two).get("pdfId"));
        org.junit.jupiter.api.Assertions.assertArrayEquals(one.getBytes(), papers.findById((String)first.get("pdfId")).orElseThrow().getPdfBytes());
        verify(provider, times(2)).postForObject(anyString(), any(), eq(Map.class));
    }

    @Test void processingRoutesRequireTaskMaterialOwnershipBeforeScheduling() throws Exception {
        Paper paper = new Paper(); paper.setId("A"); paper.setPdfBytes("%PDF-test".getBytes());
        paper.setAnalysisJson("{\"status\":\"success\",\"pdfId\":\"A\",\"ragIndexed\":false}");
        paper.setProcessingStatus("interrupted"); paper.setAiAnalysisStatus("not_requested"); papers.saveAndFlush(paper);
        workspace.create(Map.of("id", "task", "paperIds", List.of("A")));
        workspace.create(Map.of("id", "other", "paperIds", List.of()));
        mvc.perform(get("/api/task-workspaces/task/materials/A/processing"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.readingReady").value(true))
                .andExpect(jsonPath("$.questionReady").value(false)).andExpect(jsonPath("$.processingStatus").value("interrupted"));
        mvc.perform(get("/api/task-workspaces/other/materials/A/processing")).andExpect(status().isNotFound());
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/task-workspaces/other/materials/A/parse"))
                .andExpect(status().isNotFound());
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/task-workspaces/other/materials/A/overview"))
                .andExpect(status().isNotFound());
        verifyNoInteractions(provider);
    }

    @Test void legacyImportIsIdempotentAndCannotOverwriteDifferentBytes() throws Exception {
        Paper paper = new Paper(); paper.setId("old.pdf"); paper.setFileName("old.pdf"); papers.saveAndFlush(paper);
        workspace.create(Map.of("id", "task", "paperIds", List.of("old.pdf")));
        var file = new MockMultipartFile("file", "old.pdf", "application/pdf", "%PDF-old".getBytes());
        for (int n = 0; n < 2; n++) {
            mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart("/api/task-workspaces/task/materials/old.pdf/cache")
                .file(file).param("analysis", "{\"status\":\"success\",\"pdfId\":\"old.pdf\"}")
                .with(request -> { request.setMethod("PUT"); return request; })).andExpect(status().isOk());
        }
        var different = new MockMultipartFile("file", "old.pdf", "application/pdf", "%PDF-different".getBytes());
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart("/api/task-workspaces/task/materials/old.pdf/cache")
            .file(different).param("analysis", "{\"status\":\"success\",\"pdfId\":\"old.pdf\"}")
            .with(request -> { request.setMethod("PUT"); return request; })).andExpect(status().isConflict());
        mvc.perform(get("/api/task-workspaces/task/materials/old.pdf/file")).andExpect(content().bytes(file.getBytes()));
        verifyNoInteractions(provider);
    }
}
