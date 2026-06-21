package com.ai.assistant.backend_java.controller;

import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Map;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import com.ai.assistant.backend_java.service.AiService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

@WebMvcTest(AcademicController.class)
class ApiContractSmokeTest {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static JsonNode operations;

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private AiService aiService;

    @BeforeAll
    static void loadSharedContract() throws Exception {
        Path contractPath = resolveContractPath();
        JsonNode root = MAPPER.readTree(Files.readString(contractPath));
        if (root.path("schemaVersion").asInt() != 1) {
            throw new AssertionError("Unsupported API contract schemaVersion");
        }
        operations = root.path("operations");
    }

    @Test
    void readerApiRoutesMatchSharedContract() throws Exception {
        JsonNode chat = operation("chat");
        Map<String, Object> chatRequest = asMap(chat.path("frontendRequest"));
        when(aiService.chat(anyMap())).thenReturn(asMap(chat.path("gatewayResponse")));
        assertResponse(post(chat.path("javaPath").asText())
                .contentType(MediaType.APPLICATION_JSON)
                .content(MAPPER.writeValueAsString(chatRequest)), chat);
        verify(aiService).chat(eq(chatRequest));

        JsonNode critical = operation("critical");
        when(aiService.criticalReading("paper-contract-1"))
                .thenReturn(asMap(critical.path("gatewayResponse")));
        MvcResult criticalResult = mockMvc.perform(post(critical.path("javaPath").asText()))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode criticalPayload = MAPPER.readTree(criticalResult.getResponse().getContentAsString());
        assertContract(criticalPayload.path("analysis"), critical.path("pythonResponseContract"), "response.analysis");

        JsonNode background = operation("background");
        Map<String, Object> backgroundRequest = asMap(background.path("frontendRequest"));
        when(aiService.backgroundKnowledge(anyMap())).thenReturn(asMap(background.path("gatewayResponse")));
        assertResponse(post(background.path("javaPath").asText())
                .contentType(MediaType.APPLICATION_JSON)
                .content(MAPPER.writeValueAsString(backgroundRequest)), background);
        verify(aiService).backgroundKnowledge(eq(backgroundRequest));
    }

    @Test
    void researchAndTraceRoutesMatchSharedContract() throws Exception {
        JsonNode research = operation("research");
        Map<String, Object> request = asMap(research.path("frontendRequest"));
        when(aiService.createResearchTask(anyMap()))
                .thenReturn(ResponseEntity.ok(asMap(research.path("gatewayResponse"))));
        assertResponse(post(research.path("javaPath").asText())
                .contentType(MediaType.APPLICATION_JSON)
                .content(MAPPER.writeValueAsString(request)), research);
        verify(aiService).createResearchTask(eq(request));

        JsonNode trace = operation("trace");
        when(aiService.getTrace("trace-contract-1"))
                .thenReturn(ResponseEntity.ok(asMap(trace.path("gatewayResponse"))));
        assertResponse(get(trace.path("javaPath").asText()), trace);
    }

    @Test
    void agentRoutesMatchSharedContract() throws Exception {
        JsonNode project = operation("agent-projects");
        Map<String, Object> projectRequest = asMap(project.path("frontendRequest"));
        when(aiService.createAgentProject(anyMap()))
                .thenReturn(ResponseEntity.ok(asMap(project.path("gatewayResponse"))));
        assertResponse(post(project.path("javaPath").asText())
                .contentType(MediaType.APPLICATION_JSON)
                .content(MAPPER.writeValueAsString(projectRequest)), project);
        verify(aiService).createAgentProject(eq(projectRequest));

        JsonNode task = operation("agent-tasks");
        Map<String, Object> taskRequest = asMap(task.path("frontendRequest"));
        when(aiService.createAgentTask(eq("project-contract-1"), anyMap()))
                .thenReturn(ResponseEntity.ok(asMap(task.path("gatewayResponse"))));
        assertResponse(post(task.path("javaPath").asText())
                .contentType(MediaType.APPLICATION_JSON)
                .content(MAPPER.writeValueAsString(taskRequest)), task);
        verify(aiService).createAgentTask("project-contract-1", taskRequest);

        JsonNode trace = operation("agent-traces");
        when(aiService.getAgentTrace("agent-trace-contract-1"))
                .thenReturn(ResponseEntity.ok(asMap(trace.path("gatewayResponse"))));
        assertResponse(get(trace.path("javaPath").asText()), trace);
    }

    private MvcResult assertResponse(
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
            JsonNode fixture) throws Exception {
        MvcResult result = mockMvc.perform(request)
                .andExpect(status().is(fixture.path("statusCode").asInt()))
                .andReturn();
        JsonNode payload = MAPPER.readTree(result.getResponse().getContentAsString());
        assertContract(payload, fixture.path("pythonResponseContract"), "response");
        return result;
    }

    private static void assertContract(JsonNode value, JsonNode schema, String path) {
        String type = schema.path("type").asText();
        boolean validType = switch (type) {
            case "object" -> value.isObject();
            case "array" -> value.isArray();
            case "string" -> value.isTextual();
            case "number" -> value.isNumber();
            case "integer" -> value.isIntegralNumber();
            case "boolean" -> value.isBoolean();
            case "null" -> value.isNull();
            default -> true;
        };
        if (!validType) {
            throw new AssertionError(path + " expected type " + type + " but was " + value.getNodeType());
        }
        if (schema.has("enum")) {
            boolean found = false;
            for (JsonNode candidate : schema.path("enum")) {
                found |= candidate.equals(value);
            }
            if (!found) {
                throw new AssertionError(path + " is outside declared enum");
            }
        }
        if (value.isObject()) {
            for (JsonNode required : schema.path("required")) {
                if (!value.has(required.asText())) {
                    throw new AssertionError(path + "." + required.asText() + " is required");
                }
            }
            Iterator<Map.Entry<String, JsonNode>> fields = schema.path("properties").fields();
            while (fields.hasNext()) {
                Map.Entry<String, JsonNode> field = fields.next();
                if (value.has(field.getKey())) {
                    assertContract(value.path(field.getKey()), field.getValue(), path + "." + field.getKey());
                }
            }
        }
        if (value.isArray() && schema.has("items")) {
            for (int index = 0; index < value.size(); index++) {
                assertContract(value.get(index), schema.path("items"), path + "[" + index + "]");
            }
        }
    }

    private static JsonNode operation(String name) {
        for (JsonNode operation : operations) {
            if (name.equals(operation.path("operation").asText())) {
                return operation;
            }
        }
        throw new AssertionError("Missing shared contract operation: " + name);
    }

    private static Map<String, Object> asMap(JsonNode node) {
        return MAPPER.convertValue(node, new TypeReference<>() {});
    }

    private static Path resolveContractPath() {
        Path current = Path.of("").toAbsolutePath();
        Path[] candidates = {
                current.resolve("../contracts/api-contract-smoke.json").normalize(),
                current.resolve("contracts/api-contract-smoke.json").normalize(),
                current.resolve("ai_project/contracts/api-contract-smoke.json").normalize()
        };
        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate)) {
                return candidate;
            }
        }
        throw new AssertionError("Shared API contract fixture not found from " + current);
    }
}
