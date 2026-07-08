# Agent Architecture Refactor Design

Date: 2026-07-08

## Goal

Refactor the current Agent architecture to prioritize clarity of boundaries and lifecycle semantics before pursuing stronger execution quality. The refactor may change API contracts and internal persistence models, but should preserve the product's core workflow:

1. Create or choose an Agent project.
2. Start a research run for a focused question.
3. Review the generated plan before execution.
4. Execute the run and produce structured research outputs.
5. Review the final draft before completion.
6. Inspect timeline and trace information separately from core results.

This refactor should move the system away from a single expanding "task snapshot" object and toward a small set of explicit domain resources.

## Current Problems

The existing Agent implementation has already split some responsibilities between `agent_project_service.py` and `agent_orchestrator.py`, but the overall design is still organized around a single mutable task snapshot.

This creates several problems:

1. Lifecycle state, review state, execution progress, UI timeline, and result artifacts are mixed into one task object.
2. The backend orchestration layer leaks intermediate execution structure directly into public API contracts.
3. Frontend state normalization depends on many low-level task fields, which makes internal backend changes expensive.
4. Persistence and business logic are coupled, especially in `agent_project_service.py`.
5. The current `status` and `stage` fields are overloaded and force clients to infer workflow state from multiple sources.
6. Future execution changes such as queued workers, stronger orchestration, or LangGraph-style execution would remain constrained by the current snapshot contract.

## Design Principles

1. Separate workflow control from research results.
2. Use one primary lifecycle state for each run.
3. Model human review as explicit workflow resources, not loose nested fields.
4. Treat timeline, trace, and artifacts as different forms of truth with different purposes.
5. Preserve a frontend-friendly aggregate API while keeping the domain model resource-oriented underneath.
6. Keep external search authorization and safety boundaries explicit in the domain model.
7. Make persistence serve the domain model rather than define it.

## Target Architecture

The refactored Agent architecture should be a hybrid model:

1. A workflow-oriented domain model with explicit project, run, review, artifact, and timeline resources.
2. A small number of aggregate "workspace" APIs for frontend convenience.

The system should be organized around these core resources.

### 1. AgentProject

Represents the long-lived research workspace.

Responsibilities:

1. Store project title, goal, selected papers, and default constraints.
2. Reference the latest run and latest completed run.
3. Stay independent from execution-specific details.

It must not store run-scoped review state, evidence, timeline, or draft report content.

### 2. AgentRun

Represents one concrete research execution inside a project.

Responsibilities:

1. Represent one user prompt or research question.
2. Own the single authoritative workflow lifecycle state.
3. Reference trace and related review and artifact resources.
4. Record failure and completion metadata.

It must not directly embed all evidence, report, or timeline content.

### 3. PlanReviewPacket

Represents the first human gate before execution.

Responsibilities:

1. Present generated plan items.
2. Present focused papers and constraints.
3. Capture external search authorization.
4. Store review decision and notes.

### 4. FinalReviewPacket

Represents the second human gate after execution.

Responsibilities:

1. Present a compact review summary of the run outputs.
2. Present risk items derived from the final artifacts.
3. Store the reviewer decision and notes.

### 5. RunArtifacts

Represents structured research outputs for one run.

Responsibilities:

1. Store evidence items.
2. Store tool-call summary or audit-facing tool usage summary.
3. Store comparison tables, findings, conflicts, open questions, and draft report.
4. Store external evidence summary and graph-context summary when applicable.

### 6. RunTimeline

Represents user-facing progress history.

Responsibilities:

1. Store timeline entries intended for UI presentation.
2. Represent workflow progress in a readable way.
3. Avoid becoming a backend debug log.

### 7. TraceSummary

Remains a separate observational resource.

Responsibilities:

1. Provide sanitized trace and cost information.
2. Stay independent from core workflow and artifact truth.

### 8. WorkspaceView

Represents a read-only aggregate view for the frontend.

Responsibilities:

1. Combine project, active run, pending review, latest artifacts, recent runs, and timeline.
2. Make the UI simple without turning the aggregate into the domain truth.

## Backend Layering

The current `agent_project_service.py` should be decomposed into smaller services with single responsibilities.

### project_service

Owns `AgentProject`.

Responsibilities:

1. Create, update, and delete projects.
2. Manage paper membership and default constraints.
3. Query project-level summaries.

### run_service

Owns `AgentRun`.

Responsibilities:

1. Create runs.
2. Drive lifecycle transitions.
3. Cancel runs.
4. Mark runs as failed, completed, or interrupted after restart.

This must be the only layer allowed to mutate `run.status`.

### review_service

