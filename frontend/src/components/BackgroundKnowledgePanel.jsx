import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph from 'react-force-graph-2d';
import {
  BookOpenCheck,
  Database,
  Link2,
  Loader2,
  Network,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

import InsightCard from './InsightCard.jsx';
import {
  createGenerateHandler,
  getProvenanceMeta,
  getUncoveredNodeLabels,
  normalizeGraph,
  normalizeKnowledgeLevel,
  normalizeProvenanceSummary,
  normalizeReaderProfile,
  resolveLearningPathSections,
  summarizeReaderProfile,
} from './backgroundKnowledgePanelModel.js';
import SourceList from './SourceCitation.jsx';
import { normalizeEvidenceSources } from './evidenceCitationModel.js';

const EMPTY_LIST = [];

const learningModes = [
  { id: 'why', label: '先补什么' },
  { id: 'path', label: '怎么补' },
  { id: 'sources', label: '看依据' },
];

const formatPercent = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  return `${Math.round(value * 100)}%`;
};

const normalizeText = (value) => `${value ?? ''}`.trim();

const uniqueStrings = (items = []) => {
  const seen = new Set();
  return items.filter((item) => {
    const key = normalizeText(item);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};

const BackgroundKnowledgePanel = ({
  data,
  isLoading,
  hasPaperContext,
  onGenerate,
  readerProfile,
  GraphComponent = ForceGraph,
  onCaptureArtifact,
  onJumpToSource,
}) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(320);
  const [activeMode, setActiveMode] = useState('why');
  const [visiblePathCount, setVisiblePathCount] = useState(2);
  const [selectedGraphItem, setSelectedGraphItem] = useState(null);

  useEffect(() => {
    if (containerRef.current) {
      setContainerWidth(Math.max(260, containerRef.current.offsetWidth - 40));
    }
  }, [data, isLoading]);

  const selectedReaderProfile = normalizeReaderProfile(
    readerProfile || data?.reader_profile || { user_knowledge_level: data?.user_knowledge_level },
  );
  const selectedKnowledgeLevel = normalizeKnowledgeLevel(
    selectedReaderProfile.selfAssessedFamiliarity || data?.user_knowledge_level,
  );
  const graphData = useMemo(() => normalizeGraph(data), [data]);
  const learningSections = useMemo(() => resolveLearningPathSections(data), [data]);
  const backgroundItems = Array.isArray(data?.background_knowledge) ? data.background_knowledge : EMPTY_LIST;
  const ragSources = normalizeEvidenceSources(data?.rag_sources);
  const sourceCoverage = data?.sourceCoverage && typeof data.sourceCoverage === 'object' ? data.sourceCoverage : null;
  const provenanceSummary = normalizeProvenanceSummary(data);
  const confidenceText = formatPercent(data?.confidence);
  const coverageText = formatPercent(sourceCoverage?.ratio);
  const uncoveredNodeLabels = useMemo(() => getUncoveredNodeLabels(data), [data]);
  const handleGenerate = createGenerateHandler(onGenerate, selectedReaderProfile);
  const readerProfileSummary = summarizeReaderProfile(data?.reader_profile || selectedReaderProfile);

  const nodeByLabel = useMemo(() => {
    const map = new Map();
    graphData.nodes.forEach((node) => {
      const key = normalizeText(node.label).toLowerCase();
      if (key && !map.has(key)) {
        map.set(key, node);
      }
    });
    return map;
  }, [graphData.nodes]);

  const overviewSummary = useMemo(() => {
    if (!data) {
      return '先生成背景补课图谱，再按阅读需要逐步补齐概念、方法和批判视角。';
    }

    return `为了更好理解 ${data?.paper_topic || '当前论文'}，建议优先补齐最影响精读推进的背景节点。`;
  }, [data]);

  const overviewPoints = useMemo(
    () => [
      graphData.nodes.length > 0 ? `图谱包含 ${graphData.nodes.length} 个知识节点` : '等待图谱节点生成',
      learningSections.length > 0 ? `学习路径已拆成 ${learningSections.length} 个阶段` : '尚未生成学习路径',
      backgroundItems.length > 0 ? `推荐补课主题 ${backgroundItems.length} 项` : '尚未生成补课主题',
    ],
    [backgroundItems.length, graphData.nodes.length, learningSections.length],
  );

  const backgroundCards = useMemo(
    () =>
      backgroundItems.slice(0, 6).map((item) => {
        const node = nodeByLabel.get(normalizeText(item).toLowerCase());
        const stageLabel = normalizeText(node?.stageLabel);
        const whyText =
          normalizeText(node?.why) ||
          normalizeText(node?.summary) ||
          (stageLabel
            ? `建议先补这一部分的 ${stageLabel}，再继续精读正文。`
            : '建议先补这一部分背景，再继续精读正文。');

        return {
          title: item,
          stageLabel,
          whyText,
          provenanceLabel: node?.provenanceLabel || getProvenanceMeta('unknown').label,
        };
      }),
    [backgroundItems, nodeByLabel],
  );

  if (!data && !isLoading) {
    return (
      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <Network className="text-pixiu" size={40} />
        </div>
        <h3 className="theme-text-primary text-xl font-bold">生成背景补课图谱</h3>
        <p className="theme-text-secondary mb-6 mt-2 max-w-sm text-sm">
          先把这篇论文需要的概念、方法和依赖关系梳理成一条可执行的补课路径。
        </p>
        <div className="theme-card-soft theme-text-secondary mb-6 w-full max-w-2xl rounded-2xl px-4 py-3 text-sm leading-6">
          补课偏好已经收进上方悬停菜单。先在顶部微调熟悉度、目标和卡点，再开始生成会更准确。
        </div>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={!hasPaperContext}
          className="flex items-center gap-2 rounded-lg bg-pixiu px-6 py-3 text-sm font-semibold text-white shadow-lg transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          <BookOpenCheck size={18} />
          开始补课
        </button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="theme-panel flex h-full flex-col items-center justify-center p-8 text-center">
        <Loader2 className="mb-5 animate-spin text-pixiu" size={48} />
        <p className="theme-text-primary text-lg font-medium">正在构建背景知识图谱</p>
        <p className="theme-text-secondary mt-2 text-xs">
          系统会结合你的自评、卡点和最近阅读行为，先梳理依赖关系，再生成可执行的补课顺序。
        </p>
      </div>
    );
  }

  const flattenedPathSteps = learningSections.flatMap((section) =>
    section.items.map((step, index) => ({
      ...step,
      groupTitle: section.title,
      stepNumber: step.step || index + 1,
    })),
  );
  const visiblePathSteps = flattenedPathSteps.slice(0, visiblePathCount);

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 border-b px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
            <Network className="text-pixiu" size={20} />
            背景补课
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleGenerate}
              className="theme-button-secondary flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition"
            >
              <RefreshCw size={16} />
              重新生成
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-start gap-2">
          <span className="theme-text-secondary pt-1 text-xs font-medium">本次补课依据</span>
          <div className="flex flex-1 flex-wrap gap-2">
            {readerProfileSummary.map((item) => (
              <span key={item} className="workbench-kind-chip">
                {item}
              </span>
            ))}
            {data?.adaptation_reason && (
              <span className="theme-card-soft theme-text-secondary rounded-full px-3 py-1 text-xs leading-6">
                {data.adaptation_reason}
              </span>
            )}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {learningModes.map((mode) => (
            <button
              key={mode.id}
              type="button"
              onClick={() => setActiveMode(mode.id)}
              className={`workspace-section-tab ${activeMode === mode.id ? 'workspace-section-tab-active' : ''}`}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        <InsightCard
          title="为什么先补这些背景"
          icon={<BookOpenCheck size={16} className="text-pixiu" />}
          summary={overviewSummary}
          keyPoints={overviewPoints}
          footer={
            onCaptureArtifact ? (
              <button
                type="button"
                onClick={() =>
                  onCaptureArtifact({
                    kind: 'background-overview',
                    title: '背景补课总览',
                    summary: overviewSummary,
                    content: [overviewSummary, ...overviewPoints.map((item) => `- ${item}`)].join('\n\n'),
                    tags: ['background', selectedKnowledgeLevel],
                  })
                }
                className="source-link-chip"
              >
                加入工作台
              </button>
            ) : null
          }
        />

        {activeMode === 'why' && (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              {backgroundCards.map((item) => (
                <div key={item.title} className="theme-card rounded-2xl p-4 text-sm theme-text-secondary">
                  <div className="theme-text-primary mb-2 text-sm font-semibold">{item.title}</div>
                  {item.stageLabel && (
                    <div className="mb-2 flex flex-wrap gap-2">
                      <span className="workbench-kind-chip">{item.stageLabel}</span>
                      <span className="workbench-kind-chip">{item.provenanceLabel}</span>
                    </div>
                  )}
                  <div className="line-clamp-3 leading-7">{item.whyText}</div>
                </div>
              ))}
            </div>

            <div ref={containerRef} className="theme-card rounded-2xl p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h3 className="theme-text-primary text-sm font-bold">{data?.paper_topic || '当前论文'}</h3>
                  <div className="theme-text-secondary mt-1 text-xs">
                    当前识别的熟悉程度：{data?.user_knowledge_level || selectedKnowledgeLevel}
                  </div>
                </div>
                <span className="theme-text-muted text-[10px] italic">拖拽节点 / 滚轮缩放</span>
              </div>

              <div className="theme-card-soft relative h-72 w-full rounded-xl">
                {React.createElement(GraphComponent, {
                  graphData,
                  height: 280,
                  width: containerWidth,
                  nodeLabel: (node) => `${node.label}\n${node.stageLabel}\n${node.provenanceLabel}\n${node.confidenceReason || node.summary || node.why || ''}`,
                  linkLabel: (link) => `${link.label}\n${link.provenanceLabel}\n${link.confidenceReason || ''}`,
                  onNodeClick: (node) => setSelectedGraphItem({ kind: 'node', ...node }),
                  onLinkClick: (link) => setSelectedGraphItem({ kind: 'edge', ...link }),
                  nodeRelSize: 6,
                  linkColor: () => '#64748b',
                  linkDirectionalArrowLength: 3,
                  linkDirectionalArrowRelPos: 1,
                  cooldownTicks: 100,
                })}
              </div>

              {selectedGraphItem && (
                <div className="theme-card-soft mt-4 rounded-xl p-4 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="theme-text-primary font-semibold">
                      {selectedGraphItem.kind === 'node'
                        ? selectedGraphItem.label
                        : `${selectedGraphItem.source?.label || selectedGraphItem.source} → ${selectedGraphItem.target?.label || selectedGraphItem.target}`}
                    </span>
                    <span className="workbench-kind-chip">
                      {selectedGraphItem.provenanceLabel || getProvenanceMeta(selectedGraphItem.provenanceStatus).label}
                    </span>
                    {typeof selectedGraphItem.confidence === 'number' && (
                      <span className="workbench-kind-chip">置信度 {formatPercent(selectedGraphItem.confidence)}</span>
                    )}
                  </div>
                  <p className="theme-text-secondary mt-2 leading-6">
                    {selectedGraphItem.confidenceReason || selectedGraphItem.summary || selectedGraphItem.why || '暂无补充说明。'}
                  </p>
                  {Array.isArray(selectedGraphItem.sourceIds) && selectedGraphItem.sourceIds.length > 0 && (
                    <p className="theme-text-muted mt-2 text-xs">依据：{selectedGraphItem.sourceIds.join('、')}</p>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {activeMode === 'path' && (
          <>
            {visiblePathSteps.map((step, index) => {
              const stepKeyPoints = uniqueStrings([
                step.groupTitle,
                step.stageLabel && step.stageLabel !== step.groupTitle ? step.stageLabel : '',
                Array.isArray(step.sourceIds) && step.sourceIds.length > 0 ? `依据：${step.sourceIds.join('、')}` : '',
                ...(Array.isArray(step.prerequisiteEdges)
                  ? step.prerequisiteEdges.slice(0, 2).map((edge) => {
                    const supportText = edge.sourceIds?.length
                      ? `依据：${edge.sourceIds.join('、')}`
                      : edge.confidenceReason || '基于当前学习路径推断';
                    const provenanceLabel = getProvenanceMeta(edge.provenanceStatus).label;
                    return `后续会用到：${edge.target}，${provenanceLabel}，${supportText}`;
                  })
                  : []),
              ]);

              const detailBlocks = uniqueStrings([
                step.goal || '',
                Array.isArray(step.sourceIds) && step.sourceIds.length > 0
                  ? `### 相关依据\n- ${step.sourceIds.join('\n- ')}`
                  : '',
                Array.isArray(step.prerequisiteEdges) && step.prerequisiteEdges.length > 0
                  ? `### 学完后继续看\n- ${step.prerequisiteEdges.slice(0, 3).map((edge) => edge.target).join('\n- ')}`
                  : '',
              ]).join('\n\n');

              return (
                <InsightCard
                  key={`${step.groupTitle}-${step.title}-${index}`}
                  title={`${index + 1}. ${step.title}`}
                  summary={step.goal || `${step.title} 是这一阶段的关键补课点。`}
                  keyPoints={stepKeyPoints}
                  content={detailBlocks}
                  detailsTitle="展开学习说明"
                />
              );
            })}

            {visiblePathCount < flattenedPathSteps.length && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() => setVisiblePathCount((count) => Math.min(count + 2, flattenedPathSteps.length))}
                  className="workflow-next-action workflow-next-action-primary"
                >
                  再展开 2 步补课路径
                </button>
              </div>
            )}
          </>
        )}

        {activeMode === 'sources' && (
          <>
            {(confidenceText || sourceCoverage) && (
              <div className="grid gap-4 md:grid-cols-2">
                {confidenceText && (
                  <InsightCard
                    title="图谱置信度"
                    icon={<ShieldCheck size={16} className="text-pixiu" />}
                    summary={confidenceText}
                    keyPoints={['综合节点结构完整性和证据覆盖比例得出。']}
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

            {provenanceSummary && (
              <div className="grid gap-4 md:grid-cols-2">
                <InsightCard
                  title="概念节点证据覆盖"
                  summary={formatPercent(provenanceSummary.nodes.supportedRatio) || '0%'}
                  keyPoints={[
                    `当前论文支持 ${provenanceSummary.nodes.currentPaperSupported}/${provenanceSummary.nodes.total}`,
                    provenanceSummary.nodes.externalSupported > 0 ? `外部证据支持 ${provenanceSummary.nodes.externalSupported} 项` : '',
                    `模型推断 ${provenanceSummary.nodes.modelInference} 项`,
                  ].filter(Boolean)}
                />
                <InsightCard
                  title="前置关系证据覆盖"
                  summary={formatPercent(provenanceSummary.edges.supportedRatio) || '0%'}
                  keyPoints={[
                    `当前论文支持 ${provenanceSummary.edges.currentPaperSupported}/${provenanceSummary.edges.total}`,
                    provenanceSummary.edges.externalSupported > 0 ? `外部证据支持 ${provenanceSummary.edges.externalSupported} 条` : '',
                    `模型推断 ${provenanceSummary.edges.modelInference} 条`,
                  ].filter(Boolean)}
                />
              </div>
            )}

            <div className="theme-card-soft theme-text-secondary rounded-2xl p-4 text-sm leading-6">
              {data?.externalKnowledge?.enabled
                ? data.externalKnowledge.message || '已启用受控外部学术来源。'
                : (provenanceSummary?.nodes?.externalSupported > 0 || provenanceSummary?.edges?.externalSupported > 0)
                  ? `已通过外部学术来源补充 ${provenanceSummary.nodes.externalSupported + provenanceSummary.edges.externalSupported} 项证据。`
                  : '当前未使用外部学术来源；无当前论文依据的节点和关系均标记为模型推断。'}
            </div>

            {Array.isArray(data?.warnings) && data.warnings.length > 0 && (
              <InsightCard title="生成提示" keyPoints={data.warnings} />
            )}

            {ragSources.length > 0 && (
              <div className="theme-card rounded-2xl p-5">
                <h3 className="theme-text-primary mb-3 text-sm font-bold">RAG 依据片段</h3>
                <div className="space-y-3">
                  {ragSources.map((source) => (
                    <InsightCard
                      key={source.sourceId}
                      title={source.sourceId}
                      summary={source.text || '暂无片段内容'}
                      content={source.text || ''}
                      detailsTitle="展开依据片段"
                      footer={
                        onCaptureArtifact || source.canJumpToSource ? (
                          <div className="flex flex-wrap gap-2">
                            {onCaptureArtifact && (
                              <button
                                type="button"
                                onClick={() =>
                                  onCaptureArtifact({
                                    kind: 'background-evidence',
                                    title: `背景依据 ${source.sourceId}`,
                                    summary: source.text || '暂无片段内容',
                                    content: source.text || '',
                                    tags: ['background', 'evidence'],
                                  })
                                }
                                className="source-link-chip"
                              >
                                加入工作台
                              </button>
                            )}
                            <SourceList sources={[source]} onJumpToSource={onJumpToSource} />
                          </div>
                        ) : null
                      }
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
                  : '未配置 Neo4j，当前图谱来自接口返回结构。'}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default BackgroundKnowledgePanel;
