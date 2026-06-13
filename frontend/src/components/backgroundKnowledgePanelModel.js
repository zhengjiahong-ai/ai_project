export const KNOWLEDGE_LEVEL_OPTIONS = ['入门', '一般', '进阶'];
export const BACKGROUND_DEPTH_OPTIONS = ['速览', '标准', '深入'];
export const BACKGROUND_GOAL_OPTIONS = ['扫清概念障碍', '理解方法链路', '为批判阅读做准备'];

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

export const createDefaultReaderProfile = () => ({
  selfAssessedFamiliarity: '一般',
  preferredDepth: '标准',
  learningGoal: '',
  knownConcepts: [],
  confusingConcepts: [],
});

const normalizeStringList = (value) => {
  if (Array.isArray(value)) {
    return [...new Set(value.map((item) => `${item ?? ''}`.trim()).filter(Boolean))];
  }

  if (typeof value === 'string') {
    return [...new Set(
      value
        .split(/[\n,，;；、]/)
        .map((item) => item.trim())
        .filter(Boolean),
    )];
  }

  return [];
};

export const normalizePreferredDepth = (value) => {
  const text = `${value ?? ''}`.trim();
  if (text === '快速' || text === '简要') {
    return '速览';
  }
  if (text === '深度' || text === '深入') {
    return '深入';
  }
  return BACKGROUND_DEPTH_OPTIONS.includes(text) ? text : '标准';
};

export const normalizeReaderProfile = (value, fallbackKnowledgeLevel = '一般') => {
  const profile = value && typeof value === 'object' ? value : {};
  return {
    selfAssessedFamiliarity: normalizeKnowledgeLevel(
      profile.selfAssessedFamiliarity || profile.user_knowledge_level || fallbackKnowledgeLevel,
    ),
    preferredDepth: normalizePreferredDepth(profile.preferredDepth),
    learningGoal: `${profile.learningGoal ?? ''}`.trim(),
    knownConcepts: normalizeStringList(profile.knownConcepts),
    confusingConcepts: normalizeStringList(profile.confusingConcepts),
  };
};

export const summarizeReaderProfile = (profile) => {
  const normalized = normalizeReaderProfile(profile);
  return [
    `自评熟悉度：${normalized.selfAssessedFamiliarity}`,
    `补课深度：${normalized.preferredDepth}`,
    normalized.learningGoal ? `目标：${normalized.learningGoal}` : '',
    normalized.knownConcepts.length > 0 ? `已掌握：${normalized.knownConcepts.join('、')}` : '',
    normalized.confusingConcepts.length > 0 ? `卡点：${normalized.confusingConcepts.join('、')}` : '',
  ].filter(Boolean);
};

export const normalizeGraph = (data) => {
  const nodes = Array.isArray(data?.graph?.nodes) ? data.graph.nodes : [];
  const links = Array.isArray(data?.graph?.links) ? data.graph.links : [];
  const edges = Array.isArray(data?.graph?.edges) ? data.graph.edges : [];

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
    links: (links.length > 0 ? links : edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      relation: edge.type || 'prerequisite',
      label: edge.type === 'prerequisite' ? '前置' : edge.type || 'related',
    }))).map((link) => ({
      source: link.source,
      target: link.target,
      relation: link.relation || 'related',
      label: link.label || link.relation || 'related',
    })),
    edges: edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      type: edge.type || 'prerequisite',
      sourceIds: Array.isArray(edge.sourceIds) ? edge.sourceIds : [],
      confidenceReason: edge.confidenceReason || '',
    })),
  };
};

export const resolveLearningPathSections = (data) => {
  const sections = Array.isArray(data?.learning_path_sections) ? data.learning_path_sections : [];
  if (sections.length > 0) {
    return sortSectionsByPrerequisites(data, sections
      .map((section) => ({
        key: section.key || 'custom',
        title: section.title || '学习路径',
        items: Array.isArray(section.items) ? section.items : [],
      }))
      .filter((section) => section.items.length > 0));
  }

  const learningPath = Array.isArray(data?.learning_path) ? data.learning_path : [];
  if (learningPath.length === 0) {
    return [];
  }

  return sortSectionsByPrerequisites(data, [{
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
  }]);
};

const getConceptIds = (item) => (Array.isArray(item?.conceptIds) ? item.conceptIds : [])
  .map((conceptId) => `${conceptId}`.trim())
  .filter(Boolean);

const buildNodeLabelMap = (data) => new Map(
  (Array.isArray(data?.graph?.nodes) ? data.graph.nodes : [])
    .filter((node) => node?.id)
    .map((node) => [node.id, node.label || node.name || node.id]),
);

