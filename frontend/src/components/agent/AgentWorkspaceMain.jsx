import React from 'react';

import DebateLauncher from './DebateLauncher.jsx';
import DebateView from './DebateView';

import AgentTaskComposer, {
  AgentResponseCard,
  AgentWorkspaceHeader,
} from './AgentWorkspaceMainComposer.jsx';
import {
  AgentCodeExecutionSection,
  AgentComparisonSection,
  AgentConflictSection,
  AgentDraftReportSection,
  AgentIntermediateArtifactsSection,
  AgentHumanFinalReview,
  AgentTaskPlanSection,
  AgentTaskPromptBubble,
  AgentTimelineSection,
  AgentToolCallsSection,
} from './AgentWorkspaceMainSections.jsx';
import { AgentEvidenceListSection } from './AgentWorkspaceEvidenceSections.jsx';

const AgentWorkspaceMain = ({
  activeProject,
  currentTask,
  stateError,
  projectTasks,
  messages,
  currentStageLabel,
  prompt,
  onPromptChange,
  onQuickPrompt,
  onCreateTask,
  onRefresh,
  onCancelTask,
  onRetryTask,
  onReviewPlan,
  onReviewFinal,
  activePaperId,
  onCaptureArtifact,
  onJumpToSource,
  allowExternalSearch,
  onAllowExternalSearchChange,
  allowWebSearch,
  onAllowWebSearchChange,
  allowIterativeSearch,
  onAllowIterativeSearchChange,
  allowKnowledgeGraph,
  onAllowKnowledgeGraphChange,
  domain,
  onDomainChange,
  onDebateComplete,
  theme = 'light',
}) => {
  const debateResult = currentTask?.debateResult;
  const previousMessages = (messages || []).filter((message) => message.runId !== currentTask?.taskId);
  const currentRunHasUserMessage = (messages || []).some(
    (message) => message.runId === currentTask?.taskId && message.role === 'user',
  );

  return (
    <main className="agent-panel min-h-0 min-w-0 overflow-hidden rounded-[26px]">
      <AgentWorkspaceHeader
        activeProject={activeProject}
        currentTask={currentTask}
        currentStageLabel={currentStageLabel}
        projectTaskCount={projectTasks.length}
        onRefresh={onRefresh}
        onCancelTask={onCancelTask}
        onRetryTask={onRetryTask}
        extraActions={
          <DebateLauncher
            activeProject={activeProject}
            onDebateComplete={onDebateComplete}
            theme={theme}
          />
        }
      />

      <div className="agent-main-surface grid h-[calc(100%-64px)] min-h-0 grid-rows-[minmax(0,1fr)_auto]">
        <div className="min-h-0 overflow-y-auto px-5 py-5">
          <div className="mx-auto max-w-[1120px] space-y-5">
            {stateError && <div className="agent-chip-danger rounded-md px-4 py-3 text-xs">{stateError}</div>}
            {previousMessages.map((message) => message.role === 'user' ? (
              <AgentTaskPromptBubble
                key={message.messageId}
                task={{ prompt: message.content, createdAt: message.createdAt }}
              />
            ) : (
              <AgentResponseCard
                key={message.messageId}
                currentTask={{ taskId: message.runId, status: message.status || 'succeeded', draftReport: message.content }}
                currentStageLabel="已完成"
              />
            ))}
            {currentTask ? (
              <>
                {!currentRunHasUserMessage && <AgentTaskPromptBubble task={currentTask} prompt={prompt} />}
                {currentRunHasUserMessage && (
                  <AgentTaskPromptBubble
                    task={{
                      prompt: messages.find((message) => message.runId === currentTask.taskId && message.role === 'user')?.content,
                      createdAt: messages.find((message) => message.runId === currentTask.taskId && message.role === 'user')?.createdAt,
                    }}
                  />
                )}

                <AgentResponseCard currentTask={currentTask} currentStageLabel={currentStageLabel}>
                  <details className="agent-research-chain mt-4">
                    <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-sm font-semibold">
                      <span>研究链 · 点击展开完整过程</span>
                      <span className="agent-muted text-[11px]">{(currentTask?.events || []).length} 步 · {(currentTask?.evidenceItems || []).length} 条证据</span>
                    </summary>
                    <div className="border-t px-4 pb-4">
                      <AgentTimelineSection currentTask={currentTask} />
                      <AgentTaskPlanSection currentTask={currentTask} activeProject={activeProject} onReviewPlan={onReviewPlan} />
                      <AgentIntermediateArtifactsSection activeProject={activeProject} currentTask={currentTask} />
                      <AgentComparisonSection activeProject={activeProject} currentTask={currentTask} activePaperId={activePaperId} onCaptureArtifact={onCaptureArtifact} />
                      <AgentConflictSection currentTask={currentTask} onJumpToSource={onJumpToSource} />
                      <AgentCodeExecutionSection currentTask={currentTask} />
                      <AgentToolCallsSection currentTask={currentTask} />
                      <AgentEvidenceListSection activeProject={activeProject} currentTask={currentTask} activePaperId={activePaperId} onCaptureArtifact={onCaptureArtifact} onJumpToSource={onJumpToSource} />
                    </div>
                  </details>
                  {debateResult?.agent_analyses?.length > 0 ? (
                    <DebateView debateResult={debateResult} theme={theme} />
                  ) : (
                    <AgentDraftReportSection
                      activeProject={activeProject}
                      currentTask={currentTask}
                      activePaperId={activePaperId}
                      onCaptureArtifact={onCaptureArtifact}
                      onJumpToSource={onJumpToSource}
                    />
                  )}
                  {currentTask.status === 'awaiting_final_review' && (
                    <AgentHumanFinalReview currentTask={currentTask} onReviewFinal={onReviewFinal} />
                  )}
                </AgentResponseCard>
              </>
            ) : (
              <div className="agent-empty-state py-16 text-center">
                <div className="agent-title text-base font-bold">从一个研究问题开始</div>
                <p className="agent-muted mt-2 text-sm">选择或创建项目，然后在下方建立研究任务。</p>
              </div>
            )}
          </div>
        </div>

        <AgentTaskComposer
          activeProject={activeProject}
          prompt={prompt}
          onPromptChange={onPromptChange}
          onQuickPrompt={onQuickPrompt}
          onCreateTask={onCreateTask}
          allowExternalSearch={allowExternalSearch}
          onAllowExternalSearchChange={onAllowExternalSearchChange}
          allowWebSearch={allowWebSearch}
          onAllowWebSearchChange={onAllowWebSearchChange}
          allowIterativeSearch={allowIterativeSearch}
          onAllowIterativeSearchChange={onAllowIterativeSearchChange}
          allowKnowledgeGraph={allowKnowledgeGraph}
          onAllowKnowledgeGraphChange={onAllowKnowledgeGraphChange}
          domain={domain}
          onDomainChange={onDomainChange}
        />
      </div>
    </main>
  );
};

export default AgentWorkspaceMain;
