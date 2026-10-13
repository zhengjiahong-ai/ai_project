package com.ai.assistant.backend_java.repository;
import org.springframework.data.jpa.repository.JpaRepository;
import com.ai.assistant.backend_java.model.TaskMigrationSnapshot;
public interface TaskMigrationSnapshotRepository extends JpaRepository<TaskMigrationSnapshot, String> {}
