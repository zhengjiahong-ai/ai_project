package com.ai.assistant.backend_java.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TaskResearchService {
    private static final String ENGINE_V2 = "deep-research-v2";
    private static final String ENGINE_LEGACY = "legacy-v1";
    private static final int CONTRACT_V2 = 2;
    private static final Set<String> VALID_SOURCE_POLICIES = Set.of("task_only", "academic_external", "external_only");
    private static final Set<String> VALID_BUDGET_PROFILES = Set.of("standard", "extended");
    private static final Set<String> VALID_OUTPUT_KINDS = Set.of(
            "direction_survey", "paper_comparison", "claim_verification", "experiment_design", "research_entry", "general");

    private final TaskWorkspaceService tasks;
    private final ResearchService research;
    @org.springframework.beans.factory.annotation.Autowired(required = false)
    private com.ai.assistant.backend_java.repository.PaperRepository paperRepository;
    @org.springframework.beans.factory.annotation.Autowired(required = false)
    private MaterialProcessingService materialProcessing;

    public TaskResearchService(TaskWorkspaceService tasks, ResearchService research) {
        this.tasks = tasks;
        this.research = research;
    }

    public Map<String, Object> capabilities(String taskId) {
        tasks.get(taskId);
        return requireSuccess(research.researchCapabilities());
    }

    public Map<String, Object> syncPublication(String taskId, String runId) {
        requireV2Owner(taskId, runId);
        Map<String, Object> result = getV2(taskId, runId);
        Map<?, ?> state = (Map<?, ?>) result.get("task");
        Map<?, ?> report = state.get("report") instanceof Map<?, ?> value ? value : Map.of();
        if (!(report.get("versionId") instanceof String version) || version.isBlank()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "报告尚未保存");
        }
        Map<?, ?> workspace = (Map<?, ?>) result.get("workspace");
        boolean saved = ((List<?>) workspace.get("artifacts")).stream().anyMatch(value -> value instanceof Map<?, ?> artifact
                && runId.equals(artifact.get("sourceRunId")) && version.equals(artifact.get("reportVersionId")));
        if (!saved) throw new ResponseStatusException(HttpStatus.CONFLICT, "报告发布尚未确认");
        return Map.of("status", "success", "runId", runId, "reportVersionId", version);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> addSource(String taskId, String runId, String sourceId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        Map<String, Object> run = findV2Run(taskId, runId);
        Map<?, ?> policy = (Map<?, ?>) run.get("sourcePolicy");
        if (policy == null || !Set.of("academic_external", "external_only").contains(policy.get("mode"))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "本次研究未允许外部文献");
        }
        Map<String, Object> exported = requireSuccess(research.exportV2Source(runId, sourceId));
        if (!(exported.get("source") instanceof Map<?, ?> source) || !sourceId.equals(source.get("sourceId"))) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "来源身份不匹配");
        }
        Map<String, Object> result = tasks.addResearchSource(taskId, runId, sourceId, input, (Map<String, Object>) source);
        // Start ordinary PDF parsing after the task transaction has committed; never run AI analysis here.
        if (materialProcessing != null && "fulltext".equals(source.get("accessLevel"))) {
            materialProcessing.request(String.valueOf(result.get("paperId")), false);
        }
        return result;
    }

    // === Unified start: dispatches to legacy or v2 based on input ===
    public Map<String, Object> startUnified(String taskId, Map<String, Object> input) {
        // If input contains v2 markers (engineVersion, contractVersion, materialSelection, sourcePolicy), use v2
        boolean isV2 = input.containsKey("engineVersion") || input.containsKey("contractVersion")
                || input.containsKey("materialSelection") || input.containsKey("sourcePolicy")
                || input.containsKey("budgetProfile") || input.containsKey("outputKind");
        if (isV2) {
            return startV2(taskId, input);
        }
        return startLegacy(taskId, input);
    }

    // === Unified GET: dispatches by stored engine version ===
    public Map<String, Object> getUnified(String taskId, String runId) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        String engine = resolveEngine(run);
        if (ENGINE_V2.equals(engine)) {
            return getV2(taskId, runId);
        }
        return getLegacy(taskId, runId);
    }

    // === Unified resume: optional body, dispatches by engine ===
    public Map<String, Object> resumeUnified(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        String engine = resolveEngine(run);
        if (ENGINE_V2.equals(engine)) {
            return resumeV2(taskId, runId, input);
        }
        // Legacy resume ignores body
        return resumeLegacy(taskId, runId);
    }

    // === Unified cancel: optional body, dispatches by engine ===
    public Map<String, Object> cancelUnified(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        String engine = resolveEngine(run);
        if (ENGINE_V2.equals(engine)) {
            return cancelV2(taskId, runId, input);
        }
        return cancelLegacy(taskId, runId);
    }

    // === V2-only actions on unified path (legacy returns 400) ===
    public Map<String, Object> pauseUnified(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        requireV2Engine(run);
        return pauseV2(taskId, runId, input);
    }

    public Map<String, Object> clarifyUnified(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        requireV2Engine(run);
        return clarifyV2(taskId, runId, input);
    }

    public Map<String, Object> planUnified(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        requireV2Engine(run);
        return planV2(taskId, runId, input);
    }

    public Map<String, Object> continueUnified(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        requireV2Engine(run);
        return continueV2(taskId, runId, input);
    }

    public Map<String, Object> getSourcesUnified(String taskId, String runId) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        requireV2Engine(run);
        return getV2Sources(taskId, runId);
    }

    public Map<String, Object> getEventsUnified(String taskId, String runId) {
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        requireV2Engine(run);
        return getV2Events(taskId, runId);
    }

    // === Internal scope-check endpoint for Python ===
    /**
     * Python calls this before each model/retrieval step to verify:
     * - product task + run exist and match
     * - snapshot revision unchanged (recomputed from current material state)
     * - owned materials still present and ready
     * Fail-closed: repo unavailable, paper missing, or non-ready status => invalid.
     * No generation triggered. Returns current material state.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> scopeCheck(String taskId, String runId, Map<String, Object> input) {
        Map<String, Object> workspace = tasks.get(taskId);
        Map<String, Object> run = findRunByEitherId(taskId, runId);
        String engine = resolveEngine(run);
        if (!ENGINE_V2.equals(engine)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "scope-check仅适用于v2研究运行");
        }

        List<?> taskPapers = (List<?>) workspace.get("paperIds");
        List<?> runPapers = (List<?>) run.get("paperIds");

        // Verify all run materials still present in task
        if (runPapers == null || !taskPapers.containsAll(runPapers)) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("valid", false);
            result.put("reason", "materials_removed");
            result.put("taskId", taskId);
            result.put("runId", resolveRunId(run));
            return result;
        }

        // Fail-closed material readiness check via repository
        List<Map<String, Object>> materialStates = new ArrayList<>();
        boolean allReady = true;
        String failReason = null;

        if (paperRepository == null) {
            // Repository unavailable - cannot verify readiness; fail closed
            allReady = false;
            failReason = "repository_unavailable";
            for (Object pid : runPapers) {
                Map<String, Object> ms = new LinkedHashMap<>();
                ms.put("id", String.valueOf(pid));
                ms.put("status", "unverifiable");
                materialStates.add(ms);
            }
        } else {
            for (Object pid : runPapers) {
                String paperId = String.valueOf(pid);
                Map<String, Object> ms = new LinkedHashMap<>();
                ms.put("id", paperId);
                var paper = paperRepository.findById(paperId).orElse(null);
                if (paper == null) {
                    // Paper record missing from repository - fail closed
                    ms.put("status", "missing");
                    allReady = false;
                    if (failReason == null) failReason = "material_record_missing";
                } else {
                    String pStatus = paper.getProcessingStatus();
                    if (pStatus == null || pStatus.isBlank()) {
                        // Status absent - fail closed
                        ms.put("status", "unknown");
                        allReady = false;
                        if (failReason == null) failReason = "material_status_absent";
                    } else {
                        ms.put("status", pStatus);
                        ms.put("uploadTime", paper.getUploadTime() != null ? paper.getUploadTime().toString() : "");
                        ms.put("fileName", paper.getFileName() != null ? paper.getFileName() : "");
                        // Only explicit "ready" is accepted
                        if (!"ready".equals(pStatus)) {
                            allReady = false;
                            if (failReason == null) failReason = "material_not_ready";
                        }
                    }
                }
                materialStates.add(ms);
            }
        }

        // Recompute current snapshot hash from live material state and compare to supplied hash
        // This detects material replacement even if stored hash wasn't updated
        boolean snapshotValid = true;
        Object expectedSnapshotHash = input != null ? input.get("snapshotHash") : null;
        if (expectedSnapshotHash instanceof String expectedHash && paperRepository != null) {
            // Recompute current material versions from live repo state using same keys as creation
            List<String> currentMaterialIds = new ArrayList<>();
            for (Object pid : runPapers) currentMaterialIds.add(String.valueOf(pid));
            List<String> focusIds = run.get("focusPaperIds") instanceof List<?> fp
                    ? fp.stream().filter(f -> f instanceof String).map(f -> (String) f).toList() : List.of();
            Map<String, Object> policy = run.get("sourcePolicy") instanceof Map<?, ?> sp ? (Map<String, Object>) sp : Map.of("mode", "task_only");
            String policyMode = policy.get("mode") instanceof String pm ? pm : "task_only";

            List<Map<String, String>> currentVersions = buildMaterialVersions(currentMaterialIds);
            List<Map<String, String>> contexts;
            try { contexts = buildContextMaterials(workspace, run.get("contextRefs")); }
            catch (ResponseStatusException changed) { contexts = null; }
            String currentHash = contexts == null ? "revoked" : computeSnapshotHash(currentVersions, focusIds, policyMode, contexts);
            if (!currentHash.equals(expectedHash)) {
                snapshotValid = false;
            }
        } else if (expectedSnapshotHash instanceof String expectedHash) {
            // No repo available for recomputation; fall back to stored hash comparison
            String storedHash = run.get("snapshotHash") instanceof String sh ? sh : null;
            if (storedHash != null && !storedHash.equals(expectedHash)) {
                snapshotValid = false;
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("valid", allReady && snapshotValid);
        result.put("taskId", taskId);
        result.put("runId", resolveRunId(run));
        result.put("taskRevision", workspace.get("revision"));
        result.put("runRevision", run.get("runRevision"));
        result.put("materials", materialStates);
        result.put("snapshotValid", snapshotValid);
        if (!allReady) {
            result.put("reason", failReason != null ? failReason : "materials_not_ready");
        } else if (!snapshotValid) {
            result.put("reason", "snapshot_changed");
        }
        return result;
    }

    // === Legacy methods (preserved) ===
    private Map<String, Object> startLegacy(String id, Map<String, Object> input) {
        Map<String, Object> workspace = tasks.get(id);
        Object expected = input.get("expectedTaskRevision");
        if (!(expected instanceof Number n) || n.longValue() < 0 || n.doubleValue() != n.longValue()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "必须提供整数 expectedTaskRevision");
        }
        if (n.longValue() != ((Number) workspace.get("revision")).longValue()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已更新，请刷新后重试");
        }
        List<?> taskPapers = (List<?>) workspace.get("paperIds");
        Object rawScope = input.containsKey("allowedPaperIds") ? input.get("allowedPaperIds") : taskPapers;
        if (!(rawScope instanceof List<?> ids) || ids.isEmpty()
                || ids.stream().anyMatch(paper -> !(paper instanceof String) || !taskPapers.contains(paper))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "研究材料必须是当前任务内的非空论文集合");
        }
        List<?> scope = new ArrayList<>(new LinkedHashSet<>(ids));
        Object primary = input.get("pdfId");
        if (primary == null) primary = scope.contains(workspace.get("focusedPaperId")) ? workspace.get("focusedPaperId") : scope.getFirst();
        if (!(primary instanceof String) || !scope.contains(primary)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "主论文必须属于研究材料范围");
        }
        if (!(input.get("question") instanceof String question) || question.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "研究问题不能为空");
        }
        if (Boolean.TRUE.equals(input.get("allowExternalSearch")) || Boolean.TRUE.equals(input.get("allowWebSearch"))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "统一任务研究尚未授权外部检索");
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("question", question);
        body.put("pdfId", primary);
        body.put("allowedPaperIds", scope);
        body.put("allowExternalSearch", false);
        body.put("allowWebSearch", false);
        for (String field : List.of("userConstraints", "paperSkeleton", "briefPreview")) {
            if (input.containsKey(field)) body.put(field, input.get(field));
        }
        Map<String, Object> result = requireSuccess(research.createResearchTask(body));
        if (!(result.get("task") instanceof Map<?, ?> created)
                || !(created.get("taskId") instanceof String researchId) || researchId.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务未返回任务标识");
        }
        // researchId alias = runId for unified lookup
        Map<String, Object> run = new LinkedHashMap<>();
        run.put("researchId", researchId);
        run.put("runId", researchId); // alias
        run.put("engineVersion", ENGINE_LEGACY);
        run.put("paperIds", scope);
        run.put("primaryPaperId", primary);
        run.put("question", question);
        run.put("createdAt", Instant.now().toString());
        try {
            Map<String, Object> saved = tasks.attachResearchRun(id, expected, run);
            return Map.of("task", saved, "result", result);
        } catch (RuntimeException conflict) {
            try {
                requireSuccess(research.cancelResearchTask(researchId));
            } catch (RuntimeException cancelFailure) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "任务保存发生冲突，研究任务绑定未完成且取消未确认；请核对研究任务 " + researchId);
            }
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已更新，新建研究任务已取消，请刷新后重试");
        }
    }

    private Map<String, Object> getLegacy(String id, String researchId) {
        requireOwner(id, researchId);
        return publishLegacy(id, researchId, requireSuccess(research.getResearchTask(researchId)));
    }

    private Map<String, Object> cancelLegacy(String id, String researchId) {
        requireOwner(id, researchId);
        return publishLegacy(id, researchId, requireSuccess(research.cancelResearchTask(researchId)));
    }

    private Map<String, Object> resumeLegacy(String id, String researchId) {
        requireOwner(id, researchId);
        requireMaterials(id, researchId);
        return publishLegacy(id, researchId, requireSuccess(research.resumeResearchTask(researchId)));
    }

    // Legacy review preserved
    public Map<String, Object> reviewPlan(String id, String researchId, Map<String, Object> input) {
        requireOwner(id, researchId);
        requireMaterials(id, researchId);
        Map<String, Object> body = reviewFields(input, List.of("subQuestions", "reviewNotes"));
        return publishLegacy(id, researchId, requireSuccess(research.reviewResearchPlan(researchId, body)));
    }

    public Map<String, Object> reviewFinal(String id, String researchId, Map<String, Object> input) {
        requireOwner(id, researchId);
        return publishLegacy(id, researchId, requireSuccess(research.reviewResearchFinal(researchId, reviewFields(input, List.of("reviewNotes", "riskReviews")))));
    }

    // === V2 Start ===
    @SuppressWarnings("unchecked")
    private Map<String, Object> startV2(String taskId, Map<String, Object> input) {
        Map<String, Object> workspace = tasks.get(taskId);
        String requestId = input.get("requestId") instanceof String value ? value : "";
        if (requestId.isBlank() || requestId.length() > 128) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "必须提供有效的研究请求 ID");
        }
        // Resolve a previously bound intent before checking the task revision.
        // The first response may have been lost after attach/activation succeeded.
        for (Object item : (List<?>) workspace.get("researchRuns")) {
            if (item instanceof Map<?, ?> run && requestId.equals(run.get("requestId"))) {
                if (!input.equals(run.get("startInput"))) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "同一请求 ID 不能用于不同研究内容");
                }
                String existingId = resolveRunId((Map<String, Object>) run);
                Map<String, Object> existing = requireSuccess(research.getV2ResearchTask(existingId));
                if (existing.get("task") instanceof Map<?, ?> state && "queued".equals(state.get("status"))) {
                    existing = requireSuccess(research.resumeV2ResearchTask(existingId, Map.of(
                        "requestId", "activate:" + requestId, "expectedRunRevision", state.get("runRevision"))));
                }
                return publishV2(taskId, existingId, existing);
            }
        }
        Object expected = input.get("expectedTaskRevision");
        if (!(expected instanceof Number n) || n.longValue() < 0 || n.doubleValue() != n.longValue()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "必须提供整数 expectedTaskRevision");
        }
        long expectedRevision = n.longValue();
        if (expectedRevision != ((Number) workspace.get("revision")).longValue()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已更新，请刷新后重试");
        }
        if (!(input.get("question") instanceof String question) || question.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "研究问题不能为空");
        }

        List<?> taskPapers = (List<?>) workspace.get("paperIds");
        Map<String, Object> materialSelection = input.get("materialSelection") instanceof Map<?, ?> ms
                ? (Map<String, Object>) ms : null;
        String selectionMode = materialSelection != null && materialSelection.get("mode") instanceof String m ? m : "task_default";
        List<String> resolvedMaterialIds;
        switch (selectionMode) {
            case "task_default":
                resolvedMaterialIds = new ArrayList<>(taskPapers.stream()
                        .filter(p -> p instanceof String).map(p -> (String) p).toList());
                break;
            case "explicit":
                Object explicitIds = materialSelection != null ? materialSelection.get("materialIds") : null;
                if (!(explicitIds instanceof List<?> ids) || ids.isEmpty()
                        || ids.stream().anyMatch(p -> !(p instanceof String) || !taskPapers.contains(p))) {
                    throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                            "显式材料选择必须是非空且全部属于当前任务的论文集合");
                }
                resolvedMaterialIds = new ArrayList<>(new LinkedHashSet<>(ids.stream().map(p -> (String) p).toList()));
                break;
            case "external_only":
                resolvedMaterialIds = List.of();
                break;
            default:
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "无效的材料选择模式");
        }

        List<String> focusPaperIds = List.of();
        if (input.get("focusPaperIds") instanceof List<?> fp) {
            if (fp.stream().anyMatch(p -> !(p instanceof String) || !resolvedMaterialIds.contains(p))) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "焦点论文必须属于已选材料范围");
            }
            focusPaperIds = new ArrayList<>(new LinkedHashSet<>(fp.stream().map(p -> (String) p).toList()));
        }

        Map<String, Object> sourcePolicy = input.get("sourcePolicy") instanceof Map<?, ?> sp
                ? (Map<String, Object>) sp : Map.of("mode", "task_only");
        String policyMode = sourcePolicy.get("mode") instanceof String pm ? pm : "task_only";
        if (!VALID_SOURCE_POLICIES.contains(policyMode)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "无效的来源策略模式");
        }
        if ("external_only".equals(policyMode) && !"external_only".equals(selectionMode)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "仅外部研究模式需要显式指定材料选择策略");
        }
        if ("external_only".equals(selectionMode) && "task_only".equals(policyMode)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "仅外部研究需要开启外部文献范围");
        }
        if (resolvedMaterialIds.isEmpty() && !"external_only".equals(selectionMode)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "请添加任务材料或明确选择外部研究");
        }
        if (sourcePolicy.containsKey("hosts") || sourcePolicy.containsKey("urls")
                || sourcePolicy.containsKey("providers") || sourcePolicy.containsKey("endpoints")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "客户端不得指定来源主机、URL或Provider");
        }

        String budgetProfile = input.get("budgetProfile") instanceof String bp ? bp : "standard";
        if (!VALID_BUDGET_PROFILES.contains(budgetProfile)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "无效的预算档位");
        }
        String outputKind = input.get("outputKind") instanceof String ok ? ok : "general";
        if (!VALID_OUTPUT_KINDS.contains(outputKind)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "无效的成果类型");
        }

        String parentRunId = input.get("parentRunId") instanceof String pr ? pr : null;
        if (parentRunId != null) {
            boolean found = ((List<?>) workspace.get("researchRuns")).stream()
                    .anyMatch(r -> r instanceof Map<?, ?> run && parentRunId.equals(run.get("runId")));
            if (!found) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "父运行不属于当前任务");
        }

        // Fail-closed readiness check before creation: all materials must exist and be "ready"
        if (paperRepository == null) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "论文存储不可用，无法验证材料就绪状态");
        }
        for (String mid : resolvedMaterialIds) {
            var paper = paperRepository.findById(mid).orElse(null);
            if (paper == null) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "论文 " + mid + " 不存在，无法启动研究");
            }
            if (!"ready".equals(paper.getProcessingStatus())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "论文 " + mid + " 尚未就绪（状态: " + paper.getProcessingStatus() + "），请等待解析完成");
            }
        }

        // Build material versions with contentHash (SHA-256 of pdfBytes) as version identity
        List<Map<String, String>> materialVersions = buildMaterialVersions(resolvedMaterialIds);
        List<Map<String, String>> contextMaterials = buildContextMaterials(workspace, input.get("contextRefs"));

        Map<String, Object> upstream = new LinkedHashMap<>();
        upstream.put("requestId", input.get("requestId"));
        upstream.put("expectedTaskRevision", expectedRevision);
        upstream.put("question", question);
        upstream.put("engineVersion", ENGINE_V2);
        upstream.put("contractVersion", CONTRACT_V2);
        upstream.put("workspaceTaskId", taskId);
        upstream.put("operationKey", taskId + ":" + input.getOrDefault("requestId", ""));
        upstream.put("materialSelection", Map.of("mode", selectionMode, "materialIds", resolvedMaterialIds));
        upstream.put("focusPaperIds", focusPaperIds);
        upstream.put("sourcePolicy", Map.of("mode", policyMode));
        upstream.put("budgetProfile", budgetProfile);
        upstream.put("outputKind", outputKind);
        if (parentRunId != null) upstream.put("parentRunId", parentRunId);
        // Defer graph start until after Java persists run binding to avoid race
        upstream.put("deferStart", true);

        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put("materialRefs", resolvedMaterialIds);
        snapshot.put("focusPaperIds", focusPaperIds);
        snapshot.put("sourcePolicy", Map.of("mode", policyMode));
        snapshot.put("materialVersions", materialVersions);
        snapshot.put("contextMaterials", contextMaterials);
        String snapshotHash = computeSnapshotHash(materialVersions, focusPaperIds, policyMode, contextMaterials);
        snapshot.put("snapshotHash", snapshotHash);
        upstream.put("materialSnapshot", snapshot);

        Map<String, Object> result = requireSuccess(research.createV2ResearchTask(upstream));
        if (!(result.get("task") instanceof Map<?, ?> created)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务未返回任务");
        }
        String runId = textOrNull(created.get("runId"));
        String returnedTaskId = textOrNull(created.get("taskId"));
        if (runId == null || runId.isBlank()) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务未返回 runId");
        if (returnedTaskId != null && !taskId.equals(returnedTaskId)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的任务ID不匹配");
        }

        Map<String, Object> run = new LinkedHashMap<>();
        run.put("runId", runId);
        run.put("requestId", requestId);
        run.put("startInput", new LinkedHashMap<>(input));
        run.put("researchId", runId); // alias for frontend lookup
        run.put("taskId", taskId);
        run.put("contractVersion", CONTRACT_V2);
        run.put("engineVersion", ENGINE_V2);
        run.put("runRevision", created.containsKey("runRevision") ? created.get("runRevision") : 0L);
        run.put("status", created.containsKey("status") ? created.get("status") : null);
        run.put("outcome", created.get("outcome"));
        run.put("paperIds", resolvedMaterialIds);
        run.put("focusPaperIds", focusPaperIds);
        run.put("sourcePolicy", Map.of("mode", policyMode));
        run.put("budgetProfile", budgetProfile);
        run.put("outputKind", outputKind);
        run.put("question", question);
        run.put("parentRunId", parentRunId);
        run.put("snapshotHash", snapshotHash);
        run.put("contextRefs", contextMaterials.stream().map(value -> value.get("ref")).toList());
        run.put("createdAt", Instant.now().toString());

        try {
            tasks.attachResearchRun(taskId, expectedRevision, run);
        } catch (RuntimeException conflict) {
            // Cancel queued run with proper receipt/revision on conflict
            try {
                long createdRevision = created.containsKey("runRevision") && created.get("runRevision") instanceof Number cr
                        ? ((Number) cr).longValue() : 0L;
                Map<String, Object> cancelBody = new LinkedHashMap<>();
                cancelBody.put("requestId", "cancel:" + input.getOrDefault("requestId", ""));
                cancelBody.put("expectedRunRevision", createdRevision);
                requireSuccess(research.cancelV2ResearchTask(runId, cancelBody));
            } catch (RuntimeException ignored) {}
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已更新，新建研究运行已取消，请刷新后重试");
        }

        // Activate deferred run after successful attach
        long createdRevision = created.containsKey("runRevision") && created.get("runRevision") instanceof Number cr
                ? ((Number) cr).longValue() : 0L;
        String originalRequestId = input.get("requestId") instanceof String rid ? rid : "";
        Map<String, Object> activateBody = new LinkedHashMap<>();
        activateBody.put("requestId", "activate:" + originalRequestId);
        activateBody.put("expectedRunRevision", createdRevision);
        Map<String, Object> activated = requireSuccess(research.resumeV2ResearchTask(runId, activateBody));

        // Merge activated state into response
        if (activated.get("task") instanceof Map<?, ?> activatedTask) {
            return buildV2Response(taskId, runId, activatedTask);
        }
        return buildV2Response(taskId, runId, created);
    }

    // === V2 internal methods ===
    private Map<String, Object> getV2(String taskId, String runId) {
        requireV2Owner(taskId, runId);
        Map<String, Object> result = requireSuccess(research.getV2ResearchTask(runId));
        return publishV2(taskId, runId, result);
    }

    private Map<String, Object> pauseV2(String taskId, String runId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        Map<String, Object> body = forwardBody(input, List.of("requestId", "expectedRunRevision"));
        return publishV2(taskId, runId, requireSuccess(research.pauseV2ResearchTask(runId, body)));
    }

    private Map<String, Object> clarifyV2(String taskId, String runId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        Map<String, Object> body = forwardBody(input, List.of("requestId", "expectedRunRevision", "answer"));
        return publishV2(taskId, runId, requireSuccess(research.clarifyV2ResearchTask(runId, body)));
    }

    private Map<String, Object> planV2(String taskId, String runId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        Map<String, Object> body = forwardBody(input, List.of("requestId", "expectedRunRevision", "plan"));
        return publishV2(taskId, runId, requireSuccess(research.planV2ResearchTask(runId, body)));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> continueV2(String taskId, String runId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        Map<String, Object> parentRun = findV2Run(taskId, runId);
        if (input != null && input.containsKey("materialSelection")) {
            Map<String, Object> fresh = new LinkedHashMap<>(input);
            fresh.put("parentRunId", runId);
            fresh.put("engineVersion", ENGINE_V2);
            fresh.put("sourcePolicy", parentRun.get("sourcePolicy"));
            fresh.put("outputKind", parentRun.get("outputKind"));
            fresh.putIfAbsent("question", parentRun.get("question"));
            fresh.putIfAbsent("contextRefs", parentRun.getOrDefault("contextRefs", List.of()));
            return startV2(taskId, fresh);
        }
        Map<String, Object> body = forwardBody(input, List.of("requestId", "expectedRunRevision", "question", "budgetProfile", "sourcePolicy"));
        body.put("parentRunId", runId);
        // Defer child graph start to avoid race with workspace binding
        body.put("deferStart", true);
        Map<String, Object> result = requireSuccess(research.continueV2ResearchTask(runId, body));

        // Bind child run to workspace
        String childRunId = null;
        long childRevision = 0L;
        if (result.get("task") instanceof Map<?, ?> childState) {
            childRunId = textOrNull(childState.get("runId"));
            childRevision = childState.containsKey("runRevision") && childState.get("runRevision") instanceof Number cr
                    ? ((Number) cr).longValue() : 0L;
            if (childRunId != null && !childRunId.isBlank() && !runId.equals(childRunId)) {
                List<?> childPapers = parentRun.get("paperIds") instanceof List<?> cp ? cp : List.of();
                Map<String, Object> childRun = new LinkedHashMap<>();
                childRun.put("runId", childRunId);
                childRun.put("researchId", childRunId); // alias
                childRun.put("taskId", taskId);
                childRun.put("contractVersion", CONTRACT_V2);
                childRun.put("engineVersion", ENGINE_V2);
                childRun.put("runRevision", childRevision);
                childRun.put("status", childState.containsKey("status") ? childState.get("status") : null);
                childRun.put("outcome", childState.get("outcome"));
                childRun.put("paperIds", childPapers);
                childRun.put("focusPaperIds", parentRun.get("focusPaperIds"));
                childRun.put("sourcePolicy", parentRun.get("sourcePolicy"));
                childRun.put("contextRefs", parentRun.getOrDefault("contextRefs", List.of()));
                childRun.put("snapshotHash", parentRun.get("snapshotHash"));
                childRun.put("budgetProfile", input != null && input.get("budgetProfile") instanceof String bp ? bp : parentRun.get("budgetProfile"));
                childRun.put("outputKind", parentRun.get("outputKind"));
                childRun.put("question", input != null && input.get("question") instanceof String q ? q : parentRun.get("question"));
                childRun.put("parentRunId", runId);
                childRun.put("createdAt", Instant.now().toString());
                try { tasks.attachResearchRun(taskId, tasks.get(taskId).get("revision"), childRun); }
                catch (RuntimeException conflict) {
                    // Never activate an unbound child; the same request can recover its receipt.
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "后续研究尚未绑定到任务，未开始模型调用；请刷新后用原请求重试", conflict);
                }
            }
        }

        // Activate deferred child run after successful attach
        if (childRunId != null && !childRunId.isBlank() && !runId.equals(childRunId)) {
            String originalRequestId = input != null && input.get("requestId") instanceof String rid ? rid : "";
            Map<String, Object> activateBody = new LinkedHashMap<>();
            activateBody.put("requestId", "activate:" + originalRequestId);
            activateBody.put("expectedRunRevision", childRevision);
            try {
                Map<String, Object> activated = requireSuccess(research.resumeV2ResearchTask(childRunId, activateBody));
                if (activated.get("task") instanceof Map<?, ?> activatedTask) {
                    return buildContinueResponse(taskId, runId, childRunId, activated);
                }
            } catch (RuntimeException ignored) {
                // Activation failure is non-fatal; child remains queued for manual resume
            }
        }

        // For continue, response may contain child runId; build response using parent context
        return buildContinueResponse(taskId, runId, childRunId, result);
    }

    private Map<String, Object> resumeV2(String taskId, String runId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        requireV2Materials(taskId, runId);
        Map<String, Object> body = forwardBody(input, List.of("requestId", "expectedRunRevision"));
        return publishV2(taskId, runId, requireSuccess(research.resumeV2ResearchTask(runId, body)));
    }

    private Map<String, Object> cancelV2(String taskId, String runId, Map<String, Object> input) {
        requireV2Owner(taskId, runId);
        Map<String, Object> body = forwardBody(input, List.of("requestId", "expectedRunRevision"));
        return publishV2(taskId, runId, requireSuccess(research.cancelV2ResearchTask(runId, body)));
    }

    private Map<String, Object> getV2Sources(String taskId, String runId) {
        requireV2Owner(taskId, runId);
        Map<String, Object> result = requireSuccess(research.getV2Sources(runId));
        Map<String, Object> run = findV2Run(taskId, runId);
        List<?> allowedPapers = (List<?>) run.get("paperIds");
        Map<String, Object> policy = (Map<String, Object>) run.get("sourcePolicy");
        String policyMode = policy != null && policy.get("mode") instanceof String pm ? pm : "task_only";
        boolean externalAllowed = "academic_external".equals(policyMode) || "external_only".equals(policyMode);

        if (result.get("sources") instanceof List<?> sources) {
            List<Object> filtered = new ArrayList<>();
            for (Object s : sources) {
                if (!(s instanceof Map<?, ?> source)) continue;
                String sourceKind = source.get("sourceKind") instanceof String sk ? sk : "task_paper";
                if ("task_paper".equals(sourceKind)) {
                    String pdfId = source.get("pdfId") instanceof String pid ? pid : null;
                    String workId = source.get("workId") instanceof String wid ? wid : null;
                    String identity = pdfId != null ? pdfId : workId;
                    if (identity != null && allowedPapers.contains(identity)) filtered.add(s);
                } else if (externalAllowed) {
                    String extId = source.get("workId") instanceof String eid ? eid : null;
                    String extUrl = source.get("url") instanceof String eu ? eu : null;
                    String extType = source.get("sourceType") instanceof String et ? et : null;
                    if ("arxiv".equals(sourceKind) && extId != null && extId.startsWith("arxiv:")
                            && extUrl != null && extUrl.matches("https://arxiv\\.org/(?:abs|pdf)/[A-Za-z0-9./-]+")
                            && extType != null && !extType.isBlank()) {
                        filtered.add(s);
                    }
                }
            }
            Map<String, Object> response = new LinkedHashMap<>(result);
            response.put("sources", filtered);
            return response;
        }
        return result;
    }

    private Map<String, Object> getV2Events(String taskId, String runId) {
        requireV2Owner(taskId, runId);
        return requireSuccess(research.getV2Events(runId));
    }

    // === V2 Publication Logic ===
    @SuppressWarnings("unchecked")
    private Map<String, Object> publishV2(String taskId, String runId, Map<String, Object> result) {
        if (!(result.get("task") instanceof Map<?, ?> state)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务未返回任务");
        }
        String returnedRunId = textOrNull(state.get("runId"));
        String returnedTaskId = textOrNull(state.get("taskId"));
        if (returnedRunId != null && !runId.equals(returnedRunId)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的 runId 不匹配");
        }
        if (returnedTaskId != null && !taskId.equals(returnedTaskId)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回的 taskId 不匹配");
        }
        String engineVersion = textOrNull(state.get("engineVersion"));
        if (engineVersion != null && !ENGINE_V2.equals(engineVersion)) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "运行引擎版本不匹配");
        }

        Map<String, Object> storedRun = findV2Run(taskId, runId);
        Object storedRevision = storedRun.get("runRevision");
        Object incomingRevision = state.get("runRevision");
        if (storedRevision instanceof Number storedRev && incomingRevision instanceof Number incomingRev) {
            if (incomingRev.longValue() < ((Number) storedRev).longValue()) {
                return buildV2ResponseFromStored(taskId, runId, storedRun);
            }
        }

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", "success");
        response.put("workspace", tasks.get(taskId));
        Map<String, Object> taskView = new LinkedHashMap<>();
        taskView.put("runId", runId);
        taskView.put("taskId", taskId);
        taskView.put("contractVersion", CONTRACT_V2);
        taskView.put("engineVersion", ENGINE_V2);
        taskView.put("runRevision", state.containsKey("runRevision") ? state.get("runRevision") : 0L);
        // No hardcoded status when missing - pass through null
        taskView.put("status", state.get("status"));
        taskView.put("outcome", state.get("outcome"));

        if (state.get("report") instanceof Map<?, ?> report) {
            Map<String, Object> reportView = new LinkedHashMap<>();
            reportView.put("body", report.get("body"));
            reportView.put("versionId", report.get("versionId"));
            reportView.put("origin", report.containsKey("origin") ? report.get("origin") : "machine");
            taskView.put("report", reportView);
            taskView.put("reportVersionId", report.get("versionId"));
        }
        taskView.put("summary", state.get("summary"));
        taskView.put("sources", state.containsKey("sources") ? state.get("sources") : List.of());
        taskView.put("allowedActions", resolveAllowedActions(state));
        for (String key : List.of("activity", "budget", "clarification", "plan", "errorCode", "sourceCount", "events", "title", "error")) {
            if (state.containsKey(key)) taskView.put(key, state.get(key));
        }
        if (state.containsKey("parentRunId")) taskView.put("parentRunId", state.get("parentRunId"));
        response.put("task", taskView);

        // Publish terminal results
        String status = textOrNull(state.get("status"));
        String outcome = textOrNull(state.get("outcome"));
        if (isTerminal(status) && state.get("report") instanceof Map<?, ?>) {
            tasks.publishV2ResearchResult(taskId, runId, state);
        }
        if (incomingRevision instanceof Number rev) {
            tasks.updateV2RunRevision(taskId, runId, rev.longValue(), status, outcome);
        }
        response.put("workspace", tasks.get(taskId));
        return response;
    }

    /** Continue response: task.runId = childRunId for frontend adoption; parentRunId separate. Includes workspace. */
    private Map<String, Object> buildContinueResponse(String taskId, String parentRunId, String childRunId, Map<String, Object> result) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", "success");
        response.put("workspace", tasks.get(taskId));
        Map<String, Object> taskView = new LinkedHashMap<>();
        // Frontend adopts the child run via task.runId
        taskView.put("runId", childRunId != null ? childRunId : parentRunId);
        taskView.put("taskId", taskId);
        taskView.put("parentRunId", parentRunId);
        taskView.put("contractVersion", CONTRACT_V2);
        taskView.put("engineVersion", ENGINE_V2);
        if (result.get("task") instanceof Map<?, ?> childState) {
            taskView.put("runRevision", childState.containsKey("runRevision") ? childState.get("runRevision") : 0L);
            taskView.put("status", childState.get("status"));
            taskView.put("outcome", childState.get("outcome"));
        }
        taskView.put("allowedActions", List.of());
        response.put("task", taskView);
        return response;
    }

    // === Legacy publish (preserved) ===
    private Map<String, Object> publishLegacy(String id, String researchId, Map<String, Object> result) {
        if (!(result.get("task") instanceof Map<?, ?> state))
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务未返回任务");
        Map<String, Object> response = new LinkedHashMap<>(result);
        Map<String, Object> workspace = tasks.publishResearchResult(id, researchId, state);
        response.put("workspace", workspace);
        Map<?, ?> run = ((List<?>) workspace.get("researchRuns")).stream()
                .filter(value -> value instanceof Map<?, ?> item && researchId.equals(item.get("researchId")))
                .map(value -> (Map<?, ?>) value).findFirst().orElseThrow();
        Map<String, Object> scope = new LinkedHashMap<>();
        scope.put("taskId", id); scope.put("allowedPaperIds", run.get("paperIds"));
        scope.put("primaryPaperId", run.get("primaryPaperId")); scope.put("strictScope", true);
        Map<?, ?> artifact = ((List<?>) workspace.get("artifacts")).stream()
                .filter(value -> value instanceof Map<?, ?> item && researchId.equals(item.get("sourceResearchId")))
                .map(value -> (Map<?, ?>) value).findFirst().orElse(null);
        Map<?, ?> answer = ((List<?>) workspace.get("messages")).stream()
                .filter(value -> value instanceof Map<?, ?> item && researchId.equals(item.get("sourceResearchId")))
                .map(value -> (Map<?, ?>) value).findFirst().orElse(null);
        response.put("resultVersion", 1); response.put("capability", "research");
        response.put("materialScope", scope); response.put("artifact", artifact);
        response.put("sources", artifact == null ? List.of() : artifact.get("sources"));
        response.put("sentenceSourceMap", List.of()); response.put("steps", List.of());
        response.put("message", answer == null ? "研究状态已更新。" : answer.get("content"));
        return response;
    }

    // === Response builders ===
    private Map<String, Object> buildV2Response(String taskId, String runId, Map<?, ?> created) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", "success");
        response.put("workspace", tasks.get(taskId));
        Map<String, Object> taskView = new LinkedHashMap<>();
        taskView.put("runId", runId);
        taskView.put("taskId", taskId);
        taskView.put("contractVersion", CONTRACT_V2);
        taskView.put("engineVersion", ENGINE_V2);
        taskView.put("runRevision", created.containsKey("runRevision") ? created.get("runRevision") : 0L);
        taskView.put("status", created.get("status"));
        taskView.put("outcome", created.get("outcome"));
        taskView.put("report", created.get("report"));
        taskView.put("reportVersionId", created.get("report") instanceof Map<?, ?> r ? r.get("versionId") : null);
        taskView.put("summary", created.get("summary"));
        taskView.put("sources", created.containsKey("sources") ? created.get("sources") : List.of());
        taskView.put("allowedActions", resolveAllowedActions(created));
        // Include parentRunId if present in upstream response
        if (created.containsKey("parentRunId")) taskView.put("parentRunId", created.get("parentRunId"));
        response.put("task", taskView);
        return response;
    }

    private Map<String, Object> buildV2ResponseFromStored(String taskId, String runId, Map<String, Object> storedRun) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", "success");
        response.put("workspace", tasks.get(taskId));
        Map<String, Object> taskView = new LinkedHashMap<>();
        taskView.put("runId", runId);
        taskView.put("taskId", taskId);
        taskView.put("contractVersion", CONTRACT_V2);
        taskView.put("engineVersion", ENGINE_V2);
        taskView.put("runRevision", storedRun.containsKey("runRevision") ? storedRun.get("runRevision") : 0L);
        taskView.put("status", storedRun.get("status"));
        taskView.put("outcome", storedRun.get("outcome"));
        taskView.put("summary", storedRun.get("summary"));
        taskView.put("sources", storedRun.containsKey("sources") ? storedRun.get("sources") : List.of());
        taskView.put("allowedActions", List.of());
        if (storedRun.containsKey("parentRunId")) taskView.put("parentRunId", storedRun.get("parentRunId"));
        response.put("task", taskView);
        return response;
    }

    // === Helpers ===
    private Map<String, Object> forwardBody(Map<String, Object> input, List<String> fields) {
        Map<String, Object> body = new LinkedHashMap<>();
        if (input != null) for (String f : fields) if (input.containsKey(f)) body.put(f, input.get(f));
        return body;
    }

    private Map<String, Object> reviewFields(Map<String, Object> input, List<String> fields) {
        return forwardBody(input, fields);
    }

    private List<String> resolveAllowedActions(Map<?, ?> state) {
        if (state.get("allowedActions") instanceof List<?> actions) {
            return actions.stream().filter(a -> a instanceof String).map(a -> (String) a).toList();
        }
        String status = textOrNull(state.get("status"));
        if (status == null) return List.of();
        List<String> allowed = new ArrayList<>();
        if ("completed".equals(status) || "cancelled".equals(status) || "failed".equals(status)) {
            allowed.add("open_report"); allowed.add("view_sources"); allowed.add("continue");
        }
        if ("paused".equals(status) || "waiting_user".equals(status)) {
            allowed.add("resume"); allowed.add("cancel");
        }
        if ("running".equals(status)) {
            allowed.add("pause"); allowed.add("cancel");
        }
        return allowed;
    }

    private boolean isTerminal(String status) {
        return "completed".equals(status) || "cancelled".equals(status) || "failed".equals(status);
    }

    /** Find run by either runId or researchId (alias). */
    @SuppressWarnings("unchecked")
    private Map<String, Object> findRunByEitherId(String taskId, String id) {
        Map<String, Object> workspace = tasks.get(taskId);
        if (!(workspace.get("researchRuns") instanceof List<?> runs)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "研究运行不属于当前任务");
        }
        return runs.stream()
                .filter(r -> r instanceof Map<?, ?> run
                        && (id.equals(run.get("runId")) || id.equals(run.get("researchId"))))
                .map(r -> (Map<String, Object>) r)
                .findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "研究运行不属于当前任务"));
    }

    private String resolveEngine(Map<String, Object> run) {
        Object engine = run.get("engineVersion");
        if (ENGINE_V2.equals(engine)) return ENGINE_V2;
        return ENGINE_LEGACY;
    }

    private String resolveRunId(Map<String, Object> run) {
        Object runId = run.get("runId");
        if (runId instanceof String rid) return rid;
        Object researchId = run.get("researchId");
        return researchId instanceof String rid ? rid : "";
    }

    private void requireV2Engine(Map<String, Object> run) {
        if (!ENGINE_V2.equals(resolveEngine(run))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "此操作仅适用于v2研究运行");
        }
    }

    private void requireOwner(String id, String researchId) {
        Map<String, Object> workspace = tasks.get(id);
        if (!(workspace.get("researchRuns") instanceof List<?> runs)
                || runs.stream().noneMatch(run -> run instanceof Map<?, ?> value
                        && (researchId.equals(value.get("researchId")) || researchId.equals(value.get("runId"))))) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "研究任务不属于当前工作区");
        }
    }

    private void requireV2Owner(String taskId, String runId) {
        findV2Run(taskId, runId); // throws if not found
    }

    private void requireMaterials(String id, String researchId) {
        Map<String, Object> workspace = tasks.get(id);
        List<?> papers = (List<?>) workspace.get("paperIds");
        for (Object item : (List<?>) workspace.get("researchRuns")) {
            if (item instanceof Map<?, ?> run && (researchId.equals(run.get("researchId")) || researchId.equals(run.get("runId")))) {
                if (!(run.get("paperIds") instanceof List<?> scope) || scope.isEmpty() || !papers.containsAll(scope)) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "研究材料已变化，请恢复原材料后继续");
                }
                return;
            }
        }
        throw new ResponseStatusException(HttpStatus.NOT_FOUND, "研究任务不属于当前工作区");
    }

    private void requireV2Materials(String taskId, String runId) {
        Map<String, Object> workspace = tasks.get(taskId);
        List<?> papers = (List<?>) workspace.get("paperIds");
        Map<String, Object> run = findV2Run(taskId, runId);
        List<?> scope = (List<?>) run.get("paperIds");
        if (scope == null || scope.isEmpty() || !papers.containsAll(scope)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "研究材料已变化，请恢复原材料后继续");
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> findV2Run(String taskId, String runId) {
        Map<String, Object> workspace = tasks.get(taskId);
        return ((List<?>) workspace.get("researchRuns")).stream()
                .filter(r -> r instanceof Map<?, ?> run && (runId.equals(run.get("runId")) || runId.equals(run.get("researchId"))))
                .map(r -> (Map<String, Object>) r)
                .findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "研究运行不属于当前任务"));
    }

    private Map<String, Object> requireSuccess(ResponseEntity<Map<String, Object>> response) {
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new ResponseStatusException(response.getStatusCode(), "研究服务请求未完成，请重试");
        }
        Map<String, Object> body = response.getBody();
        if (body == null || !"success".equals(body.get("status"))) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "研究服务返回无效结果");
        }
        return body;
    }

    private String textOrNull(Object value) { return value instanceof String s ? s : null; }

    private String computeSnapshotHash(List<Map<String, String>> materialVersions, List<String> focusIds, String policyMode) {
        return computeSnapshotHash(materialVersions, focusIds, policyMode, List.of());
    }

    private String computeSnapshotHash(List<Map<String, String>> materialVersions, List<String> focusIds, String policyMode,
                                       List<Map<String, String>> contexts) {
        StringBuilder sb = new StringBuilder();
        for (Map<String, String> mv : materialVersions) {
            sb.append(mv.get("id"))
              .append(':').append(mv.getOrDefault("fileName", ""))
              .append(':').append(mv.getOrDefault("processingStatus", ""))
              .append(':').append(mv.getOrDefault("uploadTime", ""))
              .append(':').append(mv.getOrDefault("contentHash", ""))
              .append(',');
        }
        sb.append('|');
        for (String f : focusIds) sb.append(f).append(',');
        sb.append('|').append(policyMode);
        for (Map<String, String> context : contexts) sb.append("|context:").append(context.get("ref"))
                .append(':').append(context.get("contentHash"));
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(sb.toString().getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    /** Notes and saved reports are user context, never direct paper evidence. */
    private List<Map<String, String>> buildContextMaterials(Map<String, Object> workspace, Object rawRefs) {
        if (rawRefs == null) return List.of();
        if (!(rawRefs instanceof List<?> refs) || refs.size() > 4)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "最多选择四份笔记或成果作为研究背景");
        List<Map<String, String>> output = new ArrayList<>();
        java.util.Set<String> seen = new java.util.HashSet<>();
        for (Object raw : refs) {
            if (!(raw instanceof String ref) || !(ref.startsWith("note:") || ref.startsWith("artifact:")) || !seen.add(ref))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "背景材料身份无效");
            String kind = ref.startsWith("note:") ? "note" : "artifact";
            String id = ref.substring(ref.indexOf(':') + 1);
            List<?> candidates = workspace.get(kind.equals("note") ? "notes" : "artifacts") instanceof List<?> list ? list : List.of();
            Map<?, ?> document = candidates.stream().filter(value -> value instanceof Map<?, ?> item && id.equals(item.get("id")))
                    .map(value -> (Map<?, ?>) value).findFirst().orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.CONFLICT, "所选笔记或成果已不在本任务中"));
            String text = java.util.Objects.toString(document.get("text"), "");
            String title = java.util.Objects.toString(document.get("title"), "未命名材料");
            String contentHash;
            try { contentHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest((title + "\n" + text).getBytes(StandardCharsets.UTF_8))); }
            catch (NoSuchAlgorithmException error) { throw new IllegalStateException(error); }
            output.add(Map.of("ref", ref, "kind", kind, "title", title, "contentHash", contentHash,
                    "text", text.substring(0, Math.min(text.length(), 1000)), "accessLevel", "unverified_context"));
        }
        return output;
    }

    /**
     * Build material version entries with identical keys for both creation and scope-check recomputation.
     * Keys: id, fileName, processingStatus, uploadTime, contentHash (SHA-256 of pdfBytes).
     * contentHash serves as versionId — any byte-level change produces a new identity.
     */
    private List<Map<String, String>> buildMaterialVersions(List<String> materialIds) {
        List<Map<String, String>> versions = new ArrayList<>();
        for (String mid : materialIds) {
            Map<String, String> entry = new LinkedHashMap<>();
            entry.put("id", mid);
            if (paperRepository != null) {
                var paper = paperRepository.findById(mid).orElse(null);
                if (paper != null) {
                    entry.put("processingStatus", paper.getProcessingStatus() != null ? paper.getProcessingStatus() : "");
                    entry.put("uploadTime", paper.getUploadTime() != null ? paper.getUploadTime().toString() : "");
                    entry.put("fileName", paper.getFileName() != null ? paper.getFileName() : "");
                    String title = paper.getFileName() != null ? paper.getFileName() : mid;
                    if (paper.getAnalysisJson() != null) {
                        try {
                            String parsed = new com.fasterxml.jackson.databind.ObjectMapper()
                                    .readTree(paper.getAnalysisJson()).path("title").asText("");
                            if (!parsed.isBlank()) title = parsed;
                        } catch (com.fasterxml.jackson.core.JsonProcessingException ignored) { /* Filename remains available. */ }
                    }
                    entry.put("title", title);
                    entry.put("contentHash", computeContentHash(paper.getPdfBytes()));
                } else {
                    entry.put("processingStatus", "");
                    entry.put("uploadTime", "");
                    entry.put("fileName", "");
                    entry.put("contentHash", "");
                }
            } else {
                entry.put("processingStatus", "");
                entry.put("uploadTime", "");
                entry.put("fileName", "");
                entry.put("contentHash", "");
            }
            versions.add(entry);
        }
        return versions;
    }

    /** SHA-256 hash of raw PDF bytes; empty string when bytes are null/empty. */
    private String computeContentHash(byte[] pdfBytes) {
        if (pdfBytes == null || pdfBytes.length == 0) return "";
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(pdfBytes);
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
