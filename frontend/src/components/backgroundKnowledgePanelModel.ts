export const KNOWLEDGE_LEVEL_OPTIONS: string[] = ['入门', '一般', '进阶'];
export const BACKGROUND_DEPTH_OPTIONS: string[] = ['速览', '标准', '深入'];
export const BACKGROUND_GOAL_OPTIONS: string[] = ['扫清概念障碍', '理解方法链路', '为批判阅读做准备'];

const STAGE_META: Record<string, { title: string; color: string }> = {
  foundation: { title: '基础概念', color: '#0ea5e9' },
  method_prerequisite: { title: '方法前置', color: '#14b8a6' },
  experiment_understanding: { title: '实验理解', color: '#22c55e' },
  critical_perspective: { title: '批判视角', color: '#f59e0b' },
};

interface ProvenanceMetaEntry {
  label: string;
  tone: string;
}

const PROVENANCE_META: Record<string, ProvenanceMetaEntry> = {
  current_paper_supported: { label: '当前论文支持', tone: 'evidence' },
  library_paper_supported: { label: '库内论文支持', tone: 'evidence' },
  model_inference: { label: '模型推断', tone: 'inference' },
  external_supported: { label: '外部证据支持', tone: 'external' },
  unknown: { label: '来源未标注', tone: 'unknown' },
};

export const getProvenanceMeta = (value: string): ProvenanceMetaEntry => PROVENANCE_META[value] || PROVENANCE_META.unknown;

interface ProvenanceCounts {
  total: number;
  currentPaperSupported: number;
  libraryPaperSupported: number;
  modelInference: number;
  externalSupported: number;
  supportedRatio: number;
}

const normalizeProvenanceCounts = (value: unknown): ProvenanceCounts => {
  const counts = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  const total: number = Number.isInteger(counts.total) && (counts.total as number) >= 0 ? (counts.total as number) : 0;
  const currentPaperSupported: number = Number.isInteger(counts.currentPaperSupported) ? (counts.currentPaperSupported as number) : 0;
  const libraryPaperSupported: number = Number.isInteger(counts.libraryPaperSupported) ? (counts.libraryPaperSupported as number) : 0;
  const modelInference: number = Number.isInteger(counts.modelInference) ? (counts.modelInference as number) : 0;
  const externalSupported: number = Number.isInteger(counts.externalSupported) ? (counts.externalSupported as number) : 0;
  const supportedRatio: number = typeof counts.supportedRatio === 'number'
    ? Math.max(0, Math.min(1, counts.supportedRatio as number))
    : total > 0 ? (currentPaperSupported + libraryPaperSupported + externalSupported) / total : 0;
  return { total, currentPaperSupported, libraryPaperSupported, modelInference, externalSupported, supportedRatio };
};

interface ProvenanceSummary {
  nodes: ProvenanceCounts;
  edges: ProvenanceCounts;
}

export const normalizeProvenanceSummary = (data: Record<string, unknown> | null | undefined): ProvenanceSummary | null => {
  if (!data?.provenanceSummary || typeof data.provenanceSummary !== 'object') {
    return null;
  }
  const ps = data.provenanceSummary as Record<string, unknown>;
  return {
    nodes: normalizeProvenanceCounts(ps.nodes),
    edges: normalizeProvenanceCounts(ps.edges),
  };
};

export const normalizeKnowledgeLevel = (value: unknown): string => {
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
  knownConcepts: [] as string[],
  confusingConcepts: [] as string[],
});

const normalizeStringList = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return [...new Set(value.map((item: unknown) => `${item ?? ''}`.trim()).filter(Boolean))];
  }

  if (typeof value === 'string') {
    return [...new Set(
      value
        .split(/[\n,，;；、]/)
        .map((item: string) => item.trim())
        .filter(Boolean),
    )];
  }

  return [];
};

export const normalizePreferredDepth = (value: unknown): string => {
  const text = `${value ?? ''}`.trim();
  if (text === '快速' || text === '简要') {
    return '速览';
  }
  if (text === '深度' || text === '深入') {
    return '深入';
  }
  return BACKGROUND_DEPTH_OPTIONS.includes(text) ? text : '标准';
};

interface ReaderProfileInput {
  selfAssessedFamiliarity?: unknown;
  user_knowledge_level?: unknown;
  preferredDepth?: unknown;
  learningGoal?: unknown;
  knownConcepts?: unknown;
  confusingConcepts?: unknown;
}

