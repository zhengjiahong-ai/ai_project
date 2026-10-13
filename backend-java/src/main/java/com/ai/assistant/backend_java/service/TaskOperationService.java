package com.ai.assistant.backend_java.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

/** Validate authority before submitting; durable execution and cancellation live in Python. */
@Service
public class TaskOperationService {
    private final TaskWorkspaceService tasks;
    private final RestTemplate client;
    @org.springframework.beans.factory.annotation.Autowired
    private com.ai.assistant.backend_java.repository.PaperRepository materialRepository;
    private final String url;
    private final ObjectMapper canonical = new ObjectMapper().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    public TaskOperationService(TaskWorkspaceService tasks, RestTemplate client,
            @Value("${PYTHON_URL:http://localhost:8000/api}") String url) {
        this.tasks = tasks; this.client = client; this.url = url.replaceAll("/+$", "") + "/task-operations";
    }

    public Map<String, Object> start(String id, Map<String, Object> input) {
        return start(id, input, null);
    }
    private Map<String, Object> start(String id, Map<String, Object> input, String retryOf) {
        tasks.get(id);
        String requestId = text(input.get("requestId"));
        String kind = text(input.get("kind"));
        if (!Set.of("learning.start", "learning.action", "research.start", "conversation.execute").contains(kind)
                || !(input.get("input") instanceof Map<?, ?> raw)) throw bad("请求类型或参数无效");
        Map<String, Object> original = new LinkedHashMap<>();
        raw.forEach((k, v) -> original.put(String.valueOf(k), v));
        Map<String, Object> existing = read(id, requestId, true);
        if (existing != null) {
            if (!kind.equals(existing.get("kind")) || !sameInput(original, ((Map<?, ?>) existing.get("input")).get("original"))) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "同一请求 ID 不能用于不同内容");
            }
            return present(id, existing);
        }
        // Bind any earlier completed result before validating a new expected task revision.
        list(id);
        Map<String, Object> task = tasks.get(id);
        if (!(original.get("expectedTaskRevision") instanceof Number expected)
                || expected.doubleValue() != expected.longValue() || expected.longValue() < 0) throw bad("必须提供整数任务版本");
        if (expected.longValue() != ((Number) task.get("revision")).longValue()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务已更新，请刷新后继续");
        }
        List<?> papers = (List<?>) task.get("paperIds");
        Map<String, Object> upstream = new LinkedHashMap<>();
        List<?> scope;
        if (kind.startsWith("learning.")) {
            if (kind.equals("learning.start")) {
                if (task.get("activeActivity") instanceof Map<?, ?> active && !"finished".equals(active.get("status"))) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "请先结束现有学习活动");
                }
                String pdfId = text(original.get("pdfId"));
                if (!papers.contains(pdfId)) throw bad("论文不属于当前任务");
                String mode = String.valueOf(original.getOrDefault("mode", "read"));
                if (!Set.of("read", "quiz").contains(mode)) throw bad("学习模式无效");
                upstream.putAll(Map.of("taskId", id, "pdfId", pdfId, "mode", mode,
                        "goal", original.getOrDefault("goal", "理解论文的关键问题、方法和证据")));
                scope = List.of(pdfId);
            } else {
                if (!(task.get("activeActivity") instanceof Map<?, ?> state)) throw bad("当前没有学习活动");
                if (!state.get("activityId").equals(original.get("activityId"))
                        || !(original.get("expectedRevision") instanceof Number revision)
                        || revision.doubleValue() != ((Number) state.get("revision")).longValue()) {
                    throw new ResponseStatusException(HttpStatus.CONFLICT, "活动已更新，请刷新后继续");
                }
                String action = text(original.get("action"));
                if (!Set.of("answer", "hint", "skip", "retry", "pause", "resume", "finish", "ask", "remediate").contains(action)) throw bad("学习动作无效");
                if (!papers.contains(state.get("pdfId"))) throw bad("活动论文已移出任务");
                upstream.putAll(Map.of("taskId", id, "activityId", state.get("activityId"), "expectedRevision", state.get("revision"),
                        "action", action, "text", original.getOrDefault("text", ""), "state", state));
                scope = List.of(state.get("pdfId"));
            }
        } else if (kind.equals("conversation.execute")) {
            Object selected = original.getOrDefault("allowedPaperIds", papers);
            if (!(selected instanceof List<?> ids) || ids.stream().anyMatch(p -> !(p instanceof String) || !papers.contains(p))) throw bad("对话材料须属于当前任务");
            scope = new ArrayList<>(new LinkedHashSet<>(ids));
            String capability = String.valueOf(original.getOrDefault("capability", "chat"));
            Set<String> singles = Set.of("chat", "background", "critique", "compare");
            if (!singles.contains(capability) && !capability.equals("compose")) throw bad("对话能力无效");
            Object primary = original.get("primaryPaperId");
            if (primary != null && !scope.contains(primary)) throw bad("主论文不属于对话材料");
            Object steps = original.getOrDefault("steps", List.of());
            if (!(steps instanceof List<?> parsedSteps) || parsedSteps.size() > 3
                    || (capability.equals("compose") ? parsedSteps.size() < 2 || new LinkedHashSet<>(parsedSteps).size() != parsedSteps.size() || parsedSteps.stream().anyMatch(p -> !singles.contains(p)) : !parsedSteps.isEmpty())) throw bad("组合步骤无效");
            List<?> plan = capability.equals("compose") ? (List<?>) steps : List.of(capability);
            if (scope.isEmpty() && plan.stream().anyMatch(p -> !p.equals("chat"))) throw bad("请先选择任务材料");
            if (plan.contains("compare") && scope.size() < 2) throw bad("比较至少需要两篇论文");
            if (scope.size() > 4 && plan.stream().anyMatch(p -> p.equals("compare") || p.equals("background"))) throw bad("单次分析最多四篇论文，请明确选择材料");
            if (Boolean.TRUE.equals(original.get("allowExternalSearch")) || Boolean.TRUE.equals(original.get("allowWebSearch"))) throw bad("外部检索尚未授权");
            upstream.put("taskId", id);
            upstream.put("message", text(original.get("message")));
            upstream.put("capability", capability);
            upstream.put("allowedPaperIds", scope);
            upstream.put("primaryPaperId", primary);
            upstream.put("strictScope", Boolean.TRUE.equals(original.get("strictScope")));
            upstream.put("steps", steps);
            if (original.containsKey("targetPaperIds")) {
                if (!(original.get("targetPaperIds") instanceof List<?> targets) || targets.isEmpty()
                        || targets.size() > 4 || targets.stream().anyMatch(p -> !(p instanceof String) || !scope.contains(p))) throw bad("批判对象须属于对话材料且最多四篇");
                upstream.put("targetPaperIds", new ArrayList<>(new LinkedHashSet<>(targets)));
            }
            if (original.containsKey("followup")) bindCritiqueContext(task, original.get("followup"), scope, upstream);
            if (plan.contains("critique") && scope.size() > 4 && !upstream.containsKey("targetPaperIds")
                    && (primary == null || String.valueOf(original.get("message")).matches("(?s).*(分别|逐篇|每篇|所有论文|全部论文|两篇|这些论文).*")))
                throw bad("单次批判最多四篇论文，请明确选择材料");
            List<Map<String, String>> history = new ArrayList<>();
            for (Object value : (List<?>) task.get("messages")) {
                if (!(value instanceof Map<?, ?> message) || Boolean.TRUE.equals(message.get("isSystem"))) continue;
                if (!(message.get("context") instanceof Map<?, ?> context) || !id.equals(context.get("taskId"))
                        || !(context.get("allowedPaperIds") instanceof List<?> previous) || !scope.containsAll(previous)) continue;
                String role = String.valueOf(message.get("role"));
                if (!Set.of("user", "ai", "assistant").contains(role) || !(message.get("content") instanceof String content)) continue;
                history.add(Map.of("role", role.equals("ai") ? "assistant" : role, "content", content));
            }
            upstream.put("history", history.subList(Math.max(0, history.size() - 20), history.size()));
        } else {
            Object selected = original.getOrDefault("allowedPaperIds", papers);
            if (!(selected instanceof List<?> ids) || ids.isEmpty() || ids.stream().anyMatch(p -> !(p instanceof String) || !papers.contains(p))) throw bad("研究材料须属于当前任务");
            scope = new ArrayList<>(new LinkedHashSet<>(ids));
            String primary = original.get("pdfId") == null ? String.valueOf(scope.getFirst()) : text(original.get("pdfId"));
            if (!scope.contains(primary)) throw bad("主论文不属于研究材料");
            if (Boolean.TRUE.equals(original.get("allowExternalSearch")) || Boolean.TRUE.equals(original.get("allowWebSearch"))) throw bad("外部检索尚未授权");
            upstream.putAll(Map.of("question", text(original.get("question")), "pdfId", primary,
                    "allowedPaperIds", scope, "allowExternalSearch", false, "allowWebSearch", false));
            upstream.put("operationKey", id + ":" + requestId);
            for (String field : List.of("userConstraints", "paperSkeleton", "briefPreview")) if (original.containsKey(field)) upstream.put(field, original.get(field));
        }
        for (Object paperId : scope) {
            if (materialRepository == null) continue;
            var material = materialRepository.findById(String.valueOf(paperId)).orElse(null);
            if (material != null && material.getProcessingStatus() != null
                    && !"ready".equals(material.getProcessingStatus()))
                throw new ResponseStatusException(HttpStatus.CONFLICT, "论文正文尚未就绪，可先阅读原文或重试解析");
        }
        Map<String, Object> payload = new LinkedHashMap<>(Map.of("original", original, "upstream", upstream, "paperIds", scope));
        if (retryOf != null) payload.put("retryOf", retryOf);
        return present(id, invoke("post", url,
                Map.of("taskId", id, "requestId", requestId, "kind", kind, "input", payload), false));
    }

    public Map<String, Object> get(String id, String requestId) { tasks.get(id); return present(id, read(id, requestId, false)); }
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> list(String id) {
        tasks.get(id);
        try {
            List<Map<String, Object>> values = client.getForObject(URI.create(url + "/" + GatewayHelper.encode(id)), List.class);
            if (values == null) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "请求记录未返回");
            return values.stream().map(value -> present(id, value)).toList();
        } catch (HttpStatusCodeException failure) {
            throw new ResponseStatusException(failure.getStatusCode(), "请求记录暂不可读取，请稍后查询");
        } catch (RestClientException failure) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "暂时无法查询请求记录"); }
    }
    public Map<String, Object> cancel(String id, String requestId) {
        tasks.get(id);
        return present(id, invoke("post", endpoint(id, requestId) + "/cancel", Map.of(), false));
    }
    public Map<String, Object> cancel(String id, String requestId, Map<String, Object> intent) {
        Map<String, Object> task = tasks.get(id);
        if (read(id, requestId, true) != null) return cancel(id, requestId);
        if (intent == null || !Set.of("learning.start", "learning.action", "research.start", "conversation.execute").contains(java.util.Objects.toString(intent.get("kind"), ""))
                || !(intent.get("input") instanceof Map<?, ?> raw))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "请求尚未确认，请携带原问题停止");
        Map<String, Object> original = new LinkedHashMap<>(); raw.forEach((key, value) -> original.put(String.valueOf(key), value));
        Object selected = original.getOrDefault("allowedPaperIds", original.get("pdfId") instanceof String pdfId ? List.of(pdfId) : task.get("paperIds"));
        if (!(selected instanceof List<?> scope) || scope.stream().anyMatch(value -> !(value instanceof String))) throw bad("原材料范围无效");
        // This is a stop record, not authorization to execute. Even if material
        // or lesson state has since changed, a late request must remain stopped.
        // Explicit retry subsequently performs full membership/revision checks.
        Map<String, Object> payload = Map.of("original", original, "upstream", Map.of(), "paperIds", scope);
        return present(id, invoke("post", url + "/cancel-before-start", Map.of("taskId", id, "requestId", requestId,
                "kind", intent.get("kind"), "input", payload), false));
    }
    public Map<String, Object> retry(String id, String requestId) {
        tasks.get(id);
        Map<String, Object> original = read(id, requestId, false);
        if (!id.equals(original.get("taskId"))) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "请求任务不匹配");
        if (!Set.of("failed", "interrupted", "cancelled").contains(original.get("status")))
            return present(id, original);
        String replacementId = java.util.UUID.nameUUIDFromBytes((id + ":" + requestId + ":retry")
                .getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
        Map<String, Object> replacement = read(id, replacementId, true);
        if (replacement != null) {
            Map<String, Object> view = present(id, replacement); view.put("retryOf", requestId); return view;
        }
        Map<String, Object> task = tasks.get(id);
        if (!(original.get("input") instanceof Map<?, ?> saved) || !(saved.get("original") instanceof Map<?, ?> raw))
            throw bad("原问题未保存，请重新输入");
        Map<String, Object> input = new LinkedHashMap<>(); raw.forEach((key, value) -> input.put(String.valueOf(key), value));
        if (Set.of("conversation.execute", "research.start").contains(original.get("kind"))) {
            if (!(saved.get("paperIds") instanceof List<?> scope)) throw bad("原材料范围未保存，请重新输入");
            input.put("allowedPaperIds", scope);
            if (saved.get("upstream") instanceof Map<?, ?> upstream) {
                String primaryField = "research.start".equals(original.get("kind")) ? "pdfId" : "primaryPaperId";
                if (upstream.containsKey(primaryField)) input.put(primaryField, upstream.get(primaryField));
            }
        }
        // Only the task revision is refreshed. Material scope, activity identity
        // and question revision remain immutable and are revalidated by start.
        input.put("expectedTaskRevision", task.get("revision"));
        Map<String, Object> view = start(id, Map.of("requestId", replacementId, "kind", original.get("kind"), "input", input), requestId);
        view.put("retryOf", requestId); return view;
    }
    public Map<String, Object> recoverResult(String id, String requestId) {
        tasks.get(id);
        Map<String, Object> operation = read(id, requestId, false);
        if (!requestId.equals(operation.get("requestId")) || !id.equals(operation.get("taskId")))
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "请求记录身份不匹配");
        tasks.recoverOperationResult(id, operation);
        return present(id, operation);
    }
    private void bindCritiqueContext(Map<String, Object> task, Object raw, List<?> scope, Map<String, Object> upstream) {
        if (!(raw instanceof Map<?, ?> followup) || !(followup.get("artifactId") instanceof String artifactId)) throw bad("追问缺少成果标识");
        Map<?, ?> artifact = ((List<?>) task.get("artifacts")).stream()
                .filter(value -> value instanceof Map<?, ?> item && artifactId.equals(item.get("id")))
                .map(value -> (Map<?, ?>) value).findFirst().orElseThrow(() -> bad("追问成果不属于当前任务"));
        if (!(artifact.get("paperIds") instanceof List<?> papers) || !scope.containsAll(papers)) throw bad("追问成果超出当前材料范围");
        if (!(artifact.get("critique") instanceof Map<?, ?>)) throw bad("旧成果没有可追问的观点结构，请引用原文提问");
        Map<?, ?> critique = CritiqueContract.validate(artifact.get("critique"), papers);
        String version = String.valueOf(artifact.getOrDefault("updatedAt", null) == null ? artifact.get("createdAt") : artifact.get("updatedAt"));
        if (followup.get("version") != null && !version.equals(String.valueOf(followup.get("version"))))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "成果版本已更新，请刷新后追问");
        boolean regenerate = Boolean.TRUE.equals(followup.get("regenerate"));
        if (regenerate && (!"critique".equals(upstream.get("capability")) || followup.get("issueId") != null
                || followup.get("version") == null)) throw bad("重新核查须指定整份批判成果及保存版本");
        Object issueId = followup.get("issueId");
        if (issueId != null && (!(issueId instanceof String) || ((List<?>) critique.get("issues")).stream()
                .noneMatch(value -> value instanceof Map<?, ?> issue && issueId.equals(issue.get("id"))))) throw bad("追问观点不属于该成果");
        boolean edited = Boolean.TRUE.equals(artifact.get("edited"));
        Map<String, Object> context = new LinkedHashMap<>();
        for (String field : List.of("question", "scope")) if (critique.containsKey(field)) context.put(field, critique.get(field));
        context.put("text", artifact.get("text"));
        for (String field : List.of("claims", "issues", "pending")) context.put(field, edited ? List.of() : critique.get(field));
        context.put("version", version); context.put("sourceArtifactId", artifactId); context.put("focusedIssueId", issueId);
        context.put("edited", edited);
        context.put("regenerate", regenerate);
        upstream.put("critiqueContext", context);
        if (!upstream.containsKey("targetPaperIds") && critique.get("scope") instanceof Map<?, ?> material)
            upstream.put("targetPaperIds", material.get("targetPaperIds"));
    }
    private String endpoint(String id, String requestId) { return url + "/" + GatewayHelper.encode(id) + "/" + GatewayHelper.encode(requestId); }
    private Map<String, Object> read(String id, String requestId, boolean missingAllowed) { return invoke("get", endpoint(id, requestId), null, missingAllowed); }
    private Map<String, Object> present(String id, Map<String, Object> op) {
        if (!id.equals(op.get("taskId"))) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "请求任务不匹配");
        Map<String, Object> view = new LinkedHashMap<>();
        for (String field : List.of("taskId", "requestId", "kind", "status", "error", "createdAt", "updatedAt")) view.put(field, op.get(field));
        if (op.get("input") instanceof Map<?, ?> saved && saved.get("original") instanceof Map<?, ?> original) {
            Map<String, Object> request = new LinkedHashMap<>();
            for (String field : List.of("expectedTaskRevision", "message", "displayText", "capability", "allowedPaperIds",
                    "primaryPaperId", "strictScope", "steps", "targetPaperIds", "followup", "pdfId", "mode", "goal", "activityId", "expectedRevision",
                    "action", "text", "question", "allowExternalSearch", "allowWebSearch"))
                if (original.containsKey(field)) request.put(field, original.get(field));
            view.put("request", request);
            view.put("paperIds", saved.get("paperIds"));
            if (saved.get("retryOf") instanceof String retryOf) view.put("retryOf", retryOf);
        }
        if ("succeeded".equals(op.get("status"))) {
            view.put("result", op.get("result"));
            try { view.put("task", tasks.applyOperation(id, op)); }
            catch (ResponseStatusException conflict) {
                if (conflict.getStatusCode().value() != 409) throw conflict;
                view.put("status", "conflicted");
                view.put("error", conflict.getReason());
                view.put("paperIds", ((Map<?, ?>) op.get("input")).get("paperIds"));
            }
        }
        return view;
    }
    @SuppressWarnings("unchecked")
    private Map<String, Object> invoke(String method, String path, Object body, boolean missingAllowed) {
        try {
            Map<String, Object> result = method.equals("get") ? client.getForObject(URI.create(path), Map.class) : client.postForObject(URI.create(path), body, Map.class);
            if (result == null) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "请求记录未返回");
            return result;
        } catch (HttpStatusCodeException failure) {
            if (missingAllowed && failure.getStatusCode().value() == 404) return null;
            throw new ResponseStatusException(failure.getStatusCode(), "请求未完成，请按原请求 ID 查询状态");
        } catch (RestClientException failure) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "请求响应未确认，请按原请求 ID 查询状态");
        }
    }
    private String text(Object value) { if (!(value instanceof String s) || s.isBlank() || s.length() > 20000) throw bad("请求文字无效"); return s; }
    private boolean sameInput(Object a, Object b) {
        try { return canonical.writeValueAsString(a).equals(canonical.writeValueAsString(b)); }
        catch (java.io.IOException failure) { throw bad("请求内容无法序列化"); }
    }
    private ResponseStatusException bad(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST, message); }
}
