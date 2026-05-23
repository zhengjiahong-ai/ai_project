import assert from 'node:assert/strict';

import {
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
