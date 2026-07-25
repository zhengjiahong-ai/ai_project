import React from 'react';

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
  AgentTaskHistorySection,
  AgentHumanFinalReview,
  AgentTaskPlanSection,
  AgentTaskPromptBubble,
  AgentTimelineSection,
  AgentToolCallsSection,
} from './AgentWorkspaceMainSections.jsx';

const AgentWorkspaceMain = ({
  activeProject,
  currentTask,
  projectTasks,
  currentStageLabel,
  prompt,
  onPromptChange,
  onQuickPrompt,
  onCreateTask,
  onRefresh,
  onSelectTask,
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
  theme = 'light',
}) => (
  <main className="agent-panel min-h-0 min-w-0 overflow-hidden rounded-[26px]">
    <AgentWorkspaceHeader
      activeProject={activeProject}
      currentTask={currentTask}
      currentStageLabel={currentStageLabel}
      projectTaskCount={projectTasks.length}
      onRefresh={onRefresh}
    />

    <div className="agent-main-surface grid h-[calc(100%-61px)] min-h-0 grid-rows-[minmax(0,1fr)_auto]">
      <div className="min-h-0 overflow-y-auto px-5 py-5">
        <div className="space-y-4">
          <AgentTaskHistorySection tasks={projectTasks} currentTask={currentTask} onSelectTask={onSelectTask} />

          {currentTask ? (
            <>
              <AgentTaskPromptBubble task={currentTask} prompt={prompt} />

              <AgentResponseCard currentTask={currentTask} currentStageLabel={currentStageLabel}>
                <AgentTimelineSection currentTask={currentTask} />
                <AgentTaskPlanSection currentTask={currentTask} activeProject={activeProject} onReviewPlan={onReviewPlan} />
                <AgentIntermediateArtifactsSection activeProject={activeProject} currentTask={currentTask} />
                <AgentComparisonSection
                  activeProject={activeProject}
                  currentTask={currentTask}
                  activePaperId={activePaperId}
                  onCaptureArtifact={onCaptureArtifact}
                />
                <AgentConflictSection currentTask={currentTask} onJumpToSource={onJumpToSource} />
                <AgentCodeExecutionSection currentTask={currentTask} />
                <AgentToolCallsSection currentTask={currentTask} />
                {currentTask?.debateResult?.agent_analyses?.length > 0 ? (
                  <DebateView debateResult={currentTask.debateResult} theme={theme} />
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
            <AgentTaskPromptBubble task={null} prompt={prompt} />
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

export default AgentWorkspaceMain;