Owns both review packets.

Responsibilities:

1. Generate and store plan review packets.
2. Accept plan review decisions and unblock execution.
3. Generate and store final review packets.
4. Accept final review decisions and finalize runs.

### execution_orchestrator

Evolves from the current `agent_orchestrator.py`.

Responsibilities:

1. Execute the research flow for an approved run.
2. Call tools, collect evidence, perform synthesis, and produce structured results.
3. Return a pure execution result rather than mutate public API objects directly.

### artifact_service

Owns `RunArtifacts`.

Responsibilities:

1. Persist execution outputs.
2. Serve stable result structures to downstream consumers.
3. Derive risk inputs for final review.

### timeline_service

Owns `RunTimeline`.

Responsibilities:

1. Append user-visible progress entries.
2. Read timeline entries for frontend display.
3. Keep display timeline separate from debug logging and trace.

### workspace_query_service

Owns aggregate read models.

Responsibilities:

1. Join project, active run, pending review, latest artifacts, recent runs, and timeline.
2. Serve frontend-friendly "workspace" responses.

### repositories

Persistence should move behind repository boundaries.

Expected repositories:

1. `project_repository`
2. `run_repository`
3. `review_repository`
4. `artifact_repository`
5. `timeline_repository`

Repositories should know SQLite schema details; services should not.

## Run Lifecycle State Machine

The new lifecycle should use one primary run status plus one optional execution phase.

### Primary `run.status`

Allowed values:

1. `draft`
2. `awaiting_plan_review`
3. `queued`
4. `running`
5. `awaiting_final_review`
6. `completed`
7. `failed`
8. `cancelled`

### Optional `run.executionPhase`

Only meaningful while `run.status=running`.

Recommended values:

1. `planning_context`
2. `retrieving_evidence`
3. `synthesizing`
4. `assembling_artifacts`

### Allowed Transitions

1. `draft -> awaiting_plan_review`
2. `awaiting_plan_review -> queued`
3. `awaiting_plan_review -> cancelled`
4. `queued -> running`
5. `queued -> failed`
6. `queued -> cancelled`
7. `running -> awaiting_final_review`
8. `running -> failed`
9. `running -> cancelled`
10. `awaiting_final_review -> completed`
11. `awaiting_final_review -> failed`
12. `awaiting_final_review -> cancelled`

### Forbidden Semantics

1. Do not infer workflow state from timeline entries.
2. Do not infer workflow state from nested review fields.
3. Do not mutate artifacts after entering `awaiting_final_review`, except through an explicit rerun or regenerated review packet flow defined later.
4. Do not jump directly from plan review wait state to completed.

## API Shape

The external API should be hybrid: resource-oriented underneath, with aggregate endpoints for frontend simplicity.

### Core Resource Endpoints

1. `POST /api/agent-projects`
2. `GET /api/agent-projects`
3. `GET /api/agent-projects/{projectId}`
4. `PATCH /api/agent-projects/{projectId}`
5. `DELETE /api/agent-projects/{projectId}`
6. `POST /api/agent-projects/{projectId}/runs`
7. `GET /api/agent-projects/{projectId}/runs?limit=...`
8. `GET /api/agent-runs/{runId}`
9. `POST /api/agent-runs/{runId}/cancel`
10. `GET /api/agent-runs/{runId}/plan-review`
11. `POST /api/agent-runs/{runId}/plan-review`
12. `GET /api/agent-runs/{runId}/final-review`
13. `POST /api/agent-runs/{runId}/final-review`
14. `GET /api/agent-runs/{runId}/artifacts`
15. `GET /api/agent-runs/{runId}/timeline`
16. `GET /api/agent-traces/{traceId}`

### Aggregate Frontend Endpoints

1. `GET /api/agent-projects/{projectId}/workspace`

This endpoint should return a read model that includes:

1. project summary
2. active run summary
3. pending review packet summary
4. latest artifacts summary
5. recent runs summary
6. recent timeline entries
7. optional UI hints

The aggregate endpoint should remain read-only and should not become the authoritative persistence shape.

## Data Model Split

### AgentProject

Recommended fields:

1. `projectId`
2. `title`
3. `goal`
4. `paperIds`
5. `defaultConstraints`
6. `latestRunId`
7. `latestCompletedRunId`
8. `createdAt`
9. `updatedAt`

### AgentRun

Recommended fields:

1. `runId`
2. `projectId`
3. `status`
4. `executionPhase`
5. `prompt`
6. `focusedPaperIds`
7. `constraints`
8. `context`
9. `traceId`
10. `failureCode`
11. `failureMessage`
12. `createdAt`
13. `updatedAt`
14. `startedAt`
15. `finishedAt`

