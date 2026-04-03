package com.ai.assistant.backend_java.repository;

import com.ai.assistant.backend_java.model.Paper;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaperRepository extends JpaRepository<Paper, String> {
}
