import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph from 'react-force-graph-2d';
import { BookOpenCheck, Database, Loader2, Network, RefreshCw, Route, ShieldCheck } from 'lucide-react';
import InsightCard from './InsightCard.jsx';
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
  onCaptureArtifact,
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
  const overviewSummary = useMemo(() => {
    if (!data) {
      return '先生成背景补课图谱，帮助我们在阅读前补齐必要概念。';
    }

    return `这张图谱会优先说明为了理解“${data?.paper_topic || '当前论文'}”，你还需要补哪些概念、方法和批判视角。`;
  }, [data]);
  const overviewPoints = useMemo(
    () => [
      graphData.nodes.length > 0 ? `图谱包含 ${graphData.nodes.length} 个节点` : '等待图谱节点生成',
      learningSections.length > 0 ? `学习路径已分成 ${learningSections.length} 个阶段` : '暂未生成学习路径',
      backgroundItems.length > 0 ? `推荐补课主题 ${backgroundItems.length} 项` : '暂未生成补课清单',
    ],
    [backgroundItems.length, graphData.nodes.length, learningSections.length],
  );

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
        <InsightCard
          title="为什么先补这些背景"
          icon={<BookOpenCheck size={16} className="text-pixiu" />}
          summary={overviewSummary}
          keyPoints={overviewPoints}
          footer={onCaptureArtifact ? (
            <button
              type="button"
              onClick={() => onCaptureArtifact({
                kind: 'background-overview',
                title: '背景补课总览',
                summary: overviewSummary,
                content: [overviewSummary, ...overviewPoints.map((item) => `- ${item}`)].join('\n\n'),
                tags: ['background', selectedKnowledgeLevel],
              })}
              className="source-link-chip"
            >
              加入工作台
            </button>
          ) : null}
        />

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
              <InsightCard
                title="图谱置信度"
                icon={<ShieldCheck size={16} className="text-pixiu" />}
                summary={confidenceText}
                keyPoints={['综合考虑节点解释完整度和证据覆盖比例。']}
              />
            )}

            {sourceCoverage && (
              <InsightCard
                title="依据覆盖率"
                summary={coverageText || `${sourceCoverage.conceptsWithSources}/${sourceCoverage.totalConcepts}`}
                keyPoints={[
                  `${sourceCoverage.conceptsWithSources}/${sourceCoverage.totalConcepts} 个概念节点已绑定依据片段。`,
                  ...(uncoveredNodeLabels.length > 0 ? [`待补证据：${uncoveredNodeLabels.join('、')}`] : []),
                ]}
              />
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
                      <InsightCard
                        key={`${section.key}-${step.title}-${index}`}
                        title={`${step.step || index + 1}. ${step.title}`}
                        summary={step.goal || `${step.title} 是当前阶段的重要补课节点。`}
                        keyPoints={step.stageLabel ? [step.stageLabel] : []}
                        content={step.goal || ''}
                        detailsTitle="展开学习说明"
                      />
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
                <InsightCard
                  key={source.id}
                  title={source.id}
                  summary={source.text || '暂无片段内容'}
                  content={source.text || ''}
                  detailsTitle="展开依据片段"
                  footer={onCaptureArtifact ? (
                    <button
                      type="button"
                      onClick={() => onCaptureArtifact({
                        kind: 'background-evidence',
                        title: `背景依据 ${source.id}`,
                        summary: source.text || '暂无片段内容',
                        content: source.text || '',
                        tags: ['background', 'evidence'],
                      })}
                      className="source-link-chip"
                    >
                      加入工作台
                    </button>
                  ) : null}
                />
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
