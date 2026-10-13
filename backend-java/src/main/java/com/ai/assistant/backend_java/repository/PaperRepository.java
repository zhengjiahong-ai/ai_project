package com.ai.assistant.backend_java.repository;

import com.ai.assistant.backend_java.model.Paper;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaperRepository extends JpaRepository<Paper, String> {
    java.util.List<Paper> findByProcessingStatusInOrAiAnalysisStatusIn(
            java.util.Collection<String> processingStatuses, java.util.Collection<String> aiStatuses);
    @org.springframework.data.jpa.repository.Lock(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE)
    @org.springframework.data.jpa.repository.Query("select p from Paper p where p.id = :id")
    java.util.Optional<Paper> lockById(@org.springframework.data.repository.query.Param("id") String id);
}