export const normalizeReaderProfile = (value: ReaderProfileInput | null | undefined, fallbackKnowledgeLevel: string = '一般') => {
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

export const summarizeReaderProfile = (profile: ReaderProfileInput | null | undefined): string[] => {
  const normalized = normalizeReaderProfile(profile);
  return [
    `自评熟悉度：${normalized.selfAssessedFamiliarity}`,
    `补课深度：${normalized.preferredDepth}`,
    normalized.learningGoal ? `目标：${normalized.learningGoal}` : '',
    normalized.knownConcepts.length > 0 ? `已掌握：${normalized.knownConcepts.join('、')}` : '',
    normalized.confusingConcepts.length > 0 ? `卡点：${normalized.confusingConcepts.join('、')}` : '',
  ].filter(Boolean) as string[];
};

interface GraphData {
  graph?: {
    nodes?: unknown[];
    links?: unknown[];
    edges?: unknown[];
  };
  learning_path_sections?: unknown[];
  learning_path?: unknown[];
  sourceCoverage?: { uncoveredConceptIds?: string[] };
  background_knowledge?: unknown[];
  rag_sources?: unknown[];
  confidence?: number;
  reader_profile?: unknown;
  user_knowledge_level?: unknown;
  neo4j?: { enabled?: boolean; message?: string; status?: string };
  provenanceSummary?: unknown;
  [key: string]: unknown;
}

interface GraphNode {
  id?: string;
  label?: string;
  name?: string;
  type?: string;
  level?: string;
  stage?: string;
  stageLabel?: string;
  summary?: string;
  why?: string;
  sourceIds?: string[];
  confidence?: number;
  provenanceStatus?: string;
  confidenceReason?: string;
}

interface GraphLink {
  source: string;
  target: string;
  relation?: string;
  type?: string;
  label?: string;
  sourceIds?: string[];
  provenanceStatus?: string;
  confidence?: number;
  confidenceReason?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type?: string;
  sourceIds?: string[];
  provenanceStatus?: string;
  confidence?: number;
  confidenceReason?: string;
}

export const normalizeGraph = (data: GraphData | null | undefined) => {
  const nodes = (Array.isArray(data?.graph?.nodes) ? data.graph.nodes : []) as GraphNode[];
  const links = (Array.isArray(data?.graph?.links) ? data.graph.links : []) as GraphLink[];
  const edges = (Array.isArray(data?.graph?.edges) ? data.graph.edges : []) as GraphEdge[];

  return {
    nodes: nodes.map((node, index) => {
      const stage: string = node.stage || 'foundation';
      const stageMeta = STAGE_META[stage] || STAGE_META.foundation;
      const confidence: number | null = typeof node.confidence === 'number' ? node.confidence : null;

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
        provenanceStatus: node.provenanceStatus || 'unknown',
        provenanceLabel: getProvenanceMeta(node.provenanceStatus || 'unknown').label,
        confidenceReason: node.confidenceReason || '',
        val: node.type === 'paper' ? 14 : confidence && confidence >= 0.8 ? 9 : 7,
        color: node.type === 'paper' ? '#4D0099' : stageMeta.color,
      };
    }),
    links: (links.length > 0 ? links : edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      relation: edge.type || 'prerequisite',
      label: edge.type === 'prerequisite' ? '前置' : edge.type || 'related',
    }) as GraphLink)).map((link) => ({
      source: link.source,
      target: link.target,
      relation: (link as GraphLink).relation || (link as { relation?: string }).relation || 'related',
      label: (link as GraphLink).label || (link as { relation?: string; label?: string }).relation || (link as { label?: string }).label || 'related',
      sourceIds: Array.isArray((link as GraphLink).sourceIds) ? (link as GraphLink).sourceIds : [],
      provenanceStatus: (link as GraphLink).provenanceStatus || 'unknown',
      provenanceLabel: getProvenanceMeta((link as GraphLink).provenanceStatus || 'unknown').label,
      confidence: typeof (link as GraphLink).confidence === 'number' ? (link as GraphLink).confidence : null,
      confidenceReason: (link as GraphLink).confidenceReason || '',
    })),
    edges: edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      type: edge.type || 'prerequisite',
      sourceIds: Array.isArray(edge.sourceIds) ? edge.sourceIds : [],
      confidenceReason: edge.confidenceReason || '',
      provenanceStatus: edge.provenanceStatus || 'unknown',
      provenanceLabel: getProvenanceMeta(edge.provenanceStatus || 'unknown').label,
      confidence: typeof edge.confidence === 'number' ? edge.confidence : null,
    })),
  };
};

interface LearningPathSection {
  key?: string;
  title?: string;
  items?: LearningPathItem[];
}

interface LearningPathItem {
  title: string;
  label?: string;
  goal?: string;
  summary?: string;
  conceptIds?: string[];
  sourceIds?: string[];
  stage?: string;
  stageLabel?: string;
  step?: number;
}