### PlanReviewPacket

Recommended fields:

1. `runId`
2. `version`
3. `status`
4. `planItems`
5. `focusedPaperIds`
6. `constraints`
7. `externalSearchRequest`
8. `reviewNotes`
9. `reviewedBy`
10. `reviewedAt`

### FinalReviewPacket

Recommended fields:

1. `runId`
2. `version`
3. `status`
4. `summary`
5. `riskItems`
6. `reviewNotes`
7. `reviewedBy`
8. `reviewedAt`

### RunArtifacts

Recommended fields:

1. `runId`
2. `version`
3. `evidenceItems`
4. `toolCallSummary`
5. `comparisonTable`
6. `findings`
7. `conflicts`
8. `openQuestions`
9. `draftReport`
10. `externalEvidenceSummary`
11. `graphContextSummary`
12. `createdAt`
13. `updatedAt`

### RunTimeline

Recommended fields:

1. `runId`
2. `entries`

Timeline entry fields:

1. `id`
2. `type`
3. `title`
4. `detail`
5. `phase`
6. `createdAt`
7. `meta`

### WorkspaceView

Recommended fields:

1. `project`
2. `activeRun`
3. `pendingReview`
4. `latestArtifacts`
5. `recentRuns`
6. `timeline`
7. `uiHints`

## External Search Modeling

The current external-search authorization semantics should be simplified in the domain model.

Instead of relying on one special plan item plus run-level config duplication, the authoritative review object should carry an explicit external search request:

1. `allowed`
2. `providerPolicy`
3. `budget`
4. `reviewReason`

Plan items may still include an "External academic search" row for display, but that row should not be the only authoritative source of authorization.

## Persistence Direction

The SQLite model should evolve from broad task snapshots to normalized resource tables. A final physical schema can vary, but the logical split should be:

1. `agent_projects`
2. `agent_runs`
3. `agent_plan_reviews`
4. `agent_final_reviews`
5. `agent_run_artifacts`
6. `agent_run_timeline_entries`

Compatibility support may temporarily read old task snapshots and project them into the new model, but newly written state should follow the new resource shape.

## Migration Strategy

This refactor should be incremental rather than a full rewrite.

### Phase 1: Introduce the New Domain Model Internally

1. Add new domain objects and repositories.
2. Keep current public endpoints working through adapters.
3. Make `agent_orchestrator` return execution results instead of mutating task-like structures.

### Phase 2: Split Persistence

1. Write new resource-shaped tables.
2. Add projection from old snapshots when needed for compatibility.
3. Move restart recovery logic to `run_service` plus repositories.

### Phase 3: Introduce New Resource APIs

1. Add run, review, artifact, timeline, and workspace endpoints.
2. Keep old task endpoints as compatibility shims if necessary.
3. Let frontend progressively migrate to `workspace` and `run` resources.

### Phase 4: Remove the Legacy Task Snapshot Contract

1. Remove task-shaped source-of-truth writes.
2. Keep only adapter-level legacy support if still needed temporarily.
3. Update documentation, fixtures, and tests to the new contract.

## Testing Strategy

The refactor should restructure tests around resource boundaries.

### Unit Tests

1. `run_service` state transitions
2. `review_service` gate behavior
3. `artifact_service` derivation and persistence
4. `workspace_query_service` aggregation
5. `execution_orchestrator` output contracts

### Contract Tests

1. new resource API fixtures
2. workspace aggregate fixture
3. backward-compatibility coverage only where intentionally supported

### Persistence Tests

1. restart recovery by run status
2. review packet restoration
3. artifact restoration
4. timeline restoration

### Frontend Tests

1. workspace loading from aggregate view
2. review flows driven by review packet resources
3. timeline display independent from run status
4. artifact display independent from lifecycle metadata

## Non-Goals

This design intentionally does not include:

1. A stronger reasoning or retrieval algorithm in the same phase.
2. Full LangGraph adoption in the first refactor step.
3. Broad changes to non-Agent product areas.
4. Changes to the security boundaries for external search or code execution.

## Recommendation

The recommended implementation direction is:

1. Keep the product workflow unchanged from the user's perspective.
2. Replace the internal "task snapshot" center of gravity with explicit project, run, review, artifact, and timeline resources.
3. Expose a hybrid API with a stable aggregate workspace endpoint for the frontend.
4. Use a single primary run lifecycle status and demote fine-grained execution progress to `executionPhase` and timeline entries.

This gives the Agent system a clearer architecture without forcing the frontend to become a resource orchestration engine and without freezing future execution improvements behind the current task contract.
