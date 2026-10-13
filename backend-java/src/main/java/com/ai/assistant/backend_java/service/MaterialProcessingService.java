package com.ai.assistant.backend_java.service;

import com.ai.assistant.backend_java.model.Paper;
import com.ai.assistant.backend_java.repository.PaperRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PreDestroy;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

/** The PDF is durable before any extraction or optional model work starts. */
@Service
public class MaterialProcessingService {
    private final PaperRepository papers;
    private final ObjectMapper mapper;
    private final RestTemplate http;
    private final String pythonUrl;
    private final ExecutorService workers = new ThreadPoolExecutor(2, 2, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(16), runnable -> {
                Thread thread = new Thread(runnable, "material-processing");
                thread.setDaemon(true); return thread;
            }, new ThreadPoolExecutor.AbortPolicy());

    public MaterialProcessingService(PaperRepository papers, ObjectMapper mapper, RestTemplate http,
            @Value("${PYTHON_URL:http://localhost:8000/api}") String pythonUrl) {
        this.papers = papers; this.mapper = mapper; this.http = http; this.pythonUrl = pythonUrl;
    }

    public synchronized Map<String, Object> upload(MultipartFile file) {
        final byte[] bytes;
        final String id;
        try {
            bytes = file.getBytes();
            if (bytes.length < 5 || !"%PDF-".equals(new String(bytes, 0, 5, StandardCharsets.US_ASCII)))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "请选择 PDF 文件");
            id = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)) + ".pdf";
        } catch (ResponseStatusException error) { throw error;
        } catch (Exception error) { throw new IllegalStateException("无法读取上传文件", error); }
        Paper existing = papers.findById(id).orElse(null);
        if (existing != null && existing.getPdfBytes() != null) return view(existing);
        Paper paper = existing == null ? new Paper() : existing;
        paper.setId(id); paper.setFileName(file.getOriginalFilename()); paper.setPdfBytes(bytes);
        if (paper.getAnalysisJson() == null) {
            paper.setAnalysisJson(json(Map.of("status", "success", "pdfId", id,
                    "title", Objects.toString(file.getOriginalFilename(), "论文"),
                    "paper_skeleton", Map.of(), "paper_structure", Map.of("sections", List.of()),
                    "ragIndexed", false, "ragChunkCount", 0)));
            paper.setAiAnalysisStatus("not_requested");
            paper.setProcessingStatus("queued");
            paper.setProcessingAttemptId(UUID.randomUUID().toString());
            papers.saveAndFlush(paper);
            schedule(paper, false);
        } else papers.saveAndFlush(paper);
        return view(papers.findById(id).orElseThrow());
    }

    public synchronized Map<String, Object> request(String id, boolean ai) {
        Paper paper = papers.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        if (paper.getPdfBytes() == null)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "请先恢复论文文件");
        if (List.of("queued", "parsing").contains(Objects.toString(paper.getProcessingStatus(), ""))
                || "running".equals(paper.getAiAnalysisStatus())) return view(paper);
        Map<String, Object> analysis = read(paper);
        if (ai) {
            if (!Boolean.TRUE.equals(analysis.get("ragIndexed")))
                throw new ResponseStatusException(HttpStatus.CONFLICT, "论文正文尚未就绪，请先完成解析");
            if ("completed".equals(paper.getAiAnalysisStatus()) || paper.getAiAnalysisStatus() == null)
                return view(paper);
            paper.setAiAnalysisStatus("running");
        } else {
            if (Boolean.TRUE.equals(analysis.get("ragIndexed"))) return view(paper);
            paper.setProcessingStatus("queued");
        }
        paper.setProcessingError(null);
        paper.setProcessingAttemptId(UUID.randomUUID().toString());
        papers.saveAndFlush(paper);
        schedule(paper, ai);
        return view(papers.findById(id).orElseThrow());
    }

    private void schedule(Paper paper, boolean ai) {
        String id = paper.getId(), attempt = paper.getProcessingAttemptId();
        try { workers.execute(() -> run(id, attempt, ai)); }
        catch (RejectedExecutionException error) { finish(id, attempt, ai, null, "处理队列已满，请稍后重试"); }
    }

    private void run(String id, String attempt, boolean ai) {
        byte[] bytes = start(id, attempt, ai);
        if (bytes == null) return;
        try {
            var body = new LinkedMultiValueMap<String, Object>();
            body.add("file", new ByteArrayResource(bytes) {
                @Override public String getFilename() { return id; }
            });
            var headers = new HttpHeaders(); headers.setContentType(MediaType.MULTIPART_FORM_DATA);
            @SuppressWarnings("unchecked")
            Map<String, Object> result = http.postForObject(pythonUrl + (ai ? "/analyze-pdf" : "/parse-pdf"),
                    new HttpEntity<>(body, headers), Map.class);
            if (result == null || !"success".equals(result.get("status")))
                throw new IllegalStateException("解析服务未返回结果");
            finish(id, attempt, ai, result, null);
        } catch (Exception error) {
            finish(id, attempt, ai, null, ai ? "论文概览生成失败，可重试；原文仍可阅读" : "论文解析失败，可重试；原文仍可阅读");
        }
    }

    private synchronized byte[] start(String id, String attempt, boolean ai) {
        Paper paper = papers.findById(id).orElse(null);
        if (paper == null || !attempt.equals(paper.getProcessingAttemptId())) return null;
        if (!ai) paper.setProcessingStatus("parsing");
        papers.saveAndFlush(paper);
        return paper.getPdfBytes();
    }

    private synchronized void finish(String id, String attempt, boolean ai, Map<String, Object> result, String error) {
        Paper paper = papers.findById(id).orElse(null);
        if (paper == null || !attempt.equals(paper.getProcessingAttemptId())) return;
        if (result != null) {
            // Storage identity belongs to Java, even when the extraction service normalizes it.
            result = new LinkedHashMap<>(result); result.put("pdfId", id);
            paper.setAnalysisJson(json(result));
            paper.setProcessingStatus(Boolean.TRUE.equals(result.get("ragIndexed")) ? "ready" : "degraded");
            paper.setAiAnalysisStatus(Objects.toString(result.get("aiAnalysisStatus"), ai ? "completed" : "not_requested"));
        } else if (ai) paper.setAiAnalysisStatus("failed");
        else paper.setProcessingStatus("failed");
        paper.setProcessingError(error);
        papers.saveAndFlush(paper);
    }

    public synchronized Map<String, Object> status(String id) {
        return view(papers.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    private Map<String, Object> view(Paper paper) {
        Map<String, Object> result = new LinkedHashMap<>(read(paper));
        result.put("status", "success"); result.put("pdfId", paper.getId());
        result.put("readingReady", paper.getPdfBytes() != null);
        result.put("questionReady", Boolean.TRUE.equals(result.get("ragIndexed")));
        result.put("processingStatus", Objects.toString(paper.getProcessingStatus(),
                Boolean.TRUE.equals(result.get("ragIndexed")) ? "ready" : "degraded"));
        result.put("aiAnalysisStatus", Objects.toString(paper.getAiAnalysisStatus(), "completed"));
        if (paper.getProcessingError() != null) result.put("processingError", paper.getProcessingError());
        return result;
    }

    private Map<String, Object> read(Paper paper) {
        if (paper.getAnalysisJson() == null) return new LinkedHashMap<>();
        try { return mapper.readValue(paper.getAnalysisJson(), new TypeReference<Map<String, Object>>() {}); }
        catch (Exception error) { throw new IllegalStateException("无法读取论文解析记录", error); }
    }
    private String json(Map<String, Object> value) {
        try { return mapper.writeValueAsString(value); }
        catch (Exception error) { throw new IllegalStateException("无法保存论文解析记录", error); }
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void recoverInterrupted() {
        for (Paper paper : papers.findByProcessingStatusInOrAiAnalysisStatusIn(List.of("queued", "parsing"), List.of("running"))) {
            if (List.of("queued", "parsing").contains(Objects.toString(paper.getProcessingStatus(), "")))
                paper.setProcessingStatus("interrupted");
            if ("running".equals(paper.getAiAnalysisStatus())) paper.setAiAnalysisStatus("interrupted");
            paper.setProcessingAttemptId(UUID.randomUUID().toString());
            paper.setProcessingError("服务重启中断了处理，可重试；原文仍可阅读");
            papers.saveAndFlush(paper);
        }
    }
    @PreDestroy public void close() { workers.shutdownNow(); }
}
