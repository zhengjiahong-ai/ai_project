import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph from 'react-force-graph-2d';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertCircle, BarChart3, CheckCircle2, FileText, LayoutDashboard, Loader2 } from 'lucide-react';
import MarkdownContent from './MarkdownContent';
import {
  buildMetricCards,
  buildSummary,
  getDetailSections,
  getEvidencePreview,
  getStructuredSections,
} from './criticalAnalysisData.js';

const fallbackNetworkData = {
  nodes: [
    { id: 'current', name: '当前论文', val: 15, color: '#4D0099' },
    { id: 'ref1', name: '核心理论源', val: 8, color: '#94a3b8' },
    { id: 'ref2', name: '实验对比组', val: 8, color: '#94a3b8' },
    { id: 'cite1', name: '后续应用研究', val: 5, color: '#7c3aed' },
    { id: 'cite2', name: '算法优化扩展', val: 5, color: '#7c3aed' },
  ],
  links: [
    { source: 'current', target: 'ref1' },
    { source: 'current', target: 'ref2' },
    { source: 'cite1', target: 'current' },
    { source: 'cite2', target: 'current' },
  ],
};

const CriticalAnalysisPanel = ({ data, onAnalyze, isLoading }) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(320);

  useEffect(() => {
    if (containerRef.current) {
      setContainerWidth(Math.max(260, containerRef.current.offsetWidth - 40));
    }
  }, [data, isLoading]);

  const networkData = useMemo(() => fallbackNetworkData, []);
  const metrics = useMemo(() => buildMetricCards(data), [data]);
  const summary = useMemo(() => buildSummary(data), [data]);
  const detailSections = useMemo(() => getDetailSections(data), [data]);
  const structuredSections = useMemo(() => getStructuredSections(data), [data]);
  const evidencePreview = useMemo(() => getEvidencePreview(data), [data]);

  if (!data && !isLoading) {
    return (
      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <LayoutDashboard className="text-pixiu" size={40} />
        </div>
        <h3 className="theme-text-primary text-xl font-bold">开启深度批判性阅读</h3>
        <p className="theme-text-secondary mb-8 mt-2 max-w-xs text-sm">
          AI 将从创新性、论证链条与实验可信度等维度，对整篇论文进行深度分析。
        </p>
        <button
          onClick={onAnalyze}
          className="flex items-center gap-2 rounded-xl bg-pixiu px-8 py-3 font-semibold text-white shadow-lg transition-all hover:bg-pixiu-dark hover:shadow-pixiu/20 active:scale-95"
        >
          <BarChart3 size={20} />
          立即开始分析
        </button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="theme-panel flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="relative mb-6">
          <Loader2 className="animate-spin text-pixiu" size={48} />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-2 w-2 animate-ping rounded-full bg-pixiu" />
          </div>
        </div>
        <p className="theme-text-primary text-lg font-medium">正在构建批判性分析...</p>
        <p className="theme-text-secondary mt-2 text-xs">AI 正在读取全文并生成真实分析结果</p>
      </div>
    );
  }

  return (
    <div className="theme-panel-muted flex h-full flex-col">
      <div className="theme-panel theme-border sticky top-0 z-10 flex items-center justify-between border-b px-6 py-4">
        <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
          <FileText className="text-pixiu" size={20} />
          批判性阅读报告
        </h2>
        <button
          onClick={onAnalyze}
          className="theme-button-secondary rounded-lg px-3 py-1.5 text-sm font-medium transition"
        >
          重新分析
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div ref={containerRef} className="theme-card overflow-hidden rounded-2xl p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="theme-text-muted flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
              <LayoutDashboard size={14} className="text-pixiu" />
              论文领域学术地位
            </h3>
            <span className="theme-text-muted text-[10px] italic">滚轮缩放 / 拖拽节点</span>
          </div>

          <div className="theme-card-soft relative h-64 w-full rounded-xl">
            <ForceGraph
              graphData={networkData}
              height={250}
              width={containerWidth}
              nodeLabel="name"
              nodeRelSize={6}
              linkColor={() => '#64748b'}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              cooldownTicks={100}
            />
            <div className="theme-panel absolute bottom-2 left-2 flex gap-3 rounded p-1 text-[9px] theme-text-secondary">
              <span className="flex items-center gap-1">
                <i className="h-2 w-2 rounded-full bg-pixiu" /> 本文
              </span>
              <span className="flex items-center gap-1">
                <i className="h-2 w-2 rounded-full bg-slate-400" /> 参考文献
              </span>
              <span className="flex items-center gap-1">
                <i className="h-2 w-2 rounded-full bg-indigo-500" /> 引用本文
              </span>
            </div>
          </div>
        </div>

        <div className="theme-card rounded-2xl p-5">
          <h3 className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
            <CheckCircle2 size={14} className="text-emerald-400" />
            核心结论总结
          </h3>
          <div className="theme-markdown-panel rounded-xl border-l-4 border-pixiu p-4 text-sm leading-relaxed">
            <MarkdownContent className="prose prose-sm max-w-none">{summary}</MarkdownContent>
          </div>
        </div>

        {detailSections.length > 0 && (
          <div className="grid gap-4">
            {detailSections.map((section) => (
              <div key={section.key} className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-primary mb-3 text-sm font-bold">{section.title}</h3>
                <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none">{section.content}</MarkdownContent>
              </div>
            ))}
          </div>
        )}

        {structuredSections.length > 0 && (
          <div className="grid gap-4 md:grid-cols-3">
            {structuredSections.map((section) => (
              <div key={section.key} className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-primary mb-3 text-sm font-bold">{section.title}</h3>
                <div className="space-y-2">
                  {section.items.map((item, index) => (
                    <div key={`${section.key}-${index}`} className="theme-card-soft rounded-xl p-3 text-sm leading-relaxed theme-text-secondary">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {evidencePreview.length > 0 && (
          <div className="theme-card rounded-2xl p-5">
            <h3 className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
              <FileText size={14} className="text-pixiu" />
              参考证据
            </h3>
            <div className="space-y-3">
              {evidencePreview.map((item) => (
                <div key={item.id} className="theme-card-soft rounded-xl p-3">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px] font-semibold">
                    <span className="rounded-full bg-pixiu/10 px-2 py-1 text-pixiu">{item.sourceLabel}</span>
                    <span className="theme-text-muted">{item.sourceId}</span>
                    {item.chunkIndex !== null && (
                      <span className="theme-text-muted">chunk #{item.chunkIndex + 1}</span>
                    )}
                  </div>
                  <p className="theme-text-secondary text-sm leading-relaxed">{item.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="theme-card rounded-2xl p-5">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="theme-text-muted text-xs font-bold uppercase tracking-wider">多维度评价</h3>
            <span className="theme-text-muted text-[10px] italic">鼠标悬停查看详情</span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics} layout="vertical" margin={{ left: -20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(148, 163, 184, 0.18)" />
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 11, fontWeight: 600, fill: '#94a3b8' }} />
                <Tooltip
                  cursor={{ fill: 'rgba(148, 163, 184, 0.08)' }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0].payload;
                    return (
                      <div className="max-w-[220px] rounded-xl bg-slate-950 p-3 text-xs text-white shadow-2xl">
                        <div className="mb-1.5 flex items-center justify-between border-b border-white/10 pb-1.5 font-bold">
                          <span>{item.name}</span>
                          <span className="text-pixiu">{item.score} 分</span>
                        </div>
                        <p className="leading-normal opacity-80">{item.detail}</p>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={20}>
                  {metrics.map((entry, index) => (
                    <Cell
                      key={`${entry.name}-${index}`}
                      fill={entry.score >= 80 ? '#4D0099' : entry.score >= 60 ? '#7c3aed' : '#94a3b8'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-4">
          <div className="flex gap-3">
            <AlertCircle className="shrink-0 text-amber-500" size={18} />
            <p className="text-[11px] leading-normal text-amber-500">
              提示：分析结果已兼容真实后端返回结构与旧展示结构，建议结合 PDF 原文和划词解释功能交叉核对。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CriticalAnalysisPanel;