const getPrerequisiteEdges = (data, itemByConcept) => {
  const graphEdges = Array.isArray(data?.graph?.edges) ? data.graph.edges : [];
  const graphLinks = Array.isArray(data?.graph?.links) ? data.graph.links : [];
  const candidates = graphEdges.length > 0
    ? graphEdges
    : graphLinks.map((link) => ({ ...link, type: link.relation }));

  const validEdges = [];
  const seen = new Set();
  candidates.forEach((edge) => {
    const source = `${edge?.source ?? ''}`.trim();
    const target = `${edge?.target ?? ''}`.trim();
    const type = `${edge?.type ?? edge?.relation ?? ''}`.trim();
    const key = `${source}->${target}`;
    if (type !== 'prerequisite' || !source || !target || source === target || seen.has(key)) {
      return;
    }
    if (!itemByConcept.has(source) || !itemByConcept.has(target)) {
      return;
    }
    seen.add(key);
    validEdges.push({
      source,
      target,
      sourceIds: Array.isArray(edge.sourceIds) ? edge.sourceIds : [],
      confidenceReason: edge.confidenceReason || '',
    });
  });
  return validEdges;
};

const topologicalItemOrder = (items, prerequisiteEdges) => {
  if (items.length <= 1 || prerequisiteEdges.length === 0) {
    return items;
  }

  const itemIndex = new Map(items.map((item, index) => [item, index]));
  const outgoing = new Map(items.map((item) => [item, []]));
  const indegree = new Map(items.map((item) => [item, 0]));

  prerequisiteEdges.forEach((edge) => {
    const sourceItem = edge.sourceItem;
    const targetItem = edge.targetItem;
    if (!sourceItem || !targetItem || sourceItem === targetItem) {
      return;
    }
    outgoing.get(sourceItem).push(targetItem);
    indegree.set(targetItem, (indegree.get(targetItem) || 0) + 1);
  });

  const ready = items.filter((item) => (indegree.get(item) || 0) === 0);
  const sorted = [];
  while (ready.length > 0) {
    ready.sort((a, b) => itemIndex.get(a) - itemIndex.get(b));
    const item = ready.shift();
    sorted.push(item);
    outgoing.get(item).forEach((nextItem) => {
      indegree.set(nextItem, (indegree.get(nextItem) || 0) - 1);
      if (indegree.get(nextItem) === 0) {
        ready.push(nextItem);
      }
    });
  }

  return sorted.length === items.length ? sorted : items;
};

const sortSectionsByPrerequisites = (data, sections) => {
  const allItems = sections.flatMap((section) => section.items);
  if (allItems.length <= 1) {
    return sections;
  }

  const itemByConcept = new Map();
  allItems.forEach((item) => {
    getConceptIds(item).forEach((conceptId) => {
      if (!itemByConcept.has(conceptId)) {
        itemByConcept.set(conceptId, item);
      }
    });
  });

  const prerequisiteEdges = getPrerequisiteEdges(data, itemByConcept).map((edge) => ({
    ...edge,
    sourceItem: itemByConcept.get(edge.source),
    targetItem: itemByConcept.get(edge.target),
  }));
  if (prerequisiteEdges.length === 0) {
    return sections;
  }

  const nodeLabels = buildNodeLabelMap(data);
  const sortedItems = topologicalItemOrder(allItems, prerequisiteEdges);
  const rank = new Map(sortedItems.map((item, index) => [item, index]));
  const outgoingByItem = new Map();
  prerequisiteEdges.forEach((edge) => {
    const current = outgoingByItem.get(edge.sourceItem) || [];
    current.push({
      target: nodeLabels.get(edge.target) || edge.target,
      sourceIds: edge.sourceIds,
      confidenceReason: edge.confidenceReason,
    });
    outgoingByItem.set(edge.sourceItem, current);
  });

  return sections.map((section) => ({
    ...section,
    items: [...section.items]
      .sort((a, b) => (rank.get(a) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b) ?? Number.MAX_SAFE_INTEGER))
      .map((item) => ({
        ...item,
        prerequisiteEdges: outgoingByItem.get(item) || [],
      })),
  }));
};

export const createGenerateHandler = (onGenerate, readerProfile) => () =>
  onGenerate?.(normalizeReaderProfile(readerProfile));

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
  const normalizedReaderProfile = normalizeReaderProfile(
    data?.reader_profile,
    knowledgeLevel || data?.user_knowledge_level,
  );
  return {
    selectedKnowledgeLevel: normalizeKnowledgeLevel(knowledgeLevel || data?.user_knowledge_level),
    displayedKnowledgeLevel: data?.user_knowledge_level || normalizeKnowledgeLevel(knowledgeLevel),
    readerProfileSummary: summarizeReaderProfile(normalizedReaderProfile),
    readerProfile: normalizedReaderProfile,
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
