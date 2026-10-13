package com.ai.assistant.backend_java.controller;

import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.PaperRepository;
import com.ai.assistant.backend_java.service.TaskWorkspaceService;
import com.ai.assistant.backend_java.service.MaterialProcessingService;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.transaction.annotation.Transactional;

/** Task-scoped recovery of server files; IndexedDB is an optional local cache. */
@RestController
@RequestMapping("/api/task-workspaces/{taskId}/materials")
@CrossOrigin(origins = {"http://localhost:5173", "http://127.0.0.1:5173"}, allowCredentials = "true")
public class TaskMaterialController {
    private final TaskWorkspaceService tasks;
    private final PaperRepository papers;
    private final ObjectMapper mapper;
    private final MaterialProcessingService processing;
    public TaskMaterialController(TaskWorkspaceService tasks, PaperRepository papers, ObjectMapper mapper, MaterialProcessingService processing) {
        this.tasks = tasks; this.papers = papers; this.mapper = mapper; this.processing = processing;
    }
    @GetMapping
    public List<Map<String, Object>> list(@PathVariable String taskId) {
        return ((List<?>) tasks.get(taskId).get("paperIds")).stream().map(id -> {
            Paper paper = papers.findById(String.valueOf(id)).orElse(null);
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", id);
            item.put("filename", paper == null ? String.valueOf(id) : paper.getFileName());
            item.put("title", item.get("filename"));
            item.put("fileAvailable", paper != null && paper.getPdfBytes() != null);
            item.put("processingStatus", paper == null || paper.getProcessingStatus() == null ? "unknown" : paper.getProcessingStatus());
            if (paper != null && paper.getAnalysisJson() != null) {
                try {
                    Map<String, Object> analysis = mapper.readValue(paper.getAnalysisJson(), new TypeReference<Map<String, Object>>() {});
                    if (analysis.get("externalSource") instanceof Map<?, ?> source) item.put("externalSource", source);
                } catch (java.io.IOException ignored) { }
            }
            return item;
        }).toList();
    }
    @GetMapping("/{paperId}/file")
    public ResponseEntity<byte[]> file(@PathVariable String taskId, @PathVariable String paperId) {
        Paper paper = owned(taskId, paperId);
        if (paper.getPdfBytes() == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                "metadata".equals(paper.getProcessingStatus()) ? "此条目仅保存文献元数据，全文尚不可用，请查看来源页或上传 PDF" : "论文文件尚不可用，请重新上传 PDF");
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_PDF).body(paper.getPdfBytes());
    }
    @GetMapping("/{paperId}/analysis")
    public Map<String, Object> analysis(@PathVariable String taskId, @PathVariable String paperId) throws java.io.IOException {
        Paper paper = owned(taskId, paperId);
        if (paper.getAnalysisJson() == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "论文解析结果尚未保存");
        return processing.status(paperId);
    }

    @GetMapping("/{paperId}/processing")
    public Map<String, Object> processingStatus(@PathVariable String taskId, @PathVariable String paperId) {
        owned(taskId, paperId); return processing.status(paperId);
    }

    @PostMapping("/{paperId}/parse")
    public Map<String, Object> retryParse(@PathVariable String taskId, @PathVariable String paperId) {
        owned(taskId, paperId); return processing.request(paperId, false);
    }

    @PostMapping("/{paperId}/overview")
    public Map<String, Object> generateOverview(@PathVariable String taskId, @PathVariable String paperId) {
        owned(taskId, paperId); return processing.request(paperId, true);
    }
    private Paper owned(String taskId, String paperId) {
        if (!((List<?>) tasks.get(taskId).get("paperIds")).contains(paperId))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "论文不属于当前任务");
        return papers.findById(paperId).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "论文记录不存在"));
    }

    @PutMapping(value = "/{paperId}/cache", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Transactional
    public Map<String, Object> importLegacyCache(@PathVariable String taskId, @PathVariable String paperId,
            @RequestParam("file") MultipartFile file, @RequestParam("analysis") String analysis) throws java.io.IOException {
        owned(taskId, paperId);
        Paper paper = papers.lockById(paperId).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        Map<String, Object> parsed = mapper.readValue(analysis, new TypeReference<Map<String, Object>>() {});
        if (!paperId.equals(parsed.get("pdfId")) || !"success".equals(parsed.get("status"))
                || !java.util.Objects.equals(paper.getFileName(), file.getOriginalFilename()))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "缓存与原论文标识或文件名不匹配");
        byte[] bytes = file.getBytes();
        if (bytes.length < 5 || !new String(bytes, 0, 5, java.nio.charset.StandardCharsets.US_ASCII).equals("%PDF-"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "缓存不是PDF文件");
        if (paper.getPdfBytes() != null && !java.util.Arrays.equals(bytes, paper.getPdfBytes()))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "服务端已保存不同文件，不能用缓存覆盖");
        if (paper.getPdfBytes() == null) paper.setPdfBytes(bytes);
        if (paper.getAnalysisJson() == null) paper.setAnalysisJson(mapper.writeValueAsString(parsed));
        papers.save(paper);
        return Map.of("status", "success", "pdfId", paperId);
    }
}
