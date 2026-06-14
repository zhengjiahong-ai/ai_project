import React from 'react';

import AgentTaskComposer, {
  AgentResponseCard,
  AgentWorkspaceHeader,
} from './AgentWorkspaceMainComposer.jsx';
import {
  AgentComparisonSection,
  AgentConflictSection,
  AgentDraftReportSection,
  AgentIntermediateArtifactsSection,
  AgentTaskHistorySection,
  AgentTaskPlanSection,
  AgentTaskPromptBubble,
  AgentTimelineSection,
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
}) => (
  <main className="min-h-0 min-w-0 overflow-hidden rounded-[26px] border border-[#e6deef] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(250,248,255,0.96))] shadow-[0_16px_40px_rgba(49,24,82,0.08)]">
    <AgentWorkspaceHeader
      activeProject={activeProject}
      currentTask={currentTask}
      currentStageLabel={currentStageLabel}
      projectTaskCount={projectTasks.length}
      onRefresh={onRefresh}
    />

    <div className="grid h-[calc(100%-61px)] min-h-0 grid-rows-[minmax(0,1fr)_auto] bg-[linear-gradient(180deg,#fcfbfe,#f8f5fb)]">
      <div className="min-h-0 overflow-y-auto px-5 py-5">
        <div className="space-y-4">
          <AgentTaskHistorySection tasks={projectTasks} currentTask={currentTask} onSelectTask={onSelectTask} />

          {currentTask ? (
            <>
              <AgentTaskPromptBubble task={currentTask} prompt={prompt} />

              <AgentResponseCard currentTask={currentTask} currentStageLabel={currentStageLabel}>
                <AgentTimelineSection currentTask={currentTask} />
                <AgentTaskPlanSection currentTask={currentTask} />
                <AgentIntermediateArtifactsSection activeProject={activeProject} currentTask={currentTask} />
                <AgentComparisonSection currentTask={currentTask} />
                <AgentConflictSection currentTask={currentTask} />
                <AgentDraftReportSection currentTask={currentTask} />
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
      />
    </div>
  </main>
);

export default AgentWorkspaceMain;
