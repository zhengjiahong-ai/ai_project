import assert from 'node:assert/strict';

import {
  buildAgentComparisonArtifact,
  buildAgentEvidenceArtifact,
  buildAgentReportArtifact,
  buildDeconstructionArtifact,
  buildTranslationArtifact,
  createInsightArtifact,
  normalizeInsightArtifact,
  normalizeInsightArtifacts,
  updateInsightArtifact,
} from './artifactModel.js';

const run = async () => {
  const artifact = createInsightArtifact({
    kind: 'chat-answer',
    title: '实验设计局限',
    summary: '当前论文的实验覆盖仍不完整。',
    content: '完整内容',
    tags: ['analysis', '', 'limitations'],
    pageIndex: 2,
    pinned: true,
  });

  assert.equal(artifact.kind, 'chat-answer');
  assert.equal(artifact.title, '实验设计局限');
  assert.deepEqual(artifact.tags, ['analysis', 'limitations']);
  assert.equal(artifact.pageIndex, 2);
  assert.equal(artifact.pinned, true);
  assert.equal(artifact.lane, 'inbox');
  assert.equal(artifact.pdfId, null);
  assert.equal(artifact.sourceId, null);
  assert.equal(artifact.taskId, null);
  assert.equal(artifact.projectId, null);

  const translation = buildTranslationArtifact({
    pdfId: 'paper-1',
    pdfFileName: 'paper.pdf',
    pageIndex: 2,
    translatedText: '翻译后的正文',
  });
  assert.equal(translation.kind, 'translation-page');
  assert.equal(translation.title, 'paper.pdf · 第 3 页译文');
  assert.equal(translation.content, '翻译后的正文');
  assert.equal(translation.pdfId, 'paper-1');
  assert.equal(translation.pageIndex, 2);
  assert.equal(buildTranslationArtifact({ pdfId: 'paper-1', translatedText: '  ' }), null);

  const deconstruction = buildDeconstructionArtifact({
    pdfId: 'paper-1',
    sectionId: 'methods',
    sectionLabel: '方法',
    content: '方法章节摘要',
  });
  assert.equal(deconstruction.kind, 'paper-section');
  assert.equal(deconstruction.title, '篇章解构 · 方法');
  assert.equal(deconstruction.sectionId, 'methods');
  assert.deepEqual(deconstruction.tags, ['deconstruction', 'section', 'methods']);

  const report = buildAgentReportArtifact({
    activePdfId: 'paper-1',
    projectId: 'project-1',
    taskId: 'task-1',
    projectTitle: '对比研究',
    draftReport: '# 研究结论\n结论正文',
  });
  assert.equal(report.kind, 'agent-report');
  assert.equal(report.pdfId, 'paper-1');
  assert.equal(report.projectId, 'project-1');
  assert.equal(report.taskId, 'task-1');
  assert.equal(report.content, '# 研究结论\n结论正文');

  const comparison = buildAgentComparisonArtifact({
    activePdfId: 'paper-1',
    projectId: 'project-1',
    taskId: 'task-1',
    projectTitle: '对比研究',
    comparisonTable: {
      columns: ['论文', '方法'],
      rows: [['Paper A', 'A | B'], ['Paper B', '']],
    },
  });
  assert.equal(comparison.kind, 'agent-comparison');
  assert.equal(
    comparison.content,
    '| 论文 | 方法 |\n| --- | --- |\n| Paper A | A \\| B |\n| Paper B | - |',
  );

  const evidence = buildAgentEvidenceArtifact({
    activePdfId: 'paper-1',
    projectId: 'project-1',
    taskId: 'task-1',
    evidence: {
      pdfId: 'paper-2',
      sourceId: 'source-1',
      sourceType: 'rag',
      text: '关键证据文本',
      pageIndex: 4,
      sectionId: 'results',
    },
  });
  assert.equal(evidence.kind, 'agent-evidence');
  assert.equal(evidence.pdfId, 'paper-2');
  assert.equal(evidence.sourceId, 'source-1');
  assert.equal(evidence.pageIndex, 4);
  assert.equal(evidence.sectionId, 'results');
  assert.equal(evidence.projectId, 'project-1');
  assert.equal(evidence.taskId, 'task-1');
  assert.equal(buildAgentEvidenceArtifact({ activePdfId: '', evidence: { text: '证据' } }), null);

  const normalized = normalizeInsightArtifact({
    id: 'legacy-1',
    kind: 'finding',
    title: '  研究发现  ',
    summary: '  摘要  ',
    content: '  正文  ',
    isPinned: true,
  });

  assert.equal(normalized.artifactId, 'legacy-1');
  assert.equal(normalized.title, '研究发现');
  assert.equal(normalized.summary, '摘要');
  assert.equal(normalized.pinned, true);
  assert.equal(normalized.pdfId, null);

  const updated = updateInsightArtifact(normalized, {
    title: '更新后的研究发现',
    lane: 'evidence',
    userNote: '需要回头核对实验设置。',
  });

  assert.equal(updated.title, '更新后的研究发现');
  assert.equal(updated.lane, 'evidence');
  assert.equal(updated.userNote, '需要回头核对实验设置。');
  assert.equal(updated.artifactId, normalized.artifactId);
  assert.equal(updated.createdAt, normalized.createdAt);

  const ordered = normalizeInsightArtifacts([
    { artifactId: 'b', title: '普通卡片', summary: '2', createdAt: 2 },
    { artifactId: 'a', title: '置顶卡片', summary: '1', pinned: true, createdAt: 1 },
  ]);

  assert.deepEqual(ordered.map((item) => item.artifactId), ['a', 'b']);

  console.log('artifact model smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
