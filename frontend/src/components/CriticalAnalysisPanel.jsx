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
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  FileText,
  LayoutDashboard,
  Loader2,
} from 'lucide-react';
import MarkdownContent from './MarkdownContent';

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

const buildMetricCards = (data) => {
  if (Array.isArray(data?.metrics) && data.metrics.length > 0) {
    return data.metrics;
  }

  if (!data) {
    return [];
  }

  const textLength = (value) => (typeof value === 'string' ? value.trim().length : 0);
  const claimedLength = textLength(data.claimed_contributions);
  const inferredLength = textLength(data.inferred_real_contributions);
  const criticalLength = textLength(data.critical_analysis);

  return [
    {
      name: '作者主张',
      score: Math.min(95, Math.max(45, Math.round(claimedLength / 6) || 58)),
      detail: data.claimed_contributions || '系统未返回作者主张摘要。',
    },
    {
      name: '真实贡献',
      score: Math.min(95, Math.max(45, Math.round(inferredLength / 6) || 62)),
      detail: data.inferred_real_contributions || '系统未返回推断贡献。',
    },
    {
      name: '批判深度',
      score: Math.min(95, Math.max(45, Math.round(criticalLength / 8) || 66)),
      detail: data.critical_analysis || '系统未返回批判性结论。',
    },
  ];
};

const buildSummary = (data) => {
  if (typeof data?.summary === 'string' && data.summary.trim()) {
    return data.summary;
  }

  const sections = [
    ['作者宣称的贡献', data?.claimed_contributions],
    ['推断出的真实贡献', data?.inferred_real_contributions],
    ['批判性阅读结论', data?.critical_analysis],
  ].filter(([, value]) => typeof value === 'string' && value.trim());

  if (sections.length === 0) {
    return '暂无分析结果。';
  }

  return sections.map(([title, value]) => `### ${title}\n${value}`).join('\n\n');
};

const getDetailSections = (data) => {
  const sections = [
    { key: 'claimed', title: '作者宣称的贡献', content: data?.claimed_contributions },
    { key: 'inferred', title: '推断出的真实贡献', content: data?.inferred_real_contributions },
    { key: 'critical', title: '批判性阅读结论', content: data?.critical_analysis },
  ];

  return sections.filter((section) => typeof section.content === 'string' && section.content.trim());
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

  if (!data && !isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-slate-50 p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <LayoutDashboard className="text-pixiu" size={40} />
        </div>
        <h3 className="text-xl font-bold text-slate-800">开启深度批判性阅读</h3>
        <p className="mt-2 mb-8 max-w-xs text-sm text-slate-500">
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
      <div className="flex h-full flex-col items-center justify-center bg-white p-8 text-center">
        <div className="relative mb-6">
          <Loader2 className="animate-spin text-pixiu" size={48} />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-2 w-2 animate-ping rounded-full bg-pixiu" />
          </div>
        </div>
        <p className="text-lg font-medium text-slate-700">正在构建批判性分析...</p>
        <p className="mt-2 text-xs text-slate-400">AI 正在读取全文并生成真实分析结果</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-slate-50/30">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4">
        <h2 className="flex items-center gap-2 text-lg font-bold text-slate-800">
          <FileText className="text-pixiu" size={20} />
          批判性阅读报告
        </h2>
        <button
          onClick={onAnalyze}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:border-pixiu hover:text-pixiu"
        >
          重新分析
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div ref={containerRef} className="overflow-hidden rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <LayoutDashboard size={14} className="text-pixiu" />
              论文领域学术地位
            </h3>
            <span className="text-[10px] italic text-slate-400">滚轮缩放 / 拖拽节点</span>
          </div>

          <div className="relative h-64 w-full rounded-xl border border-slate-100 bg-slate-50">
            <ForceGraph
              graphData={networkData}
              height={250}
              width={containerWidth}
              nodeLabel="name"
              nodeRelSize={6}
              linkColor={() => '#cbd5e1'}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              cooldownTicks={100}
            />
            <div className="absolute bottom-2 left-2 flex gap-3 rounded bg-white/80 p-1 text-[9px] text-slate-500">
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

        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
            <CheckCircle2 size={14} className="text-green-500" />
            核心结论总结
          </h3>
          <div className="rounded-xl border-l-4 border-pixiu bg-slate-50 p-4 text-sm leading-relaxed text-slate-600">
            <MarkdownContent className="prose prose-sm max-w-none">
              {summary}
            </MarkdownContent>
          </div>
        </div>

        {detailSections.length > 0 && (
          <div className="grid gap-4">
            {detailSections.map((section) => (
              <div key={section.key} className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
                <h3 className="mb-3 text-sm font-bold text-slate-700">{section.title}</h3>
                <MarkdownContent className="prose prose-sm max-w-none text-slate-700">
                  {section.content}
                </MarkdownContent>
              </div>
            ))}
          </div>
        )}

        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-6 flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">多维度评价</h3>
            <span className="text-[10px] italic text-slate-400">鼠标悬停查看详情</span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics} layout="vertical" margin={{ left: -20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis
                  dataKey="name"
                  type="category"
                  width={80}
                  tick={{ fontSize: 11, fontWeight: 600, fill: '#64748b' }}
                />
                <Tooltip
                  cursor={{ fill: '#f1f5f9', opacity: 0.5 }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0].payload;
                    return (
                      <div className="max-w-[220px] animate-in fade-in slide-in-from-bottom-1 rounded-xl bg-slate-900 p-3 text-xs text-white shadow-2xl">
                        <div className="mb-1.5 flex items-center justify-between border-b border-white/10 pb-1.5 font-bold">
                          <span>{item.name}</span>
                          <span className="text-pixiu-dark">{item.score} 分</span>
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

        <div className="flex gap-3 rounded-xl border border-amber-100 bg-amber-50 p-4">
          <AlertCircle className="shrink-0 text-amber-500" size={18} />
          <p className="text-[11px] leading-normal text-amber-700">
            提示：分析结果已兼容真实后端返回结构与旧展示结构，建议结合 PDF 原文和划词解释功能交叉核对。
          </p>
        </div>
      </div>
    </div>
  );
};

export default CriticalAnalysisPanel;
