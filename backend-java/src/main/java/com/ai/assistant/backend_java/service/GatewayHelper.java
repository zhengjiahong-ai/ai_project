package com.ai.assistant.backend_java.service;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class GatewayHelper {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private GatewayHelper() {}

    public static String encode(String value) {
        return URLEncoder.encode(String.valueOf(value), StandardCharsets.UTF_8).replace("+", "%20");
    }

    @SuppressWarnings("unchecked")
    public static ResponseEntity<Map<String, Object>> forward(
            RestTemplate restTemplate,
            String pythonServiceUrl,
            HttpMethod method,
            String path,
            Map<String, Object> payload) {

        URI uri = UriComponentsBuilder.fromUriString(pythonServiceUrl + path).build(true).toUri();
        HttpEntity<?> entity = payload == null ? HttpEntity.EMPTY : new HttpEntity<>(payload);

        try {
            ResponseEntity<Map> response = restTemplate.exchange(uri, method, entity, Map.class);
            return ResponseEntity.status(response.getStatusCode())
                    .body(normalizeBody(response.getBody()));
        } catch (HttpStatusCodeException error) {
            return ResponseEntity.status(error.getStatusCode())
                    .body(parsePythonErrorBody(error));
        } catch (ResourceAccessException error) {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("status", "error");
            body.put("message", "Python AI service is unreachable. Please try again.");
            return ResponseEntity.status(502).body(body);
        }
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> parsePythonErrorBody(HttpStatusCodeException error) {
        String rawBody = error.getResponseBodyAsString(StandardCharsets.UTF_8);
        if (rawBody != null && !rawBody.isBlank()) {
            try {
                return OBJECT_MAPPER.readValue(rawBody, new TypeReference<>() {});
            } catch (IOException ignored) {
                // Fall through
            }
        }
        Map<String, Object> fallback = new LinkedHashMap<>();
        fallback.put("status", "error");
        fallback.put("message",
                (rawBody != null && !rawBody.isBlank()) ? rawBody : "Python service request failed.");
        return fallback;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> normalizeBody(Map<?, ?> body) {
        Map<String, Object> response = new LinkedHashMap<>();
        if (body != null) {
            for (Map.Entry<?, ?> entry : body.entrySet()) {
                response.put(String.valueOf(entry.getKey()), entry.getValue());
            }
        }
        if (!response.containsKey("status")) {
            response.put("status", "error");
            response.put("message", "Python service returned no response.");
        }
        return response;
    }
}
