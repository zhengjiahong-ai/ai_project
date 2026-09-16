import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph from 'react-force-graph-2d';
import { cachedThemeColor } from '../utils/themeColor';
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  FileText,
  LayoutDashboard,
  Link2,
  Loader2,
} from 'lucide-react';
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

import SourceList from './SourceCitation.jsx';

import InsightCard from './InsightCard';
import {
  buildEvidenceGraphLegend,
  buildMetricCards,
  buildSummary,
  getClaimSupportRows,
  getDetailSections,
  getEvidenceGraph,
  getEvidencePreview,
  getNoveltyDimensionRows,
  getSentenceSourceReferences,
  getStructuredSections,
} from './criticalAnalysisData.ts';

const readingSteps = [
  { id: 'summary', label: '判断' },
  { id: 'claims', label: '再看主张' },
  { id: 'evidence', label: '最后看证据' },
];

const CriticalAnalysisPanel = ({ data, onAnalyze, isLoading, onCaptureArtifact, onJumpToSource }) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(320);
  const [activeStep, setActiveStep] = useState('summary');

  useEffect(() => {
    if (containerRef.current) {
      setContainerWidth(Math.max(260, containerRef.current.offsetWidth - 40));
    }
  }, [data, isLoading]);

  const networkData = useMemo(() => getEvidenceGraph(data), [data]);
  const graphLegend = useMemo(() => buildEvidenceGraphLegend(networkData), [networkData]);
  const metrics = useMemo(() => buildMetricCards(data), [data]);
  const summary = useMemo(() => buildSummary(data), [data]);
  const detailSections = useMemo(() => getDetailSections(data), [data]);
  const structuredSections = useMemo(() => getStructuredSections(data), [data]);
  const claimSupportRows = useMemo(() => getClaimSupportRows(data), [data]);
  const noveltyDimensions = useMemo(() => getNoveltyDimensionRows(data), [data]);
  const evidencePreview = useMemo(() => getEvidencePreview(data), [data]);
  const sentenceReferences = useMemo(() => getSentenceSourceReferences(data), [data]);

  const overviewPoints = useMemo(
    () => [
      metrics.length > 0 ? `已生成 ${metrics.length} 个批判维度评分` : '等待多维评分生成',
      structuredSections.length > 0 ? `已识别 ${structuredSections.length} 类风险与证据缺口` : '尚未提取结构化风险点',
      claimSupportRows.length > 0 ? `已验证 ${claimSupportRows.length} 条作者主张` : '尚未形成主张-证据校验',
    ],
    [claimSupportRows.length, metrics.length, structuredSections.length],
  );

  if (!data && !isLoading) {
    return (
      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <LayoutDashboard className="text-pixiu" size={40} />
        </div>
        <h3 className="theme-text-primary text-xl font-bold">开启批判性阅读</h3>
        <button
          type="button"
          onClick={onAnalyze}
          className="flex items-center gap-2 rounded-xl bg-pixiu px-8 py-3 font-semibold text-white shadow-lg transition-all hover:bg-pixiu-dark hover:shadow-pixiu/20 active:scale-95"
        >
          <BarChart3 size={20} />
          开始分析
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
        <p className="theme-text-primary text-lg font-medium">正在检查主张与证据链</p>
      </div>
    );
  }

  return (
    <div className="theme-panel-muted flex h-full flex-col">
      <div className="theme-panel theme-border sticky top-0 z-10 border-b px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
              <FileText className="text-pixiu" size={20} />
              批判阅读
            </h2>
          </div>
          <button
            type="button"
            onClick={onAnalyze}
            className="theme-button-secondary rounded-lg px-3 py-1.5 text-sm font-medium transition"
          >
            重新分析
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {readingSteps.map((step) => (
            <button
              key={step.id}
              type="button"
              onClick={() => setActiveStep(step.id)}
              className={`workspace-section-tab ${activeStep === step.id ? 'workspace-section-tab-active' : ''}`}
            >
              {step.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        <InsightCard
          title="批判总览"
          icon={<CheckCircle2 size={14} className="text-pixiu" />}
          summary={summary}
          keyPoints={overviewPoints}
          detailsTitle="展开完整总览"
          content={summary}
          footer={
            <div className="flex flex-wrap gap-2">
              <span className="source-link-chip inline-flex items-center gap-1">
                <ArrowRight size={12} />
                先决定要不要深挖
              </span>
              <span className="source-link-chip inline-flex items-center gap-1">
                <ArrowRight size={12} />
                再进入证据核对
              </span>
            </div>
          }
        />

        {activeStep === 'summary' && (
          <>
            <div className="theme-card rounded-2xl p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="theme-text-muted flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                  <LayoutDashboard size={14} className="text-pixiu" />
                  证据关系图
                </h3>
                {networkData && (
                  <span className="theme-text-muted text-[10px] italic">拖拽节点 / 缩放查看</span>
                )}
              </div>

              {networkData ? (
                <>
                  <div ref={containerRef} className="theme-card-soft relative h-64 w-full rounded-xl">
                    <ForceGraph
                      graphData={networkData}
                      height={250}
                      width={containerWidth}
                      nodeLabel="name"
                      nodeRelSize={6}
                      linkColor={() => cachedThemeColor('--text-muted', '#64748b')}
                      linkDirectionalArrowLength={3}
                      linkDirectionalArrowRelPos={1}
                      cooldownTicks={100}
                    />
                  </div>

                  {graphLegend.length > 0 && (
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                      {graphLegend.map((item) => (
                        <span key={item.level} className="theme-text-muted inline-flex items-center gap-1.5 text-[10px]">
                          <span
                            className="inline-block h-2 w-2 rounded-full"
                            style={{ backgroundColor: item.color }}
                          />
                          {item.label} {item.count}
                        </span>
                      ))}
                      <span className="theme-text-muted inline-flex items-center gap-1.5 text-[10px]">
                        <span className="inline-block h-2 w-2 rounded-full bg-slate-500" />
                        原文片段
                      </span>
                    </div>
                  )}
                </>
              ) : (
                <div ref={containerRef} className="theme-card-soft flex min-h-40 flex-col items-center justify-center rounded-xl p-6 text-center">
                  <p className="theme-text-primary text-sm font-semibold">暂无证据关系</p>
                  <p className="theme-text-secondary mt-2 max-w-sm text-xs leading-relaxed">
                    本次批判阅读没有主张能落到检索到的原文片段上，因此没有可画的连线；
                    不会用模拟关系兜底展示。
                  </p>
                </div>
              )}
            </div>

            <div className="theme-card rounded-2xl p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="theme-text-muted text-xs font-bold uppercase tracking-wider">多维评分</h3>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metrics} layout="vertical" margin={{ left: -20, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border-subtle)" />
                    <XAxis type="number" domain={[0, 100]} hide />
                    <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 11, fontWeight: 600, fill: 'var(--text-muted)' }} />
                    <Tooltip
                      cursor={{ fill: 'var(--accent-soft)' }}
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
                            {Array.isArray(item.basis) && item.basis.length > 0 && (
                              <div className="mt-2 space-y-1 border-t border-white/10 pt-2 opacity-80">
                                {item.basis.slice(0, 4).map((basis, basisIndex) => (
                                  <div key={`${item.name}-basis-${basisIndex}`}>- {basis}</div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      }}
                    />
                    <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={20}>
                      {metrics.map((entry, index) => (
                        <Cell
                          key={`${entry.name}-${index}`}
                          fill={entry.score >= 80 ? 'var(--accent-strong)' : entry.score >= 60 ? 'var(--accent)' : 'var(--text-muted)'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {noveltyDimensions.length > 0 && (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {noveltyDimensions.map((dimension) => (
                    <div key={dimension.id} className="theme-card-soft rounded-xl p-3">
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <span className="theme-text-primary text-xs font-bold">{dimension.label}</span>
                        <span className="theme-text-muted text-[11px]">{dimension.statusLabel} · {dimension.score} 分</span>
                      </div>
                      <p className="theme-text-secondary text-xs leading-relaxed">{dimension.detail}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {activeStep === 'claims' && (
          <>
            {detailSections.length > 0 && (
              <div className="grid gap-4">
                {detailSections.map((section) => (
                  <InsightCard
                    key={section.key}
                    title={section.title}
                    content={section.content}
                    detailsTitle="展开细节分析"
                    footer={onCaptureArtifact ? (
                      <button
                        type="button"
                        onClick={() =>
                          onCaptureArtifact({
                            kind: `critical-${section.key}`,
                            title: section.title,
                            summary: section.content,
                            content: section.content,
                            tags: ['analysis', section.key],
                          })
                        }
                        className="source-link-chip"
                      >
                        加入工作台
                      </button>
                    ) : null}
                  />
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

            {claimSupportRows.length > 0 && (
              <div className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                  <CheckCircle2 size={14} className="text-pixiu" />
                  主张-证据校验
                </h3>
                <div className="space-y-3">
                  {claimSupportRows.map((row) => (
                    <div key={row.id} className="theme-card-soft rounded-xl p-4">
                      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                        <p className="theme-text-primary min-w-0 flex-1 text-sm font-semibold leading-relaxed">{row.claim}</p>
                        <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${row.supportClassName}`}>
                          {row.supportLabel}
                        </span>
                      </div>
                      <p className="theme-text-secondary text-xs leading-relaxed">{row.reason}</p>
                      {row.missingEvidence.length > 0 && (
                        <div className="mt-3 space-y-1">
                          {row.missingEvidence.map((item, index) => (
                            <div key={`${row.id}-missing-${index}`} className="rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-600">
                              {item}
                            </div>
                          ))}
                        </div>
                      )}
                      {row.numericVerificationStatus !== 'not_applicable' && (
                        <div className="mt-3 rounded-xl border border-sky-400/20 bg-sky-500/10 p-3">
                          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                            <span className="text-xs font-bold text-sky-600">表格/数值证据</span>
                            <span className="text-[11px] font-medium text-sky-600">
                              {row.numericVerificationStatusLabel}
                            </span>
                          </div>
                          {row.numericEvidenceCandidates.length > 0 ? (
                            <div className="space-y-2">
                              {row.numericEvidenceCandidates.map((candidate) => (
                                <div key={candidate.id} className="rounded-lg bg-white/45 p-3 text-xs leading-relaxed dark:bg-slate-950/20">
                                  <div className="mb-1 flex flex-wrap items-center gap-2">
                                    {candidate.label && (
                                      <span className="source-link-chip">{candidate.label}</span>
                                    )}
                                    {candidate.metrics.map((metric) => (
                                      <span key={`${candidate.id}-metric-${metric}`} className="source-link-chip">
                                        {metric}
                                      </span>
                                    ))}
                                    {candidate.numbers.map((number) => (
                                      <span
                                        key={`${candidate.id}-number-${number}`}
                                        className={
                                          (candidate.matchedNumbers || []).includes(number)
                                            ? 'source-link-chip border-emerald-500/40 bg-emerald-500/10 text-emerald-600'
                                            : 'source-link-chip'
                                        }
                                        title={
                                          (candidate.matchedNumbers || []).includes(number)
                                            ? '与主张里的数值逐字一致'
                                            : undefined
                                        }
                                      >
                                        {number}
                                      </span>
                                    ))}
                                  </div>
                                  <p className="theme-text-secondary">{candidate.preview}</p>
                                  <div className="mt-2 flex flex-wrap items-center gap-2">
                                    {candidate.reason && (
                                      <span className="theme-text-muted text-[11px]">{candidate.reason}</span>
                                    )}
                                    <SourceList sources={[candidate]} onJumpToSource={onJumpToSource} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-xs leading-relaxed text-sky-600">
                              未找到可对应的表格/数值片段。
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {activeStep === 'evidence' && (
          <>
            {evidencePreview.length > 0 && (
              <div className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                  <FileText size={14} className="text-pixiu" />
                  证据片段
                </h3>
                <div className="space-y-3">
                  {evidencePreview.map((item) => (
                    <InsightCard
                      key={item.id}
                      title={item.sourceLabel}
                      summary={item.text}
                      keyPoints={[
                        `来源 ID: ${item.sourceId}`,
                        item.chunkIndex !== null ? `片段序号: chunk #${item.chunkIndex + 1}` : '未标注 chunk 序号',
                        item.locationLabel ? `原文位置: ${item.locationLabel}` : '未标注页码',
                      ]}
                      content={item.text}
                      detailsTitle="展开证据片段"
                      footer={<SourceList sources={[item]} onJumpToSource={onJumpToSource} />}
                    />
                  ))}
                </div>
              </div>
            )}

            {sentenceReferences.length > 0 && (
              <div className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-muted mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                  <FileText size={14} className="text-pixiu" />
                  结论引用
                </h3>
                <div className="space-y-3">
                  {sentenceReferences.map((reference) => (
                    <InsightCard
                      key={reference.id}
                      title={`引用来源: ${reference.sourceIds.join('、')}`}
                      summary={reference.sentence}
                      keyPoints={reference.sources.map((source) =>
                        `[${source.sourceId}]${source.locationLabel ? ` ${source.locationLabel}` : ''} ${source.preview}`
                      )}
                      content={[
                        `### 结论`,
                        reference.sentence,
                        '',
                        `### 证据片段`,
                        ...reference.sources.map((source) => `- [${source.sourceId}] ${source.text}`),
                      ].join('\n')}
                      detailsTitle="展开引用证据"
                      footer={reference.sources.some((source) => source.canJumpToSource) ? (
                        <div className="flex flex-wrap gap-2">
                          <SourceList sources={reference.sources} onJumpToSource={onJumpToSource} />
                        </div>
                      ) : null}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-4">
          <div className="flex gap-3">
            <AlertCircle className="shrink-0 text-amber-500" size={18} />
            <p className="text-[11px] leading-normal text-amber-500">
              分析结果建议结合 PDF 原文和划词解释交叉核对，再决定是否发起深度研究。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CriticalAnalysisPanel;
