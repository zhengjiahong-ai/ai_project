package com.ai.assistant.backend_java.model;
import jakarta.persistence.*;
@Entity
@Table(name = "task_migration_snapshots")
public class TaskMigrationSnapshot {
    @Id @Column(length = 255) private String id;
    @Column(nullable = false, length = 255) private String taskId;
    @Lob @Column(nullable = false) private String payloadJson;
    public String getId() { return id; }
    public void setId(String value) { id = value; }
    public String getTaskId() { return taskId; }
    public void setTaskId(String value) { taskId = value; }
    public String getPayloadJson() { return payloadJson; }
    public void setPayloadJson(String value) { payloadJson = value; }
}