export const resolveLearningPathSections = (data: GraphData | null | undefined) => {
  const sections = (Array.isArray(data?.learning_path_sections) ? data.learning_path_sections : []) as LearningPathSection[];
  if (sections.length > 0) {
    return sortSectionsByPrerequisites(data, sections
      .map((section) => ({
        key: section.key || 'custom',
        title: section.title || '学习路径',
        items: (Array.isArray(section.items) ? section.items : []) as LearningPathItem[],
      }))
      .filter((section) => section.items.length > 0));
  }

  const learningPath = (Array.isArray(data?.learning_path) ? data.learning_path : []) as LearningPathItem[];
  if (learningPath.length === 0) {
    return [];
  }

  return sortSectionsByPrerequisites(data, [{
    key: 'legacy',
    title: '学习路径',
    items: learningPath.map((step, index) => ({
      title: (step.title || step.label || `第 ${index + 1} 步`) as string,
      goal: step.goal || step.summary || '',
      conceptIds: Array.isArray(step.conceptIds) ? step.conceptIds : [],
      sourceIds: Array.isArray(step.sourceIds) ? step.sourceIds : [],
      stage: step.stage || 'foundation',
      stageLabel: step.stageLabel || '学习路径',
      step: step.step || index + 1,
    })),
  }]);
};

const getConceptIds = (item: LearningPathItem | null | undefined): string[] => (Array.isArray(item?.conceptIds) ? item.conceptIds : [])
  .map((conceptId: string) => `${conceptId}`.trim())
  .filter(Boolean);

const buildNodeLabelMap = (data: GraphData | null | undefined): Map<string, string> => new Map(
  ((Array.isArray(data?.graph?.nodes) ? data.graph.nodes : []) as GraphNode[])
    .filter((node) => node?.id)
    .map((node) => [node.id as string, (node.label || node.name || node.id) as string]),
);

interface PrerequisiteEdge {
  source: string;
  target: string;
  sourceIds: string[];
  confidenceReason: string;
  provenanceStatus: string;
  confidence: number | null;
}

const getPrerequisiteEdges = (data: GraphData | null | undefined, itemByConcept: Map<string, LearningPathItem>): PrerequisiteEdge[] => {
  const graphEdges = (Array.isArray(data?.graph?.edges) ? data.graph.edges : []) as GraphEdge[];
  const graphLinks = (Array.isArray(data?.graph?.links) ? data.graph.links : []) as GraphLink[];
  const candidates = graphEdges.length > 0
    ? graphEdges
    : graphLinks.map((link) => ({ ...link, type: link.relation }));

  const validEdges: PrerequisiteEdge[] = [];
  const seen = new Set<string>();
  candidates.forEach((edge) => {
    const source = `${edge?.source ?? ''}`.trim();
    const target = `${edge?.target ?? ''}`.trim();
    const type = `${(edge as GraphEdge)?.type ?? (edge as GraphLink)?.relation ?? ''}`.trim();
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
      provenanceStatus: edge.provenanceStatus || 'unknown',
      confidence: typeof edge.confidence === 'number' ? edge.confidence : null,
    });
  });
  return validEdges;
};

interface TopologicalEdge extends PrerequisiteEdge {
  sourceItem: unknown;
  targetItem: unknown;
}

const topologicalItemOrder = (items: unknown[], prerequisiteEdges: TopologicalEdge[]): unknown[] => {
  if (items.length <= 1 || prerequisiteEdges.length === 0) {
    return items;
  }

  const itemIndex = new Map<unknown, number>(items.map((item, index) => [item, index]));
  const outgoing = new Map<unknown, unknown[]>(items.map((item) => [item, []]));
  const indegree = new Map<unknown, number>(items.map((item) => [item, 0]));

  prerequisiteEdges.forEach((edge) => {
    const sourceItem = edge.sourceItem;
    const targetItem = edge.targetItem;
    if (!sourceItem || !targetItem || sourceItem === targetItem) {
      return;
    }
    (outgoing.get(sourceItem) as unknown[]).push(targetItem);
    indegree.set(targetItem, (indegree.get(targetItem) || 0) + 1);
  });

  const ready = items.filter((item) => (indegree.get(item) || 0) === 0);
  const sorted: unknown[] = [];
  while (ready.length > 0) {
    ready.sort((a, b) => (itemIndex.get(a) ?? 0) - (itemIndex.get(b) ?? 0));
    const item = ready.shift() as unknown;
    sorted.push(item);
    (outgoing.get(item) as unknown[]).forEach((nextItem) => {
      indegree.set(nextItem, (indegree.get(nextItem) || 0) - 1);
      if (indegree.get(nextItem) === 0) {
        ready.push(nextItem);
      }
    });
  }

  return sorted.length === items.length ? sorted : items;
};

interface SectionWithItems {
  key: string;
  title: string;
  items: LearningPathItem[];
}

