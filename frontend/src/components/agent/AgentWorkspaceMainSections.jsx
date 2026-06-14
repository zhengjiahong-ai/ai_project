import React from 'react';
import { AlertTriangle, BookOpen, FileText, GitCompare, Sparkles, Workflow } from 'lucide-react';

import { formatAgentTime, getStatusLabel, getStatusTone } from './agentWorkspaceUi.js';

export const AgentTaskPromptBubble = ({ task, prompt }) => (
  <div className="flex justify-end">
    <div className="max-w-[82%] rounded-[22px] border border-[#dcc8f6] bg-[#f5eeff] shadow-[0_8px_22px_rgba(96,52,170,0.08)]">
      <div className="flex items-center justify-between gap-4 border-b border-[#e8dffd] px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-[#5b2ea6]">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-[#d7c2fb] bg-white text-[11px] font-bold">
            你
          </span>
          研究请求
        </div>
        <span className="text-[11px] text-[#8f7ab7]">{formatAgentTime(task?.createdAt || task?.updatedAt) || '实时输入'}</span>
      </div>
      <div className="whitespace-pre-wrap px-4 py-3 text-sm leading-7 text-slate-700">
        {task?.prompt || prompt || '输入一个多论文研究任务，例如比较方法、证据和局限性。'}
      </div>
    </div>
  </div>
);

export const AgentTaskHistoryCard = ({ task, isActive, onSelect }) => (
  <button
    type="button"
    onClick={() => onSelect?.(task)}
    className={`w-full rounded-[22px] border p-4 text-left transition ${
      isActive
        ? 'border-[#d4c0f0] bg-white shadow-[0_12px_28px_rgba(96,52,170,0.08)]'
        : 'border-[#ece6f5] bg-white/78 hover:border-[#d4c0f0] hover:bg-white'
    }`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="line-clamp-2 text-sm font-semibold leading-6 text-slate-900">
          {task.prompt || '未命名研究任务'}
        </div>
        <div className="mt-1 text-[11px] text-slate-400">
          {formatAgentTime(task.updatedAt || task.createdAt)} · {task.stage || 'planning'}
        </div>
      </div>
      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${getStatusTone(task.status)}`}>
        {getStatusLabel(task.status)}
      </span>
    </div>
    <div className="mt-3 grid gap-2 text-[11px] text-slate-500 sm:grid-cols-3">
      <div className="rounded-xl bg-[#fbf9ff] px-3 py-2">{(task.events || []).length} 个事件</div>
      <div className="rounded-xl bg-[#fbf9ff] px-3 py-2">{(task.evidenceItems || []).length} 条证据</div>
      <div className="rounded-xl bg-[#fbf9ff] px-3 py-2">{(task.conflicts || []).length} 个冲突</div>
    </div>
  </button>
);

export const AgentTaskHistorySection = ({ tasks, currentTask, onSelectTask }) => {
  if (!tasks.length) {
    return (
      <div className="rounded-[24px] border border-dashed border-[#ddd2ec] bg-white/75 px-5 py-8 text-center">
        <div className="text-sm font-semibold text-slate-900">还没有研究记录</div>
        <p className="mx-auto mt-2 max-w-xl text-xs leading-6 text-slate-500">
          创建项目后，在底部输入框发起第一个任务。之后每次提问都会作为独立研究记录保留在当前项目下。
        </p>
      </div>
    );
  }

  return (
    <section className="rounded-[24px] border border-[#e6dff1] bg-[#fbf9ff]/85 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-900">项目对话记录</div>
          <div className="mt-1 text-[11px] text-slate-500">每次研究请求都会保留，可点击切换查看过程和结果。</div>
        </div>
        <span className="rounded-full border border-[#dcc8f6] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#6b36d9]">
          {tasks.length} tasks
        </span>
      </div>
      <div className="grid gap-3">
        {tasks.map((task) => (
          <AgentTaskHistoryCard
            key={task.taskId}
            task={task}
            isActive={task.taskId === currentTask?.taskId}
            onSelect={onSelectTask}
          />
        ))}
      </div>
    </section>
  );
};

export const AgentTimelineSection = ({ currentTask }) => {
  const events = currentTask?.events || [];

  return (
    <details className="mt-4 overflow-hidden rounded-[18px] border border-[#ece6f5] bg-[#fcfaff]" open>
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-slate-900">
        <span className="flex items-center gap-2">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[#efe6ff] text-[#5b2ea6]">
            <Workflow size={14} />
          </span>
          研究过程时间线
        </span>
        <span className="rounded-full border border-[#dcc8f6] bg-[#f5eeff] px-2.5 py-1 text-[11px] font-semibold text-[#6b36d9]">
          {events.length} events
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {events.map((event, index) => (
          <div key={event.eventId || `${event.type}-${index}`} className="grid grid-cols-[16px_minmax(0,1fr)] gap-3">
            <div className="pt-1">
              <span className="block h-3 w-3 rounded-full bg-[linear-gradient(135deg,#5b2ea6,#7d57e6)] shadow-[0_0_0_4px_rgba(107,54,217,0.12)]" />
            </div>
            <div className="rounded-2xl border border-[#ebe3f5] bg-white px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-slate-900">{event.summary || event.type}</span>
                <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7b61a6]">
                  {event.stage || currentTask?.stage || 'stage'}
                </span>
              </div>
              <div className="mt-1 text-[10px] text-slate-400">{event.type}</div>
            </div>
          </div>
        ))}
        {events.length === 0 && (
          <div className="rounded-2xl border border-dashed border-[#ddd2ec] bg-white px-4 py-4 text-xs leading-6 text-slate-500">
            启动任务后，这里会随着轮询逐步出现规划、检索、判断和报告更新事件。
          </div>
        )}
      </div>
    </details>
  );
};

export const AgentTaskPlanSection = ({ currentTask }) => (
  <details className="mt-4 overflow-hidden rounded-[18px] border border-[#ece6f5] bg-[#fcfaff]" open>
    <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-slate-900">
      <span className="flex items-center gap-2">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[#efe6ff] text-[#5b2ea6]">
          <Sparkles size={14} />
        </span>
        执行计划
      </span>
      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
        {(currentTask?.planItems || []).length} steps
      </span>
    </summary>
    <div className="space-y-2 px-4 pb-4">
      {(currentTask?.planItems || []).map((item, index) => (
        <div
          key={item.id || item.label || index}
          className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-start gap-3 rounded-2xl border border-[#ebe3f5] bg-white px-3 py-3"
        >
          <div className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[#d8c9ef] bg-[#f5eeff] text-xs font-bold text-[#5b2ea6]">
            {index + 1}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold text-slate-900">{item.label || item.question || item.id}</div>
            <div className="mt-1 text-[11px] leading-5 text-slate-500">{item.detail || '等待执行'}</div>
          </div>
          <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${getStatusTone(item.status)}`}>
            {item.status || 'pending'}
          </span>
        </div>
      ))}
      {(currentTask?.planItems || []).length === 0 && (
        <div className="rounded-2xl border border-dashed border-[#ddd2ec] bg-white px-4 py-4 text-xs leading-6 text-slate-500">
          任务开始后，这里会展示 Agent 的结构化计划和当前阶段。
        </div>
      )}
    </div>
  </details>
);

