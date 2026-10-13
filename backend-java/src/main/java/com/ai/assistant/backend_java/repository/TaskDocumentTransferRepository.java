package com.ai.assistant.backend_java.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.ai.assistant.backend_java.model.TaskDocumentTransfer;

public interface TaskDocumentTransferRepository extends JpaRepository<TaskDocumentTransfer, String> {}