const sortSectionsByPrerequisites = (data: GraphData | null | undefined, sections: SectionWithItems[]): SectionWithItems[] => {
  const allItems: LearningPathItem[] = sections.flatMap((section) => section.items);
  if (allItems.length <= 1) {
    return sections;
  }

  const itemByConcept = new Map<string, LearningPathItem>();
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
  })) as TopologicalEdge[];
  if (prerequisiteEdges.length === 0) {
    return sections;
  }

  const nodeLabels = buildNodeLabelMap(data);
  const sortedItems = topologicalItemOrder(allItems, prerequisiteEdges);
  const rank = new Map<unknown, number>(sortedItems.map((item, index) => [item, index]));
  const outgoingByItem = new Map<unknown, Record<string, unknown>[]>();
  prerequisiteEdges.forEach((edge) => {
    const current = outgoingByItem.get(edge.sourceItem) || [];
    current.push({
      target: nodeLabels.get(edge.target) || edge.target,
      sourceIds: edge.sourceIds,
      confidenceReason: edge.confidenceReason,
      ...(edge.provenanceStatus !== 'unknown' ? { provenanceStatus: edge.provenanceStatus } : {}),
      ...(edge.confidence !== null ? { confidence: edge.confidence } : {}),
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

// 背景补课是同步单请求：后端要先抽取前置概念、再判定它们之间的依赖关系，两轮都
// 要调模型。实测冷跑 194 秒，浏览器里带上篇章结构时更久，而等待期原本只有一个
// 转圈图标，用户分不清“正在算”和“卡死了”。给真实已耗时比画一个拿不到的进度
// 条诚实。超过一分钟才显示分，避免“0 分 5 秒”这种噪音。
export const formatElapsedDuration = (totalSeconds: number): string => {
  const seconds = Number.isFinite(totalSeconds) && totalSeconds > 0 ? Math.floor(totalSeconds) : 0;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes > 0 ? `${minutes} 分 ${rest} 秒` : `${rest} 秒`;
};

export const createGenerateHandler = (onGenerate: ((profile: ReturnType<typeof normalizeReaderProfile>) => void) | null | undefined, readerProfile: ReaderProfileInput | null | undefined) => () =>
  onGenerate?.(normalizeReaderProfile(readerProfile));

export const getUncoveredNodeLabels = (data: GraphData | null | undefined): string[] => {
  const sourceCoverage = data?.sourceCoverage;
  if (!Array.isArray(sourceCoverage?.uncoveredConceptIds)) {
    return [];
  }
  const nodes = (Array.isArray(data?.graph?.nodes) ? data.graph.nodes : []) as GraphNode[];
  const labelMap = new Map<string, string>(
    nodes.map((node) => [node.id as string, (node.label || node.id) as string]),
  );
  return sourceCoverage.uncoveredConceptIds.map((nodeId: string) => labelMap.get(nodeId) || nodeId);
};

export const createBackgroundKnowledgeSnapshot = (data: GraphData | null | undefined, knowledgeLevel: string = '一般') => {
  const sections = resolveLearningPathSections(data);
  const normalizedReaderProfile = normalizeReaderProfile(
    data?.reader_profile as ReaderProfileInput | undefined,
    knowledgeLevel || (data?.user_knowledge_level as string),
  );
  return {
    selectedKnowledgeLevel: normalizeKnowledgeLevel(knowledgeLevel || data?.user_knowledge_level),
    displayedKnowledgeLevel: (data?.user_knowledge_level as string) || normalizeKnowledgeLevel(knowledgeLevel),
    readerProfileSummary: summarizeReaderProfile(normalizedReaderProfile),
    readerProfile: normalizedReaderProfile,
    graphNodeCount: normalizeGraph(data).nodes.length,
    graphLinkCount: normalizeGraph(data).links.length,
    learningSectionTitles: sections.map((section) => section.title),
    learningItems: sections.flatMap((section) => section.items.map((item) => item.title)),
    backgroundItems: Array.isArray(data?.background_knowledge) ? data.background_knowledge : [],
    ragSourceIds: (Array.isArray(data?.rag_sources) ? data.rag_sources : []).map((source: unknown) => (source as { id?: string; sourceId?: string }).id || (source as { id?: string; sourceId?: string }).sourceId),
    hasConfidence: typeof data?.confidence === 'number',
    hasSourceCoverage: Boolean(data?.sourceCoverage),
    provenanceSummary: normalizeProvenanceSummary(data),
    uncoveredNodeLabels: getUncoveredNodeLabels(data),
    neo4jMessage: data?.neo4j?.enabled
      ? (data?.neo4j?.message || data?.neo4j?.status || '')
      : '未配置 Neo4j，已使用接口返回的图谱结果。',
  };
};
