package com.ai.assistant.backend_java.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "task_document_transfers")
public class TaskDocumentTransfer {
    @Id
    @Column(length = 255)
    private String id;
    @Column(nullable = false, length = 2000)
    private String identity;
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getIdentity() { return identity; }
    public void setIdentity(String identity) { this.identity = identity; }
}
