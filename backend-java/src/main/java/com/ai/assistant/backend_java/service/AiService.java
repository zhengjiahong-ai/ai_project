package com.ai.assistant.backend_java.service;

import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

/**
 * Facade over {@link PdfService}, {@link ResearchService}, and {@link AgentGatewayService}.
 * Kept for backward compatibility — new code should inject the specialized services directly.
 */
@Service
public class AiService {

    @Autowired
    private PdfService pdfService;

    @Autowired
    private ResearchService researchService;

    @Autowired
    private AgentGatewayService agentService;

    // ── PDF / Reader ──────────────────────────────────────────────────────

    public Map<String, Object> analyzePdf(MultipartFile file)                     { return pdfService.analyzePdf(file); }
    public Map<String, Object> explainTerm(Map<String, Object> request)           { return pdfService.explainTerm(request); }
    public Map<String, Object> chat(Map<String, Object> request)                  { return pdfService.chat(request); }
    public Map<String, Object> translatePage(Map<String, Object> request)         { return pdfService.translatePage(request); }
    public Map<String, Object> getChatHistory(String id)                          { return pdfService.getChatHistory(id); }
    public Map<String, Object> criticalReading(String pdfId)                      { return pdfService.criticalReading(pdfId); }
    public Map<String, Object> socraticQuestions(Map<String, Object> request)     { return pdfService.socraticQuestions(request); }
    public Map<String, Object> startSocraticSession(Map<String, Object> request)  { return pdfService.startSocraticSession(request); }
    public Map<String, Object> answerSocraticSession(Map<String, Object> request) { return pdfService.answerSocraticSession(request); }
    public Map<String, Object> backgroundKnowledge(Map<String, Object> request)   { return pdfService.backgroundKnowledge(request); }

    // ── Research Tasks ────────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> createResearchTask(Map<String, Object> r)        { return researchService.createResearchTask(r); }
    public ResponseEntity<Map<String, Object>> previewResearchBrief(Map<String, Object> r)       { return researchService.previewResearchBrief(r); }
    public ResponseEntity<Map<String, Object>> getResearchTask(String id)                        { return researchService.getResearchTask(id); }
    public ResponseEntity<Map<String, Object>> getLatestResearchTask(String pdfId)               { return researchService.getLatestResearchTask(pdfId); }
    public ResponseEntity<Map<String, Object>> cancelResearchTask(String id)                     { return researchService.cancelResearchTask(id); }
    public ResponseEntity<Map<String, Object>> reviewResearchPlan(String id, Map<String, Object> r) { return researchService.reviewResearchPlan(id, r); }
    public ResponseEntity<Map<String, Object>> reviewResearchFinal(String id, Map<String, Object> r) { return researchService.reviewResearchFinal(id, r); }
    public ResponseEntity<Map<String, Object>> getTrace(String id)                               { return researchService.getTrace(id); }

