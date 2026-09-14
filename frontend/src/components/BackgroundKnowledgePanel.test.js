import assert from 'node:assert/strict';

import {
  createBackgroundKnowledgeSnapshot,
  createDefaultReaderProfile,
  createGenerateHandler,
  formatElapsedDuration,
  getProvenanceMeta,
  normalizeGraph,
  normalizeKnowledgeLevel,
  normalizeProvenanceSummary,
  normalizeReaderProfile,
  resolveGraphTitle,
  resolveLearningPathSections,
} from './backgroundKnowledgePanelModel.ts';


const run = async () => {
  // 等待耗时展示：背景补课实测冷跑三分钟起，等待期原本只有一个转圈图标，
  // 用户分不清“正在算”和“卡死了”。不满一分钟时不显示分，避免“0 分 5 秒”。
  assert.equal(formatElapsedDuration(0), '0 秒');
  assert.equal(formatElapsedDuration(59), '59 秒');
  assert.equal(formatElapsedDuration(60), '1 分 0 秒');
  assert.equal(formatElapsedDuration(194), '3 分 14 秒');
  assert.equal(formatElapsedDuration(900), '15 分 0 秒');
  // 非法输入不能让面板崩在 NaN 上。
  assert.equal(formatElapsedDuration(Number.NaN), '0 秒');
  assert.equal(formatElapsedDuration(-5), '0 秒');

  // 图谱卡片标题：canvas 不绘制节点文字（没传 nodeCanvasObject），这行 h3 是用户
  // 唯一能看到“这是哪篇论文的图谱”的地方。后端把根节点 label 解析成论文标题，
  // 而 paper_topic 仍是研究问题（要继续喂模型），所以标题必须优先取根节点。
  assert.equal(
    resolveGraphTitle({
      paper_topic: 'How to efficiently reconstruct 3D scenes from sparse multi-view images',
      graph: {
        nodes: [
          { id: 'current-paper', label: 'MVSplat: Efficient 3D Gaussian Splatting', type: 'paper' },
          { id: 'concept-1', label: '三维高斯泼溅' },
        ],
        links: [],
      },
    }),
    'MVSplat: Efficient 3D Gaussian Splatting',
  );
  // 没有根节点时回落 paper_topic，再回落占位文案：标题不能是空的。
  assert.equal(resolveGraphTitle({ paper_topic: 'RAG', graph: { nodes: [], links: [] } }), 'RAG');
  assert.equal(resolveGraphTitle({ graph: { nodes: [], links: [] } }), '当前论文');
  assert.equal(resolveGraphTitle(null), '当前论文');
  // 根节点缺 label（IndexedDB 里的旧图谱就是这种形状）时不能把技术 id 当标题显示，
  // 只认 label / name 两个真标题来源；根节点识别与后端一致，认 id 也认 type=paper。
  assert.equal(
    resolveGraphTitle({
      paper_topic: 'RAG',
      graph: { nodes: [{ id: 'current-paper', type: 'paper' }], links: [] },
    }),
    'RAG',
  );
  assert.equal(
    resolveGraphTitle({
      graph: { nodes: [{ id: 'root-1', name: 'MVSplat', type: 'paper' }], links: [] },
    }),
    'MVSplat',
  );

  assert.equal(normalizeKnowledgeLevel('普通/一般'), '一般');
  assert.equal(normalizeKnowledgeLevel('进阶'), '进阶');
  assert.equal(normalizeKnowledgeLevel('unknown'), '一般');
  assert.deepEqual(createDefaultReaderProfile(), {
    selfAssessedFamiliarity: '一般',
    preferredDepth: '标准',
    learningGoal: '',
    knownConcepts: [],
    confusingConcepts: [],
  });
  assert.deepEqual(normalizeReaderProfile({
    selfAssessedFamiliarity: '普通/一般',
    preferredDepth: '深度',
    learningGoal: '理解方法链路',
    knownConcepts: 'Transformer，检索增强生成',
    confusingConcepts: ['图检索'],
  }), {
    selfAssessedFamiliarity: '一般',
    preferredDepth: '深入',
    learningGoal: '理解方法链路',
    knownConcepts: ['Transformer', '检索增强生成'],
    confusingConcepts: ['图检索'],
  });

  let generatedProfile = null;
  createGenerateHandler((profile) => {
    generatedProfile = profile;
  }, { selfAssessedFamiliarity: '普通/一般', preferredDepth: '标准' })();
  assert.deepEqual(generatedProfile, {
    selfAssessedFamiliarity: '一般',
    preferredDepth: '标准',
    learningGoal: '',
    knownConcepts: [],
    confusingConcepts: [],
  });

  const legacyData = {
    paper_topic: 'AcademicRAG',
    user_knowledge_level: '普通/一般',
    reader_profile: {
      selfAssessedFamiliarity: '一般',
      preferredDepth: '标准',
      learningGoal: '扫清概念障碍',
      knownConcepts: ['Transformer'],
      confusingConcepts: ['RAG'],
    },
    graph: {
      nodes: [
        { id: 'current-paper', label: 'AcademicRAG', type: 'paper', level: 'target' },
        { id: 'rag', label: 'RAG', stage: 'foundation', summary: 'Retrieval augmented generation' },
      ],
      links: [{ source: 'rag', target: 'current-paper', relation: 'prerequisite', label: '前置' }],
    },
    learning_path: [
      { step: 1, title: 'RAG', goal: '先理解检索增强生成。' },
    ],
    background_knowledge: ['RAG'],
    rag_sources: [{ id: 'source-1', sourceId: 'source-1', text: 'RAG source text' }],
    neo4j: { enabled: false, status: 'skipped' },
  };

  const normalizedLegacyGraph = normalizeGraph(legacyData);
  assert.equal(normalizedLegacyGraph.nodes[1].stageLabel, '基础概念');
  assert.equal(normalizedLegacyGraph.nodes[1].provenanceStatus, 'unknown');
  assert.equal(getProvenanceMeta('unknown').label, '来源未标注');

  const legacySections = resolveLearningPathSections(legacyData);
  assert.equal(legacySections.length, 1);
  assert.equal(legacySections[0].title, '学习路径');

  const legacySnapshot = createBackgroundKnowledgeSnapshot(legacyData, '普通/一般');
  assert.equal(legacySnapshot.selectedKnowledgeLevel, '一般');
  assert.equal(legacySnapshot.displayedKnowledgeLevel, '普通/一般');
  assert.deepEqual(legacySnapshot.readerProfileSummary, [
    '自评熟悉度：一般',
    '补课深度：标准',
    '目标：扫清概念障碍',
    '已掌握：Transformer',
    '卡点：RAG',
  ]);
  assert.deepEqual(legacySnapshot.learningSectionTitles, ['学习路径']);
  assert.deepEqual(legacySnapshot.learningItems, ['RAG']);
  assert.deepEqual(legacySnapshot.ragSourceIds, ['source-1']);
  assert.equal(legacySnapshot.hasConfidence, false);
  assert.equal(legacySnapshot.hasSourceCoverage, false);

  const structuredData = {
    paper_topic: 'AcademicRAG',
    user_knowledge_level: '进阶',
    confidence: 0.86,
    sourceCoverage: {
      totalConcepts: 3,
      conceptsWithSources: 2,
      ratio: 0.67,
      uncoveredConceptIds: ['critical-view'],
    },
    graph: {
      nodes: [
        { id: 'current-paper', label: 'AcademicRAG', type: 'paper', level: 'target', stage: 'critical_perspective' },
        {
          id: 'rag',
          label: 'RAG',
          type: 'concept',
          level: 'basic',
          stage: 'foundation',
          stageLabel: '基础概念',
          summary: '检索增强生成',
          sourceIds: ['source-1'],
          confidence: 0.82,
        },
        {
          id: 'graph-retrieval',
          label: '图检索',
          type: 'method',
          level: 'intermediate',
          stage: 'method_prerequisite',
          stageLabel: '方法前置',
          why: '理解图谱如何参与检索',
          sourceIds: ['source-2'],
          confidence: 0.8,
        },
        {
          id: 'critical-view',
          label: '局限性审视',
          type: 'concept',
          level: 'advanced',
          stage: 'critical_perspective',
          stageLabel: '批判视角',
          why: '识别方法边界',
          sourceIds: [],
          confidence: 0.55,
        },
      ],
      links: [
        { source: 'rag', target: 'graph-retrieval', relation: 'prerequisite', label: '前置' },
        { source: 'graph-retrieval', target: 'current-paper', relation: 'supports', label: '支持理解' },
      ],
    },
    learning_path_sections: [
      {
        key: 'foundation',
        title: '基础概念',
        items: [{ step: 1, title: 'RAG', goal: '先补齐 RAG 的基本定义。', stageLabel: '基础概念' }],
      },
      {
        key: 'method_prerequisite',
        title: '方法前置',
        items: [{ step: 2, title: '图检索', goal: '理解图结构在检索中的作用。', stageLabel: '方法前置' }],
      },
      {
        key: 'critical_perspective',
        title: '批判视角',
        items: [{ step: 3, title: '局限性审视', goal: '识别方法边界。', stageLabel: '批判视角' }],
      },
    ],
    background_knowledge: ['RAG', '图检索', '局限性审视'],
    rag_sources: [
      { id: 'source-1', sourceId: 'source-1', text: 'RAG source text' },
      { id: 'source-2', sourceId: 'source-2', text: 'Graph retrieval source text' },
    ],
    neo4j: { enabled: true, message: 'Knowledge graph persisted to Neo4j.' },
  };

  const structuredSections = resolveLearningPathSections(structuredData);
  assert.equal(structuredSections.length, 3);
  assert.equal(structuredSections[0].title, '基础概念');

  const structuredSnapshot = createBackgroundKnowledgeSnapshot(structuredData, '进阶');
  assert.equal(structuredSnapshot.selectedKnowledgeLevel, '进阶');
  assert.equal(structuredSnapshot.graphNodeCount, 4);
  assert.equal(structuredSnapshot.graphLinkCount, 2);
  assert.deepEqual(structuredSnapshot.learningSectionTitles, ['基础概念', '方法前置', '批判视角']);
  assert.deepEqual(structuredSnapshot.learningItems, ['RAG', '图检索', '局限性审视']);
  assert.equal(structuredSnapshot.hasConfidence, true);
  assert.equal(structuredSnapshot.hasSourceCoverage, true);
  assert.deepEqual(structuredSnapshot.uncoveredNodeLabels, ['局限性审视']);
  assert.equal(structuredSnapshot.neo4jMessage, 'Knowledge graph persisted to Neo4j.');

  const dependencyData = {
    graph: {
      nodes: [
        { id: 'current-paper', label: 'AcademicRAG', type: 'paper', stage: 'critical_perspective' },
        { id: 'rag', label: 'RAG', stage: 'foundation' },
        { id: 'graph-retrieval', label: '图检索', stage: 'method_prerequisite' },
        { id: 'critical-view', label: '局限性审视', stage: 'critical_perspective' },
      ],
      edges: [
        { source: 'rag', target: 'graph-retrieval', type: 'prerequisite', sourceIds: ['source-1'] },
        { source: 'graph-retrieval', target: 'critical-view', type: 'prerequisite', confidenceReason: '先理解图检索，再审视局限。' },
        { source: 'missing', target: 'critical-view', type: 'prerequisite' },
      ],
    },
    learning_path: [
      { step: 1, title: '局限性审视', conceptIds: ['critical-view'] },
      { step: 2, title: '图检索', conceptIds: ['graph-retrieval'] },
      { step: 3, title: 'RAG', conceptIds: ['rag'] },
    ],
  };

  const provenanceData = {
    provenanceSummary: {
      nodes: { total: 3, currentPaperSupported: 2, libraryPaperSupported: 0, modelInference: 1, externalSupported: 0, supportedRatio: 0.67 },
      edges: { total: 2, currentPaperSupported: 1, libraryPaperSupported: 0, modelInference: 1, externalSupported: 0, supportedRatio: 0.5 },
    },
    graph: {
      nodes: [{
        id: 'attention',
        label: 'Attention',
        provenanceStatus: 'current_paper_supported',
        confidence: 0.85,
        confidenceReason: '论文方法章节明确使用。',
        sourceIds: ['source-1'],
      }],
      edges: [{
        source: 'linear-algebra',
        target: 'attention',
        type: 'prerequisite',
        provenanceStatus: 'model_inference',
        confidence: 0.6,
        confidenceReason: '模型推断。',
      }],
    },
  };
  assert.deepEqual(normalizeProvenanceSummary(provenanceData), provenanceData.provenanceSummary);
  assert.equal(getProvenanceMeta('current_paper_supported').label, '当前论文支持');
  assert.equal(getProvenanceMeta('model_inference').label, '模型推断');
  // 缺陷E回归护栏：库内论文支持不得再回落到 unknown（旧表现缺这一项）。
  assert.equal(getProvenanceMeta('library_paper_supported').label, '库内论文支持');
  // 后端未给 supportedRatio 时，库内支持也计入支持率。
  assert.equal(
    normalizeProvenanceSummary({ provenanceSummary: { nodes: { total: 4, currentPaperSupported: 1, libraryPaperSupported: 1, externalSupported: 0, modelInference: 2 }, edges: { total: 0 } } }).nodes.supportedRatio,
    0.5,
  );
  const normalizedProvenanceGraph = normalizeGraph(provenanceData);
  assert.equal(normalizedProvenanceGraph.nodes[0].confidenceReason, '论文方法章节明确使用。');
  assert.equal(normalizedProvenanceGraph.edges[0].provenanceStatus, 'model_inference');
  assert.equal(normalizedProvenanceGraph.edges[0].confidence, 0.6);

  const dependencySections = resolveLearningPathSections(dependencyData);
  assert.deepEqual(
    dependencySections.flatMap((section) => section.items.map((item) => item.title)),
    ['RAG', '图检索', '局限性审视'],
  );
  assert.deepEqual(dependencySections[0].items[0].prerequisiteEdges, [
    { target: '图检索', sourceIds: ['source-1'], confidenceReason: '' },
  ]);
  assert.deepEqual(dependencySections[0].items[1].prerequisiteEdges, [
    { target: '局限性审视', sourceIds: [], confidenceReason: '先理解图检索，再审视局限。' },
  ]);

  const cyclicData = {
    graph: {
      nodes: [
        { id: 'a', label: 'A', stage: 'foundation' },
        { id: 'b', label: 'B', stage: 'foundation' },
      ],
      edges: [
        { source: 'a', target: 'b', type: 'prerequisite' },
        { source: 'b', target: 'a', type: 'prerequisite' },
      ],
    },
    learning_path: [
      { step: 1, title: 'B', conceptIds: ['b'] },
      { step: 2, title: 'A', conceptIds: ['a'] },
    ],
  };
  assert.deepEqual(
    resolveLearningPathSections(cyclicData).flatMap((section) => section.items.map((item) => item.title)),
    ['B', 'A'],
  );

  console.log('background knowledge panel model smoke tests passed');
};


run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
