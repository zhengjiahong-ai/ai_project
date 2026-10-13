package com.ai.assistant.backend_java.controller;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import jakarta.persistence.OptimisticLockException;
import java.util.Map;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice(assignableTypes = TaskWorkspaceController.class)
public class TaskWorkspaceErrorHandler {
    @ExceptionHandler({ObjectOptimisticLockingFailureException.class, OptimisticLockException.class,
            DataIntegrityViolationException.class})
    public ResponseEntity<Map<String, Object>> conflict(Exception exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("code", "TASK_CONFLICT", "message", "任务已在其他位置更新，请刷新后核对。本地草稿会保留。"));
    }
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, Object>> requestFailure(ResponseStatusException exception) {
        return ResponseEntity.status(exception.getStatusCode()).body(Map.of("code", exception.getStatusCode().value() == 409 ? "TASK_CONFLICT" : "TASK_REQUEST_FAILED",
                "message", exception.getReason() == null ? "任务请求未完成" : exception.getReason()));
    }
}
