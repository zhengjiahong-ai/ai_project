package com.ai.assistant.backend_java.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;

/** Reads and commits in separate short transactions; no DB transaction spans a provider call. */
@Service
public class TaskLearningService {
    private static final Set<String> ACTIONS = Set.of("answer", "hint", "skip", "retry", "pause", "resume", "finish", "ask", "remediate");
    private final TaskWorkspaceService tasks;
    private final RestTemplate client;
    private final String pythonUrl;

    public TaskLearningService(TaskWorkspaceService tasks, RestTemplate client,
            @Value("${PYTHON_URL:http://localhost:8000/api}") String pythonUrl) {
        this.tasks = tasks;
        this.client = client;
        this.pythonUrl = pythonUrl.replaceAll("/+$", "");
    }

    public Map<String, Object> start(String taskId, Map<String, Object> input) {
        Map<String, Object> task = tasks.get(taskId);
        checkRevision(input.get("expectedTaskRevision"), task.get("revision"));
        if (task.get("activeActivity") instanceof Map<?, ?> active && !"finished".equals(active.get("status"))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "请先结束现有学习活动再开始新活动");
        }
        String pdfId = text(input.get("pdfId"), "pdfId");
        checkPaper(task, pdfId);
        String mode = input.get("mode") == null ? "read" : text(input.get("mode"), "mode");
        if (!Set.of("read", "quiz").contains(mode)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "学习模式无效");
        Map<String, Object> upstream = new LinkedHashMap<>();
        upstream.put("taskId", taskId);
        upstream.put("pdfId", pdfId);
        upstream.put("mode", mode);
        if (input.get("goal") != null) upstream.put("goal", text(input.get("goal"), "goal"));
        Map<String, Object> result = invoke("start", upstream);
        return commit(task, result, pdfId, null, 0);
    }

    public Map<String, Object> action(String taskId, Map<String, Object> input) {
        Map<String, Object> task = tasks.get(taskId);
        checkRevision(input.get("expectedTaskRevision"), task.get("revision"));
        if (!(task.get("activeActivity") instanceof Map<?, ?> state)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "当前任务没有学习活动");
        }
        String activityId = text(input.get("activityId"), "activityId");
        if (!activityId.equals(state.get("activityId")) || !taskId.equals(state.get("taskId"))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "学习活动对象已改变");
        }
        checkRevision(input.get("expectedRevision"), state.get("revision"));
        String pdfId = text(state.get("pdfId"), "pdfId");
        checkPaper(task, pdfId);
        String action = text(input.get("action"), "action");
        if (!ACTIONS.contains(action)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "学习动作无效");
        Map<String, Object> upstream = new LinkedHashMap<>();
        upstream.put("taskId", taskId);
        upstream.put("activityId", activityId);
        upstream.put("expectedRevision", state.get("revision"));
        upstream.put("action", action);
        upstream.put("text", input.get("text") == null ? "" : string(input.get("text"), "text"));
        upstream.put("state", state); // Client-supplied state is deliberately ignored.
        Map<String, Object> result = invoke("action", upstream);
        return commit(task, result, pdfId, activityId, ((Number) state.get("revision")).longValue() + 1);
    }

    private Map<String, Object> commit(Map<String, Object> snapshot, Map<String, Object> result,
            String pdfId, String activityId, long revision) {
        if (!(result.get("state") instanceof Map<?, ?> rawState)
                || !snapshot.get("id").equals(rawState.get("taskId"))
                || !pdfId.equals(rawState.get("pdfId"))
                || !(rawState.get("activityId") instanceof String id) || id.isBlank()
                || (activityId != null && !activityId.equals(id))
                || !(rawState.get("revision") instanceof Number n) || n.longValue() != revision
                || n.doubleValue() != revision) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "学习服务返回了无效活动状态");
        }
        Map<String, Object> state = new LinkedHashMap<>();
        rawState.forEach((key, value) -> state.put(String.valueOf(key), value));
        state.put("id", state.get("activityId"));
        state.put("paperIds", List.of(pdfId));
        state.put("primaryPaperId", pdfId);
        state.put("strictScope", true);
        state.put("snapshot", Map.of("paperIds", List.of(pdfId), "primaryPaperId", pdfId, "strictScope", true));
        snapshot.put("activeActivity", state);
        // update re-reads the entity and checks the snapshot revision; concurrent task writes -> 409.
        Map<String, Object> saved = tasks.update((String) snapshot.get("id"), snapshot);
        Map<String, Object> normalizedResult = new LinkedHashMap<>(result);
        normalizedResult.put("state", state);
        return Map.of("task", saved, "result", normalizedResult);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> invoke(String operation, Map<String, Object> body) {
        try {
            Map<String, Object> result = client.postForObject(pythonUrl + "/adaptive-learning/" + operation, body, Map.class);
            if (result == null) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "学习服务未返回状态");
            return result;
        } catch (HttpStatusCodeException failure) {
            HttpStatus status = failure.getStatusCode().value() == 409 ? HttpStatus.CONFLICT
                    : failure.getStatusCode().value() == 422 ? HttpStatus.BAD_REQUEST : HttpStatus.SERVICE_UNAVAILABLE;
            throw new ResponseStatusException(status, "学习服务暂未完成，请保留当前活动并重试");
        } catch (RestClientException failure) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "学习服务暂不可用，当前活动未改变");
        }
    }

    private void checkPaper(Map<String, Object> task, String pdfId) {
        if (!(task.get("paperIds") instanceof List<?> ids) || !ids.contains(pdfId)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "学习论文不属于当前任务");
        }
    }

    private void checkRevision(Object expected, Object actual) {
        if (!(expected instanceof Number n) || n.longValue() < 0 || n.doubleValue() != n.longValue()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "必须提供非负整数版本");
        }
        if (!(actual instanceof Number current) || n.longValue() != current.longValue()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "任务或活动已更新，请刷新后重试");
        }
    }

    private String string(Object value, String field) {
        if (!(value instanceof String text)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " 必须是文字");
        return text;
    }

    private String text(Object value, String field) {
        String text = string(value, field);
        if (text.isBlank()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " 不能为空");
        return text;
    }
}
