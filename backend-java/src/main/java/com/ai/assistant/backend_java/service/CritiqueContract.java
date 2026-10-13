package com.ai.assistant.backend_java.service;

import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Structural and material checks only; these do not assert scientific validity. */
final class CritiqueContract {
    private CritiqueContract() {}
    static Map<?, ?> validate(Object value, List<?> allowed) {
        if (value == null) return null;
        if (!(value instanceof Map<?, ?> critique) || !Integer.valueOf(2).equals(critique.get("schemaVersion"))) throw invalid();
        if (!(critique.get("scope") instanceof Map<?, ?> scope) || !allowed.equals(scope.get("allowedPaperIds"))
                || !(scope.get("targetPaperIds") instanceof List<?> targets) || targets.isEmpty()
                || !allowed.containsAll(targets) || new HashSet<>(targets).size() != targets.size()
                || (scope.get("primaryPaperId") != null && !targets.contains(scope.get("primaryPaperId")))) throw invalid();
        Set<String> claims = ids(critique.get("claims"), allowed, true);
        Set<String> issues = ids(critique.get("issues"), allowed, true);
        Set<String> pending = ids(critique.get("pending"), allowed, false);
        for (Object raw : (List<?>) critique.get("claims")) {
            Map<?, ?> claim = (Map<?, ?>) raw;
            if (!Set.of("reported", "inference").contains(claim.get("kind")) || !(claim.get("text") instanceof String text)
                    || text.isBlank() || !(claim.get("references") instanceof List<?>)) throw invalid();
            for (Object rawReference : (List<?>) claim.get("references")) {
                if (!(rawReference instanceof Map<?, ?> reference)
                        || (reference.get("pdfId") != null && !allowed.contains(reference.get("pdfId")))) throw invalid();
            }
        }
        for (Object raw : (List<?>) critique.get("issues")) {
            Map<?, ?> issue = (Map<?, ?>) raw;
            if (!claims.contains(issue.get("conclusionClaimId")) || !(issue.get("supportClaimIds") instanceof List<?> support)
                    || !claims.containsAll(support) || (issue.get("implicationClaimId") != null && !claims.contains(issue.get("implicationClaimId")))
                    || !(issue.get("relatedPendingIds") instanceof List<?> related) || !pending.containsAll(related)) throw invalid();
        }
        if (!(critique.get("presentation") instanceof Map<?, ?> presentation)
                || !members(presentation.get("leadClaimIds"), claims) || !members(presentation.get("chatIssueIds"), issues)
                || !members(presentation.get("artifactIssueIds"), issues)) throw invalid();
        return critique;
    }
    private static boolean members(Object value, Set<String> ids) { return value instanceof List<?> list && ids.containsAll(list); }
    private static Set<String> ids(Object value, List<?> allowed, boolean papersRequired) {
        if (!(value instanceof List<?> list)) throw invalid();
        Set<String> ids = new HashSet<>();
        for (Object raw : list) {
            if (!(raw instanceof Map<?, ?> item) || !(item.get("id") instanceof String id) || id.isBlank() || !ids.add(id)) throw invalid();
            if (papersRequired && (!(item.get("paperIds") instanceof List<?> papers) || papers.isEmpty() || !allowed.containsAll(papers))) throw invalid();
        }
        return ids;
    }
    private static ResponseStatusException invalid() { return new ResponseStatusException(HttpStatus.BAD_GATEWAY, "批判结构不符合材料范围或观点依赖"); }
}
