import React from 'react';
import { Wrench } from 'lucide-react';

import { getProgressWidth, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentToolTraceSection = ({ currentTask }) => (
  <>
    <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
      <span>Task Trace</span>
      <span>{(currentTask?.toolCalls || []).length} tools</span>
    </div>

    <div className="mt-3 space-y-3">
      {(currentTask?.toolCalls || []).map((tool, index) => (
        <article
          key={tool.id || `${tool.name}-${index}`}
          className={`overflow-hidden rounded-[18px] border bg-white ${tool.status === 'succeeded' ? 'border-[#d7c8ee]' : 'border-[#e6deef]'}`}
        >
          <div className="flex items-center justify-between border-b border-[#f0ebf6] bg-[#fbf9ff] px-3 py-2.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
              <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[#efe6ff] text-[#5b2ea6]">
                <Wrench size={13} />
              </span>
              {tool.name || tool.id || 'tool_call'}
            </div>
            <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${getStatusTone(tool.status)}`}>
              {getStatusLabel(tool.status)}
            </span>
          </div>
          <div className="space-y-2 px-3 py-3 text-[11px] leading-5 text-slate-600">
            <div>
              <span className="font-semibold text-slate-900">Target:</span> {tool.target || '-'}
            </div>
            <div>
              <span className="font-semibold text-slate-900">Result:</span> {tool.result || '等待结果'}
            </div>
            {tool.meta?.reason && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-2.5 py-2 text-amber-800">
                回退原因：{tool.meta.reason}
              </div>
            )}
          </div>
        </article>
      ))}
      {(currentTask?.toolCalls || []).length === 0 && (
        <div className="rounded-[18px] border border-dashed border-[#ddd2ec] bg-white px-4 py-5 text-xs leading-6 text-slate-500">
          当前还没有工具调用记录。启动任务后，这里会展示检索与汇总轨迹。
        </div>
      )}
    </div>
  </>
);

export const AgentEvidenceListSection = ({ currentTask }) => (
  <>
    <div className="mt-5 flex items-center justify-between text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
      <span>Evidence</span>
      <span>{(currentTask?.evidenceItems || []).length} items</span>
    </div>

    <div className="mt-3 space-y-3">
      {(currentTask?.evidenceItems || []).map((item) => (
        <article key={item.sourceId} className="rounded-[18px] border border-[#e8e0f1] bg-white p-3">
          <div className="text-xs font-semibold leading-5 text-slate-900">{item.pdfId || item.sourceId}</div>
          <div className="mt-1 flex flex-wrap gap-2 text-[10px] font-semibold text-[#5b2ea6]">
            {item.sectionId && <span>{item.sectionId}</span>}
            {Number.isInteger(item.pageIndex) && <span>p.{item.pageIndex + 1}</span>}
            {item.sourceType && <span>{item.sourceType}</span>}
          </div>
          <div className="mt-2 border-l-2 border-[#dbcaf5] pl-3 text-[11px] leading-6 text-slate-600">
            {item.text}
          </div>
        </article>
      ))}
      {(currentTask?.evidenceItems || []).length === 0 && (
        <div className="rounded-[18px] border border-dashed border-[#ddd2ec] bg-white px-4 py-5 text-xs leading-6 text-slate-500">
          暂无证据卡片。任务进入检索阶段后，会在这里展示可追踪片段。
        </div>
      )}
    </div>
  </>
);

export const AgentTaskSummaryCard = ({ activeProject, currentTask, activePaperId }) => (
  <div className="mt-5 rounded-[20px] border border-[#ebe3f5] bg-[#f8f5fb] p-4">
    <div className="text-xs font-semibold text-slate-900">任务摘要</div>
    <div className="mt-3 space-y-2 text-[11px] leading-6 text-slate-600">
      <div>项目 ID：{activeProject?.projectId || '-'}</div>
      <div>任务 ID：{currentTask?.taskId || '-'}</div>
      <div>Trace ID：{currentTask?.traceId || '-'}</div>
      <div>当前论文：{activePaperId || '-'}</div>
      <div>项目论文：{(activeProject?.paperIds || []).join(', ') || '无'}</div>
      <div>事件数量：{(currentTask?.events || []).length}</div>
      <div>冲突候选：{(currentTask?.conflicts || []).length}</div>
    </div>

    <div className="mt-4">
      <div className="mb-2 flex items-center justify-between text-[11px] font-semibold text-slate-700">
        <span>Progress</span>
        <span>{Math.round((currentTask?.progress || 0) * 100)}%</span>
      </div>
      <div className="h-2 rounded-full bg-white">
        <div
          className="h-2 rounded-full bg-[linear-gradient(135deg,#5b2ea6,#7d57e6)]"
          style={{ width: getProgressWidth(currentTask?.progress) }}
        />
      </div>
    </div>
  </div>
);
