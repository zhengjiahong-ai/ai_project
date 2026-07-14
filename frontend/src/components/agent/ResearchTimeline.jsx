import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle, Download, GitBranch, Search, Sparkles, XCircle } from 'lucide-react';

const STEP_ICONS = {
  search: Search,
  fetch: Download,
  judge: Sparkles,
  refine: GitBranch,
  conclusion: CheckCircle,
  retrieve: Download,
};

const STATUS_TONE = {
  success: 'text-emerald-400',
  error: 'text-red-400',
  running: 'text-blue-400',
  pending: 'text-gray-400',
};

const STATUS_DOT = {
  success: 'bg-emerald-400',
  error: 'bg-red-400',
  running: 'bg-blue-400 animate-pulse',
  pending: 'bg-gray-400',
};

const STEP_LABELS = {
  search: '搜索',
  fetch: '抓取',
  judge: '评估',
  refine: '精炼',
  conclusion: '结论',
  retrieve: '检索',
};

const ResearchTimeline = ({ steps = [], isRunning = false }) => {
  const [expanded, setExpanded] = useState({});
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current && isRunning) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps.length, isRunning]);

  if (!steps || steps.length === 0) {
    return (
      <div className="agent-empty-state rounded-2xl border-dashed px-4 py-4 text-xs leading-6">
        启动任务后，这里会逐步展示搜索 query → 结果概要 → 抓取页面 → judge 反思 → 精炼 query → 结论。
      </div>
    );
  }

  const toggleExpand = (stepId) => {
    setExpanded((prev) => ({ ...prev, [stepId]: !prev[stepId] }));
  };

  return (
    <div ref={scrollRef} className="max-h-80 overflow-y-auto space-y-1.5">
      {steps.map((step, index) => {
        const Icon = STEP_ICONS[step.type] || Search;
        const isExpanded = !!expanded[step.stepId || index];
        const label = STEP_LABELS[step.type] || step.type;
        const status = step.status || 'pending';
        const hasDetail = !!(step.detail && step.detail.trim());

        return (
          <div key={step.stepId || index} className="grid grid-cols-[16px_minmax(0,1fr)] gap-3">
            {/* Timeline connector + dot */}
            <div className="flex flex-col items-center pt-0.5">
              <span className={`block h-2.5 w-2.5 rounded-full ${STATUS_DOT[status] || 'bg-gray-400'}`} />
              {index < steps.length - 1 && (
                <span className="mt-0.5 h-full min-h-[1rem] w-px bg-[color:var(--border)]" />
              )}
            </div>

            {/* Step card */}
            <div
              className={`agent-card rounded-xl px-3 py-2.5 ${hasDetail ? 'cursor-pointer hover:brightness-95' : ''}`}
              onClick={() => hasDetail && toggleExpand(step.stepId || index)}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Icon size={13} className={`shrink-0 ${STATUS_TONE[status] || 'text-gray-400'}`} />
                  <span className="agent-title text-xs font-semibold truncate">
                    {step.summary || `${label}`}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {step.durationMs > 0 && (
                    <span className="text-[10px] text-[color:var(--muted)]">
                      {(step.durationMs / 1000).toFixed(1)}s
                    </span>
                  )}
                  <span className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${STATUS_TONE[status] || 'text-gray-400'}`}>
                    {label}
                  </span>
                </div>
              </div>

              {/* Expandable detail */}
              {isExpanded && hasDetail && (
                <div className="mt-2 border-t border-[color:var(--border)] pt-2">
                  <pre className="agent-card-soft max-h-48 overflow-auto rounded-lg p-2.5 text-[11px] leading-5 font-mono whitespace-pre-wrap text-[color:var(--muted)]">
                    {step.detail}
                  </pre>
                </div>
              )}

              {hasDetail && !isExpanded && (
                <div className="agent-muted mt-1 text-[10px]">点击展开详情</div>
              )}
            </div>
          </div>
        );
      })}

      {isRunning && (
        <div className="grid grid-cols-[16px_minmax(0,1fr)] gap-3">
          <span className="mt-0.5 block h-2.5 w-2.5 rounded-full bg-blue-400 animate-pulse" />
          <div className="agent-muted py-1 text-[11px]">研究中...</div>
        </div>
      )}
    </div>
  );
};

export default ResearchTimeline;
