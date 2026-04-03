package com.ai.assistant.backend_java.repository;

import com.ai.assistant.backend_java.model.ChatMessage;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, Long> {
    List<ChatMessage> findByPdfIdOrderByTimestampAsc(String pdfId);
}
