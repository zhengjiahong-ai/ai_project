import React from 'react';
import { Archive, Wrench } from 'lucide-react';

import { buildAgentEvidenceArtifact } from '../artifactModel.ts';
import SourceList from '../SourceCitation.jsx';
import { getAgentArtifactSaveState } from './agentWorkspaceModel.ts';
import { getProgressWidth, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentToolTraceSection = ({ currentTask }) => (
  <>
    <div className="agent-section-label flex items-center justify-between text-[11px]">
      <span>Task Trace</span>
      <span>{(currentTask?.toolCalls || []).length} tools</span>
    </div>

    <div className="mt-3 space-y-3">
      {(currentTask?.toolCalls || []).map((tool, index) => (
        <article
          key={tool.id || `${tool.name}-${index}`}
          className="agent-card overflow-hidden rounded-[18px]"
        >
          <div className="agent-header flex items-center justify-between border-b px-3 py-2.5">
            <div className="agent-title flex items-center gap-2 text-xs font-semibold">
              <span className="agent-icon-accent inline-flex h-6 w-6 items-center justify-center rounded-lg">
                <Wrench size={13} />
              </span>
              {tool.name || tool.id || 'tool_call'}
            </div>
            <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${getStatusTone(tool.status)}`}>
              {getStatusLabel(tool.status)}
            </span>
          </div>
          <div className="agent-body space-y-2 px-3 py-3 text-[11px] leading-5">
            <div>
              <span className="agent-title font-semibold">Target:</span> {tool.target || '-'}
            </div>
            <div>
              <span className="agent-title font-semibold">Result:</span> {tool.result || '等待结果'}
            </div>
            {tool.meta?.reason && (
              <div className="agent-chip-warning rounded-xl px-2.5 py-2">
                回退原因：{tool.meta.reason}
              </div>
            )}
          </div>
        </article>
      ))}
      {(currentTask?.toolCalls || []).length === 0 && (
        <div className="agent-empty-state rounded-[18px] border-dashed px-4 py-5 text-xs leading-6">
          当前还没有工具调用记录。启动任务后，这里会展示检索与汇总轨迹。
        </div>
      )}
    </div>
  </>
);

export const AgentEvidenceListSection = ({ activeProject, currentTask, activePaperId, onCaptureArtifact, onJumpToSource }) => (
  <>
    <div className="agent-section-label mt-5 flex items-center justify-between text-[11px]">
      <span>Evidence</span>
      <span>{(currentTask?.evidenceItems || []).length} items</span>
    </div>

    <div className="mt-3 space-y-3">
      {(currentTask?.evidenceItems || []).map((item) => {
        // 17-3: chart_analysis / image_analysis get special rendering.
        if (item.sourceType === 'chart_analysis' && item.metadata?.chartData) {
          const ChartAnalysisCard = React.lazy(() => import('./ChartAnalysisCard.jsx'));
          return (
            <React.Suspense key={item.sourceId} fallback={<div className="agent-card rounded-[18px] p-3 text-xs">加载图表...</div>}>
              <ChartAnalysisCard evidence={item} />
            </React.Suspense>
          );
        }
        if (item.sourceType === 'image_analysis') {
          return (
            <article key={item.sourceId} className="agent-card rounded-[18px] p-3 border-l-[3px]" style={{ borderLeftColor: 'var(--info, #0ea5e9)' }}>
              <div className="agent-title text-xs font-semibold leading-5">图片分析</div>
              <div className="mt-1 text-xs text-[color:var(--text-secondary)]">{item.text}</div>
              {item.metadata?.imageUrl && (
                <div className="mt-2 text-[10px] text-[color:var(--text-muted)]">来源: {item.metadata.imageUrl}</div>
              )}
              <div className="agent-evidence-meta mt-1 flex flex-wrap gap-2 text-[10px] font-semibold">
                <span className="text-[color:var(--info)]">image_analysis</span>
              </div>
            </article>
          );
        }
        return (
        <article key={item.sourceId} className="agent-card rounded-[18px] p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="agent-title text-xs font-semibold leading-5">{item.pdfId || item.sourceId}</div>
            {(() => {
              const saveState = getAgentArtifactSaveState({ activePdfId: activePaperId, content: item.text });
              return (
                <button
                  type="button"
                  disabled={!saveState.canSave || !onCaptureArtifact}
                  title={saveState.reason || '保存这条关键证据'}
                  onClick={() => {
                    const artifact = buildAgentEvidenceArtifact({
                      activePdfId: activePaperId,
                      projectId: activeProject?.projectId || currentTask?.projectId,
                      taskId: currentTask?.taskId,
                      evidence: item,
                    });
                    if (artifact) onCaptureArtifact?.(artifact);
                  }}
                  className="agent-secondary-button inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Archive size={11} />
                  加入工作台
                </button>
              );
            })()}
          </div>
          <div className="agent-evidence-meta mt-1 flex flex-wrap gap-2 text-[10px] font-semibold">
            {item.sectionId && <span>{item.sectionId}</span>}
            {Number.isInteger(item.pageIndex) && <span>p.{item.pageIndex + 1}</span>}
            {item.sourceType && (
              <span className={(item.sourceType === 'web_page' || item.sourceType === 'web_search') ? 'text-[color:var(--accent)]' : ''}>
                {item.sourceType}
              </span>
            )}
          </div>
          <div className="mt-2">
            <SourceList sources={[item]} onJumpToSource={onJumpToSource} variant="agent" />
          </div>
        </article>
        );
      })}
      {(currentTask?.evidenceItems || []).length === 0 && (
        <div className="agent-empty-state rounded-[18px] border-dashed px-4 py-5 text-xs leading-6">
          暂无证据卡片。任务进入检索阶段后，会在这里展示可追踪片段。
        </div>
      )}
    </div>
  </>
);

export const AgentTaskSummaryCard = ({ activeProject, currentTask, activePaperId }) => (
  <div className="agent-card-soft mt-5 rounded-[20px] p-4">
    <div className="agent-title text-xs font-semibold">任务摘要</div>
    <div className="agent-body mt-3 space-y-2 text-[11px] leading-6">
      <div>项目 ID：{activeProject?.projectId || '-'}</div>
      <div>任务 ID：{currentTask?.taskId || '-'}</div>
      <div>Trace ID：{currentTask?.traceId || '-'}</div>
      <div>当前论文：{activePaperId || '-'}</div>
      <div>项目论文：{(activeProject?.paperIds || []).join(', ') || '无'}</div>
      <div>事件数量：{(currentTask?.events || []).length}</div>
      <div>冲突候选：{(currentTask?.conflicts || []).length}</div>
    </div>

    <div className="mt-4">
      <div className="agent-title mb-2 flex items-center justify-between text-[11px] font-semibold">
        <span>Progress</span>
        <span>{Math.round((currentTask?.progress || 0) * 100)}%</span>
      </div>
      <div className="agent-progress-track h-2 rounded-full">
        <div
          className="agent-progress-bar h-2 rounded-full"
          style={{ width: getProgressWidth(currentTask?.progress) }}
        />
      </div>
    </div>
  </div>
);
