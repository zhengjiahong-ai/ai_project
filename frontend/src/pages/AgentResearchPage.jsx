import React, { lazy, Suspense } from 'react';
import { ErrorBoundary } from '../components/ErrorBoundary';

const AgentWorkspace = lazy(() => import('../components/agent/AgentWorkspace'));

export default function AgentResearchPage({
  papersList,
  pdfId,
  handleCaptureWorkbenchArtifact,
  handleJumpToSource,
}) {
  return (
    <ErrorBoundary area="Agent工作区">
      <Suspense fallback={<div className="flex items-center justify-center h-full theme-text-muted">加载 Agent 工作区…</div>}>
        <AgentWorkspace
          paperLibrary={papersList}
          activePaperId={pdfId || ''}
          onCaptureArtifact={handleCaptureWorkbenchArtifact}
          onJumpToSource={handleJumpToSource}
        />
      </Suspense>
    </ErrorBoundary>
  );
}
