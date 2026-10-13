package com.ai.assistant.backend_java.model;

import jakarta.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;

@Entity
@Data
@Table(name = "papers")
public class Paper {
    @Id
    private String id; // Use the filename or a unique hash as ID
    
    private String fileName;
    
    private LocalDateTime uploadTime;

    private String processingStatus;
    private String aiAnalysisStatus;
    private String processingAttemptId;
    private String processingError;

    @Lob
    @com.fasterxml.jackson.annotation.JsonIgnore
    @lombok.ToString.Exclude
    private byte[] pdfBytes;

    @Lob
    @com.fasterxml.jackson.annotation.JsonIgnore
    @lombok.ToString.Exclude
    private String analysisJson;

    @PrePersist
    protected void onCreate() {
        uploadTime = LocalDateTime.now();
    }
}
