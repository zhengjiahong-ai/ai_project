export const KNOWLEDGE_LEVEL_OPTIONS = ['入门', '一般', '进阶'];

const STAGE_META = {
  foundation: { title: '基础概念', color: '#0ea5e9' },
  method_prerequisite: { title: '方法前置', color: '#14b8a6' },
  experiment_understanding: { title: '实验理解', color: '#22c55e' },
  critical_perspective: { title: '批判视角', color: '#f59e0b' },
};

export const normalizeKnowledgeLevel = (value) => {
  const text = `${value ?? ''}`.trim();
  if (text === '普通/一般') {
    return '一般';
  }
  return KNOWLEDGE_LEVEL_OPTIONS.includes(text) ? text : '一般';
};

export const normalizeGraph = (data) => {
  const nodes = Array.isArray(data?.graph?.nodes) ? data.graph.nodes : [];
  const links = Array.isArray(data?.graph?.links) ? data.graph.links : [];

  return {
    nodes: nodes.map((node, index) => {
      const stage = node.stage || 'foundation';
      const stageMeta = STAGE_META[stage] || STAGE_META.foundation;
      const confidence = typeof node.confidence === 'number' ? node.confidence : null;

      return {
        id: node.id || `node-${index}`,
        label: node.label || node.name || node.id || `概念 ${index + 1}`,
        type: node.type || 'concept',
        level: node.level || 'basic',
        stage,
        stageLabel: node.stageLabel || stageMeta.title,
        summary: node.summary || '',
        why: node.why || '',
        sourceIds: Array.isArray(node.sourceIds) ? node.sourceIds : [],
        confidence,
        val: node.type === 'paper' ? 14 : confidence && confidence >= 0.8 ? 9 : 7,
        color: node.type === 'paper' ? '#4D0099' : stageMeta.color,
      };
    }),
    links: links.map((link) => ({
      source: link.source,
      target: link.target,
      relation: link.relation || 'related',
      label: link.label || link.relation || 'related',
    })),
  };
};

export const resolveLearningPathSections = (data) => {
  const sections = Array.isArray(data?.learning_path_sections) ? data.learning_path_sections : [];
  if (sections.length > 0) {
    return sections
      .map((section) => ({
        key: section.key || 'custom',
        title: section.title || '学习路径',
        items: Array.isArray(section.items) ? section.items : [],
      }))
      .filter((section) => section.items.length > 0);
  }

  const learningPath = Array.isArray(data?.learning_path) ? data.learning_path : [];
  if (learningPath.length === 0) {
    return [];
  }

  return [{
    key: 'legacy',
    title: '学习路径',
    items: learningPath.map((step, index) => ({
      title: step.title || step.label || `第 ${index + 1} 步`,
      goal: step.goal || step.summary || '',
      conceptIds: Array.isArray(step.conceptIds) ? step.conceptIds : [],
      sourceIds: Array.isArray(step.sourceIds) ? step.sourceIds : [],
      stage: step.stage || 'foundation',
      stageLabel: step.stageLabel || '学习路径',
      step: step.step || index + 1,
    })),
  }];
};

export const createGenerateHandler = (onGenerate, knowledgeLevel) => () =>
  onGenerate?.(normalizeKnowledgeLevel(knowledgeLevel));

export const getUncoveredNodeLabels = (data) => {
  const sourceCoverage = data?.sourceCoverage;
  if (!Array.isArray(sourceCoverage?.uncoveredConceptIds)) {
    return [];
  }
  const labelMap = new Map(
    (Array.isArray(data?.graph?.nodes) ? data.graph.nodes : []).map((node) => [node.id, node.label || node.id]),
  );
  return sourceCoverage.uncoveredConceptIds.map((nodeId) => labelMap.get(nodeId) || nodeId);
};

export const createBackgroundKnowledgeSnapshot = (data, knowledgeLevel = '一般') => {
  const sections = resolveLearningPathSections(data);
  return {
    selectedKnowledgeLevel: normalizeKnowledgeLevel(knowledgeLevel || data?.user_knowledge_level),
    displayedKnowledgeLevel: data?.user_knowledge_level || normalizeKnowledgeLevel(knowledgeLevel),
    graphNodeCount: normalizeGraph(data).nodes.length,
    graphLinkCount: normalizeGraph(data).links.length,
    learningSectionTitles: sections.map((section) => section.title),
    learningItems: sections.flatMap((section) => section.items.map((item) => item.title)),
    backgroundItems: Array.isArray(data?.background_knowledge) ? data.background_knowledge : [],
    ragSourceIds: (Array.isArray(data?.rag_sources) ? data.rag_sources : []).map((source) => source.id || source.sourceId),
    hasConfidence: typeof data?.confidence === 'number',
    hasSourceCoverage: Boolean(data?.sourceCoverage),
    uncoveredNodeLabels: getUncoveredNodeLabels(data),
    neo4jMessage: data?.neo4j?.enabled
      ? data?.neo4j?.message || data?.neo4j?.status || ''
      : '未配置 Neo4j，已使用接口返回的图谱结果。',
  };
};
