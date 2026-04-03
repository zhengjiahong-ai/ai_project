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

    @PrePersist
    protected void onCreate() {
        uploadTime = LocalDateTime.now();
    }
}
