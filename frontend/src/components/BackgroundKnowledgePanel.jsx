import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph from 'react-force-graph-2d';
import { BookOpenCheck, Database, Loader2, Network, RefreshCw, Route, ShieldCheck } from 'lucide-react';
import MarkdownContent from './MarkdownContent';
import {
  KNOWLEDGE_LEVEL_OPTIONS,
  createGenerateHandler,
  getUncoveredNodeLabels,
  normalizeGraph,
  normalizeKnowledgeLevel,
  resolveLearningPathSections,
} from './backgroundKnowledgePanelModel.js';

const formatPercent = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  return `${Math.round(value * 100)}%`;
};

const KnowledgeLevelPicker = ({ value, onChange, compact = false }) => (
  <label className={`flex ${compact ? 'items-center gap-2' : 'flex-col gap-2'} text-left`}>
    <span className="theme-text-secondary text-xs font-medium">知识水平</span>
    <select
      value={normalizeKnowledgeLevel(value)}
      onChange={(event) => onChange?.(normalizeKnowledgeLevel(event.target.value))}
      className="theme-card-soft theme-text-primary rounded-lg border border-transparent px-3 py-2 text-sm outline-none transition focus:border-pixiu/40"
    >
      {KNOWLEDGE_LEVEL_OPTIONS.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  </label>
);

const BackgroundKnowledgePanel = ({
  data,
  isLoading,
  hasPaperContext,
  onGenerate,
  knowledgeLevel = '一般',
  onKnowledgeLevelChange,
  GraphComponent = ForceGraph,
}) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(320);

  useEffect(() => {
    if (containerRef.current) {
      setContainerWidth(Math.max(260, containerRef.current.offsetWidth - 40));
    }
  }, [data, isLoading]);

  const selectedKnowledgeLevel = normalizeKnowledgeLevel(knowledgeLevel || data?.user_knowledge_level);
  const graphData = useMemo(() => normalizeGraph(data), [data]);
  const learningSections = useMemo(() => resolveLearningPathSections(data), [data]);
  const backgroundItems = Array.isArray(data?.background_knowledge) ? data.background_knowledge : [];
  const ragSources = Array.isArray(data?.rag_sources) ? data.rag_sources : [];
  const sourceCoverage = data?.sourceCoverage && typeof data.sourceCoverage === 'object' ? data.sourceCoverage : null;
  const confidenceText = formatPercent(data?.confidence);
  const coverageText = formatPercent(sourceCoverage?.ratio);
  const uncoveredNodeLabels = useMemo(() => getUncoveredNodeLabels(data), [data]);
  const handleGenerate = createGenerateHandler(onGenerate, selectedKnowledgeLevel);

  if (!data && !isLoading) {
    return (
      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <Network className="text-pixiu" size={40} />
        </div>
        <h3 className="theme-text-primary text-xl font-bold">生成前置知识图谱</h3>
        <p className="theme-text-secondary mb-6 mt-2 max-w-sm text-sm">
          先把阅读这篇论文需要补齐的概念、方法和依赖关系梳理成一条学习路径。
        </p>
        <div className="mb-6 w-full max-w-xs">
          <KnowledgeLevelPicker value={selectedKnowledgeLevel} onChange={onKnowledgeLevelChange} />
        </div>
        <button
          onClick={handleGenerate}
          disabled={!hasPaperContext}
          className="flex items-center gap-2 rounded-lg bg-pixiu px-6 py-3 text-sm font-semibold text-white shadow-lg transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          <BookOpenCheck size={18} />
          开始背景补课
        </button>
        {!hasPaperContext && (
          <div className="theme-text-muted mt-4 text-xs">请先上传并完成篇章解构，系统才能基于当前论文生成图谱。</div>
        )}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="theme-panel flex h-full flex-col items-center justify-center p-8 text-center">
        <Loader2 className="mb-5 animate-spin text-pixiu" size={48} />
        <p className="theme-text-primary text-lg font-medium">正在构建前置知识图谱...</p>
        <p className="theme-text-secondary mt-2 text-xs">
          正在结合当前论文、RAG 片段和学习路径生成依赖关系，当前知识水平：{selectedKnowledgeLevel}。
        </p>
      </div>
    );
  }

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b px-6 py-4">
        <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
          <Network className="text-pixiu" size={20} />
          背景补课图谱
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <KnowledgeLevelPicker value={selectedKnowledgeLevel} onChange={onKnowledgeLevelChange} compact />
          <button
            onClick={handleGenerate}
            className="theme-button-secondary flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition"
          >
            <RefreshCw size={16} />
            重新生成
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div ref={containerRef} className="theme-card overflow-hidden rounded-2xl p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="theme-text-primary text-sm font-bold">{data?.paper_topic || '当前论文'}</h3>
              <div className="theme-text-secondary mt-1 text-xs">当前知识水平：{data?.user_knowledge_level || selectedKnowledgeLevel}</div>
            </div>
            <span className="theme-text-muted text-[10px] italic">拖拽节点 / 滚轮缩放</span>
          </div>

          <div className="theme-card-soft relative h-72 w-full rounded-xl">
            {React.createElement(GraphComponent, {
              graphData,
              height: 280,
              width: containerWidth,
              nodeLabel: (node) => `${node.label}\n${node.stageLabel}\n${node.summary || node.why || ''}`,
              nodeRelSize: 6,
              linkColor: () => '#64748b',
              linkDirectionalArrowLength: 3,
              linkDirectionalArrowRelPos: 1,
              cooldownTicks: 100,
            })}
          </div>
        </div>

        {(confidenceText || sourceCoverage) && (
          <div className="grid gap-4 md:grid-cols-2">
            {confidenceText && (
              <div className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-primary mb-2 flex items-center gap-2 text-sm font-bold">
                  <ShieldCheck size={16} className="text-pixiu" />
                  图谱置信度
                </h3>
                <div className="theme-text-primary text-2xl font-bold">{confidenceText}</div>
                <div className="theme-text-secondary mt-1 text-xs">综合考虑节点解释完整度和证据覆盖比例。</div>
              </div>
            )}

            {sourceCoverage && (
              <div className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-primary mb-2 text-sm font-bold">依据覆盖率</h3>
                <div className="theme-text-primary text-2xl font-bold">{coverageText || `${sourceCoverage.conceptsWithSources}/${sourceCoverage.totalConcepts}`}</div>
                <div className="theme-text-secondary mt-1 text-xs">
                  {sourceCoverage.conceptsWithSources}/{sourceCoverage.totalConcepts} 个概念节点已绑定依据片段。
                </div>
                {uncoveredNodeLabels.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {uncoveredNodeLabels.map((label) => (
                      <span key={label} className="rounded-full bg-amber-500/10 px-3 py-1 text-[11px] font-semibold text-amber-600">
                        {label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {learningSections.length > 0 && (
          <div className="theme-card rounded-2xl p-5">
            <h3 className="theme-text-primary mb-4 flex items-center gap-2 text-sm font-bold">
              <Route size={16} className="text-pixiu" />
              学习路径
            </h3>
            <div className="space-y-5">
              {learningSections.map((section) => (
                <div key={section.key} className="space-y-3">
                  <div className="theme-text-primary text-sm font-semibold">{section.title}</div>
                  <div className="space-y-3">
                    {section.items.map((step, index) => (
                      <div key={`${section.key}-${step.title}-${index}`} className="theme-card-soft rounded-xl px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="theme-text-primary text-sm font-semibold">
                            {step.step || index + 1}. {step.title}
                          </div>
                          {step.stageLabel && (
                            <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[11px] font-semibold text-pixiu">
                              {step.stageLabel}
                            </span>
                          )}
                        </div>
                        {step.goal && (
                          <MarkdownContent className="theme-text-secondary prose prose-sm mt-2 max-w-none text-sm">
                            {step.goal}
                          </MarkdownContent>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {backgroundItems.length > 0 && (
          <div className="theme-card rounded-2xl p-5">
            <h3 className="theme-text-primary mb-3 text-sm font-bold">建议补课清单</h3>
            <div className="flex flex-wrap gap-2">
              {backgroundItems.map((item) => (
                <span key={item} className="rounded-full bg-pixiu/10 px-3 py-1 text-xs font-semibold text-pixiu">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {ragSources.length > 0 && (
          <div className="theme-card rounded-2xl p-5">
            <h3 className="theme-text-primary mb-3 text-sm font-bold">RAG 依据片段</h3>
            <div className="space-y-3">
              {ragSources.map((source) => (
                <div key={source.id} className="theme-markdown-panel rounded-xl px-4 py-3 text-sm">
                  <div className="mb-2 text-xs font-semibold text-pixiu">{source.id}</div>
                  <MarkdownContent className="theme-text-secondary prose prose-sm max-w-none">
                    {source.text || '暂无片段内容'}
                  </MarkdownContent>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="theme-card rounded-2xl p-5">
          <h3 className="theme-text-primary mb-2 flex items-center gap-2 text-sm font-bold">
            <Database size={16} className="text-pixiu" />
            Neo4j 状态
          </h3>
          <div className="theme-text-secondary text-sm">
            {data?.neo4j?.enabled
              ? data?.neo4j?.message || data?.neo4j?.status
              : '未配置 Neo4j，已使用接口返回的图谱结果。'}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BackgroundKnowledgePanel;