    // ── Agent Projects ────────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> createAgentProject(Map<String, Object> r)                       { return agentService.createAgentProject(r); }
    public ResponseEntity<Map<String, Object>> listAgentProjects()                                              { return agentService.listAgentProjects(); }
    public ResponseEntity<Map<String, Object>> getAgentProject(String id)                                       { return agentService.getAgentProject(id); }
    public ResponseEntity<Map<String, Object>> updateAgentProject(String id, Map<String, Object> r)             { return agentService.updateAgentProject(id, r); }
    public ResponseEntity<Map<String, Object>> deleteAgentProject(String id)                                    { return agentService.deleteAgentProject(id); }
    public ResponseEntity<Map<String, Object>> addAgentProjectPapers(String id, Map<String, Object> r)          { return agentService.addAgentProjectPapers(id, r); }
    public ResponseEntity<Map<String, Object>> removeAgentProjectPaper(String pid, String pdfId)                { return agentService.removeAgentProjectPaper(pid, pdfId); }
    public ResponseEntity<Map<String, Object>> createAgentTask(String id, Map<String, Object> r)                { return agentService.createAgentTask(id, r); }
    public ResponseEntity<Map<String, Object>> createAgentRun(String id, Map<String, Object> r)                 { return agentService.createAgentRun(id, r); }
    public ResponseEntity<Map<String, Object>> getAgentWorkspace(String id)                                     { return agentService.getAgentWorkspace(id); }
    public ResponseEntity<Map<String, Object>> getLatestAgentTask(String id)                                    { return agentService.getLatestAgentTask(id); }
    public ResponseEntity<Map<String, Object>> listAgentProjectTasks(String id, Integer limit)                  { return agentService.listAgentProjectTasks(id, limit); }
    public ResponseEntity<Map<String, Object>> getAgentTask(String id)                                          { return agentService.getAgentTask(id); }
    public ResponseEntity<Map<String, Object>> getAgentRun(String id)                                           { return agentService.getAgentRun(id); }
    public ResponseEntity<Map<String, Object>> getAgentRunArtifacts(String id)                                  { return agentService.getAgentRunArtifacts(id); }
    public ResponseEntity<Map<String, Object>> getAgentRunTimeline(String id)                                   { return agentService.getAgentRunTimeline(id); }
    public ResponseEntity<Map<String, Object>> cancelAgentTask(String id)                                       { return agentService.cancelAgentTask(id); }
    public ResponseEntity<Map<String, Object>> reviewAgentRunPlan(String id, Map<String, Object> r)             { return agentService.reviewAgentRunPlan(id, r); }
    public ResponseEntity<Map<String, Object>> reviewAgentPlan(String id, Map<String, Object> r)                { return agentService.reviewAgentPlan(id, r); }
    public ResponseEntity<Map<String, Object>> reviewAgentRunFinal(String id, Map<String, Object> r)            { return agentService.reviewAgentRunFinal(id, r); }
    public ResponseEntity<Map<String, Object>> reviewAgentFinal(String id, Map<String, Object> r)               { return agentService.reviewAgentFinal(id, r); }
    public ResponseEntity<Map<String, Object>> getAgentTrace(String id)                                         { return agentService.getAgentTrace(id); }
    public ResponseEntity<Map<String, Object>> answerAgentClarification(String id, Map<String, Object> r)       { return agentService.answerAgentClarification(id, r); }

    // ── Code Execution ────────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> uploadCodeExecutionArtifact(MultipartFile file)                   { return agentService.uploadCodeExecutionArtifact(file); }
    public ResponseEntity<Map<String, Object>> createCodeExecutionJob(Map<String, Object> r)                     { return agentService.createCodeExecutionJob(r); }
    public ResponseEntity<Map<String, Object>> listCodeExecutionJobs()                                           { return agentService.listCodeExecutionJobs(); }
    public ResponseEntity<Map<String, Object>> getCodeExecutionJob(String id)                                    { return agentService.getCodeExecutionJob(id); }
    public ResponseEntity<Map<String, Object>> reviewCodeExecution(String id, Map<String, Object> r)             { return agentService.reviewCodeExecution(id, r); }
    public ResponseEntity<Map<String, Object>> reviewCodePublication(String id, Map<String, Object> r)           { return agentService.reviewCodePublication(id, r); }

    // ── Paper Draft ───────────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> generatePaperDraft(Map<String, Object> r)                         { return agentService.generatePaperDraft(r); }

    // ── Research Monitors ─────────────────────────────────────────────────

    public ResponseEntity<Map<String, Object>> createResearchMonitor(Map<String, Object> r)                      { return agentService.createResearchMonitor(r); }
    public ResponseEntity<Map<String, Object>> listResearchMonitors()                                            { return agentService.listResearchMonitors(); }
    public ResponseEntity<Map<String, Object>> checkResearchMonitor(String id)                                   { return agentService.checkResearchMonitor(id); }
    public ResponseEntity<Map<String, Object>> getResearchMonitorDigest(String id)                               { return agentService.getResearchMonitorDigest(id); }
    public ResponseEntity<Map<String, Object>> deactivateResearchMonitor(String id)                              { return agentService.deactivateResearchMonitor(id); }

    public ResponseEntity<Map<String, Object>> createAgentGraph(Map<String, Object> r)                           { return agentService.createAgentGraph(r); }
    public ResponseEntity<Map<String, Object>> resumeAgentGraph(String id, Map<String, Object> r)                { return agentService.resumeAgentGraph(id, r); }
    public ResponseEntity<Map<String, Object>> getAgentGraph(String id)                                           { return agentService.getAgentGraph(id); }
}
