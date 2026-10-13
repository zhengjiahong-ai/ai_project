package com.ai.assistant.backend_java.repository;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;
import java.util.Optional;

import com.ai.assistant.backend_java.model.TaskWorkspace;

public interface TaskWorkspaceRepository extends JpaRepository<TaskWorkspace, String> {
    List<TaskWorkspace> findAllByOrderByUpdatedAtDesc();
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select t from TaskWorkspace t where t.id = :id")
    Optional<TaskWorkspace> lockById(@Param("id") String id);
}