export const AgentIntermediateArtifactsSection = ({ activeProject, currentTask }) => (
  <details className="mt-4 overflow-hidden rounded-[18px] border border-[#ece6f5] bg-[#fcfaff]" open>
    <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-slate-900">
      <span className="flex items-center gap-2">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[#efe6ff] text-[#5b2ea6]">
          <BookOpen size={14} />
        </span>
        中间产物
      </span>
      <span className="rounded-full border border-[#dcc8f6] bg-[#f5eeff] px-2.5 py-1 text-[11px] font-semibold text-[#6b36d9]">
        live snapshot
      </span>
    </summary>
    <div className="grid gap-3 px-4 pb-4 md:grid-cols-3">
      <div className="rounded-2xl border border-[#ebe3f5] bg-white p-3">
        <div className="text-xs font-semibold text-slate-900">研究目标</div>
        <div className="mt-2 text-[11px] leading-5 text-slate-500">{activeProject?.goal || '等待项目目标'}</div>
      </div>
      <div className="rounded-2xl border border-[#ebe3f5] bg-white p-3">
        <div className="text-xs font-semibold text-slate-900">证据覆盖</div>
        <div className="mt-2 text-[11px] leading-5 text-slate-500">
          已收集 {(currentTask?.evidenceItems || []).length} 条证据，覆盖 {(activeProject?.paperIds || []).length} 篇项目论文。
        </div>
      </div>
      <div className="rounded-2xl border border-[#ebe3f5] bg-white p-3">
        <div className="text-xs font-semibold text-slate-900">冲突候选</div>
        <div className="mt-2 text-[11px] leading-5 text-slate-500">
          当前发现 {(currentTask?.conflicts || []).length} 个冲突或置信度风险候选。
        </div>
      </div>
    </div>
  </details>
);

export const AgentComparisonSection = ({ currentTask }) => {
  const columns = currentTask?.comparisonTable?.columns || [];
  const rows = currentTask?.comparisonTable?.rows || [];

  return (
    <details className="mt-4 overflow-hidden rounded-[18px] border border-[#ece6f5] bg-[#fcfaff]" open>
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-slate-900">
        <span className="flex items-center gap-2">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[#efe6ff] text-[#5b2ea6]">
            <GitCompare size={14} />
          </span>
          跨论文判断
        </span>
        <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-semibold text-sky-700">
          {rows.length} rows
        </span>
      </summary>
      <div className="px-4 pb-4">
        {rows.length > 0 ? (
          <div className="overflow-x-auto rounded-2xl border border-[#ebe3f5] bg-white">
            <table className="w-full min-w-[720px] text-left text-[11px]">
              <thead className="bg-[#fbf9ff] text-slate-500">
                <tr>
                  {columns.map((column) => (
                    <th key={column} className="px-3 py-2 font-bold">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="text-slate-600">
                {rows.map((row, rowIndex) => (
                  <tr key={`${row?.[0] || 'row'}-${rowIndex}`} className="border-t border-[#eee7f5]">
                    {(Array.isArray(row) ? row : []).map((cell, cellIndex) => (
                      <td key={`${rowIndex}-${cellIndex}`} className="max-w-[320px] px-3 py-2 leading-5">
                        {cell || '-'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[#ddd2ec] bg-white px-4 py-4 text-xs leading-6 text-slate-500">
            完成证据检索后，这里会展示按论文聚合的判断表。
          </div>
        )}
      </div>
    </details>
  );
};

export const AgentConflictSection = ({ currentTask }) => {
  const conflicts = currentTask?.conflicts || [];

  return (
    <details className="mt-4 overflow-hidden rounded-[18px] border border-[#ece6f5] bg-[#fcfaff]" open>
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-slate-900">
        <span className="flex items-center gap-2">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
            <AlertTriangle size={14} />
          </span>
          冲突检测
        </span>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
          {conflicts.length} candidates
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {conflicts.map((conflict) => (
          <article key={conflict.id || conflict.claim} className="rounded-2xl border border-amber-200 bg-white px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-900">{conflict.claim || '冲突候选'}</div>
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-700">
                {conflict.severity || 'unknown'}
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-6 text-slate-600">{conflict.summary}</p>
            <div className="mt-2 text-[10px] font-semibold text-[#5b2ea6]">
              {(conflict.papers || []).filter(Boolean).join(' / ') || '未指定论文'}
            </div>
            {conflict.resolutionHint && (
              <div className="mt-2 rounded-xl border border-[#eee7f5] bg-[#fbf9ff] px-2.5 py-2 text-[11px] leading-5 text-slate-500">
                建议：{conflict.resolutionHint}
              </div>
            )}
          </article>
        ))}
        {conflicts.length === 0 && (
          <div className="rounded-2xl border border-dashed border-[#ddd2ec] bg-white px-4 py-4 text-xs leading-6 text-slate-500">
            综合阶段会生成冲突候选，包括证据覆盖不均、检索回退和潜在结论风险。
          </div>
        )}
      </div>
    </details>
  );
};

export const AgentDraftReportSection = ({ currentTask }) => {
  const draftReport = `${currentTask?.draftReport || ''}`.trim();
  const draftSections = draftReport
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);

  return (
    <details className="mt-4 overflow-hidden rounded-[18px] border border-[#ece6f5] bg-[#fcfaff]" open>
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-slate-900">
        <span className="flex items-center gap-2">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[#efe6ff] text-[#5b2ea6]">
            <FileText size={14} />
          </span>
          最终结果草稿
        </span>
        <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-semibold text-sky-700">
          {draftSections.length || 0} paragraphs
        </span>
      </summary>
      <div className="space-y-2 px-4 pb-4">
        {draftSections.length > 0 ? (
          draftSections.map((line, index) => (
            <div key={`${line}-${index}`} className="whitespace-pre-wrap rounded-2xl border border-[#ebe3f5] bg-white px-3 py-2.5 text-xs leading-6 text-slate-700">
              {line}
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-[#ddd2ec] bg-white px-4 py-4 text-xs leading-6 text-slate-500">
            这里会显示当前 Agent 任务输出的完整结构化草稿，不再截断前几段。
          </div>
        )}
      </div>
    </details>
  );
};
