import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph from 'react-force-graph-2d';
import { BookOpenCheck, Database, Loader2, Network, RefreshCw, Route } from 'lucide-react';
import MarkdownContent from './MarkdownContent';

const normalizeGraph = (data) => {
  const nodes = Array.isArray(data?.graph?.nodes) ? data.graph.nodes : [];
  const links = Array.isArray(data?.graph?.links) ? data.graph.links : [];

  return {
    nodes: nodes.map((node, index) => ({
      id: node.id || `node-${index}`,
      label: node.label || node.name || node.id || `概念 ${index + 1}`,
      type: node.type || 'concept',
      level: node.level || 'basic',
      summary: node.summary || '',
      why: node.why || '',
      sourceIds: Array.isArray(node.sourceIds) ? node.sourceIds : [],
      val: node.type === 'paper' ? 14 : node.level === 'advanced' ? 9 : 7,
      color: node.type === 'paper' ? '#4D0099' : node.level === 'advanced' ? '#f59e0b' : '#0ea5e9',
    })),
    links: links.map((link) => ({
      source: link.source,
      target: link.target,
      relation: link.relation || 'related',
      label: link.label || link.relation || 'related',
    })),
  };
};

const BackgroundKnowledgePanel = ({ data, isLoading, hasPaperContext, onGenerate }) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(320);

  useEffect(() => {
    if (containerRef.current) {
      setContainerWidth(Math.max(260, containerRef.current.offsetWidth - 40));
    }
  }, [data, isLoading]);

  const graphData = useMemo(() => normalizeGraph(data), [data]);
  const learningPath = Array.isArray(data?.learning_path) ? data.learning_path : [];
  const backgroundItems = Array.isArray(data?.background_knowledge) ? data.background_knowledge : [];
  const ragSources = Array.isArray(data?.rag_sources) ? data.rag_sources : [];

  if (!data && !isLoading) {
    return (
      <div className="theme-panel-muted flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-pixiu/10">
          <Network className="text-pixiu" size={40} />
        </div>
        <h3 className="theme-text-primary text-xl font-bold">生成前置知识图谱</h3>
        <p className="theme-text-secondary mb-8 mt-2 max-w-sm text-sm">
          先把阅读这篇论文需要补齐的概念、方法和依赖关系梳理成一条学习路径。
        </p>
        <button
          onClick={onGenerate}
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
        <p className="theme-text-secondary mt-2 text-xs">正在结合当前论文、RAG 片段和学习路径生成依赖关系。</p>
      </div>
    );
  }

  return (
    <div className="theme-panel-muted flex h-full flex-col overflow-hidden">
      <div className="theme-panel theme-border sticky top-0 z-10 flex items-center justify-between border-b px-6 py-4">
        <h2 className="theme-text-primary flex items-center gap-2 text-lg font-bold">
          <Network className="text-pixiu" size={20} />
          背景补课图谱
        </h2>
        <button
          onClick={onGenerate}
          className="theme-button-secondary flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition"
        >
          <RefreshCw size={16} />
          重新生成
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div ref={containerRef} className="theme-card overflow-hidden rounded-2xl p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="theme-text-primary text-sm font-bold">{data?.paper_topic || '当前论文'}</h3>
              <div className="theme-text-secondary mt-1 text-xs">默认知识水平：{data?.user_knowledge_level || '普通/一般'}</div>
            </div>
            <span className="theme-text-muted text-[10px] italic">拖拽节点 / 滚轮缩放</span>
          </div>

          <div className="theme-card-soft relative h-72 w-full rounded-xl">
            <ForceGraph
              graphData={graphData}
              height={280}
              width={containerWidth}
              nodeLabel={(node) => `${node.label}\n${node.summary || node.why || ''}`}
              nodeRelSize={6}
              linkColor={() => '#64748b'}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              cooldownTicks={100}
            />
          </div>
        </div>

        {learningPath.length > 0 && (
          <div className="theme-card rounded-2xl p-5">
            <h3 className="theme-text-primary mb-4 flex items-center gap-2 text-sm font-bold">
              <Route size={16} className="text-pixiu" />
              学习路径
            </h3>
            <div className="space-y-3">
              {learningPath.map((step, index) => (
                <div key={`${step.title}-${index}`} className="theme-card-soft rounded-xl px-4 py-3">
                  <div className="theme-text-primary text-sm font-semibold">
                    {step.step || index + 1}. {step.title}
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
