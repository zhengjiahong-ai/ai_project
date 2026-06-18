import assert from 'node:assert/strict';

import {
  buildSourceLookup,
  collectSourcesByIds,
  normalizeEvidenceSources,
  normalizeSentenceReferences,
} from './evidenceCitationModel.js';

const run = async () => {
  const sources = [
    {
      sourceId: 'source-1',
      text: '第一段证据详细内容。',
      sourceType: 'current_paper',
      chunkIndex: 0,
      pageIndex: 2,
      sectionId: 'section-1',
      pdfId: 'paper-1',
    },
    { id: 'legacy-2', text: '第二段证据详细内容。', sourceType: 'library' },
    { sourceId: 'empty', text: '  ' },
  ];

  const lookup = buildSourceLookup(sources);
  assert.equal(lookup.size, 2);
  assert.equal(lookup.get('source-1').chunkIndex, 0);
  assert.equal(lookup.get('source-1').pageIndex, 2);
  assert.equal(lookup.get('source-1').sectionId, 'section-1');
  assert.equal(lookup.get('source-1').pdfId, 'paper-1');
  assert.equal(lookup.get('source-1').canJumpToSource, true);
  assert.equal(lookup.get('legacy-2').sourceType, 'library');
  assert.equal(lookup.get('legacy-2').pageIndex, null);
  assert.equal(lookup.get('legacy-2').canJumpToSource, false);

  const legacySources = normalizeEvidenceSources([
    { id: 'legacy-source', content: '旧缓存正文', pageIndex: '4', pdfId: 'paper-2' },
    { id: 'legacy-source', content: '重复来源应去重' },
    { id: 'no-page', preview: '只有摘要的旧来源' },
  ]);
  assert.equal(legacySources.length, 2);
  assert.equal(legacySources[0].sourceId, 'legacy-source');
  assert.equal(legacySources[0].text, '旧缓存正文');
  assert.equal(legacySources[0].pageIndex, 4);
  assert.equal(legacySources[0].locationLabel, 'p.5');
  assert.equal(legacySources[1].text, '只有摘要的旧来源');
  assert.equal(legacySources[1].canJumpToSource, false);

  const referencedSources = collectSourcesByIds(
    ['source-1', 'missing', 'legacy-2', 'source-1'],
    sources,
  );
  assert.deepEqual(referencedSources.map((source) => source.sourceId), ['source-1', 'legacy-2']);

  const references = normalizeSentenceReferences(
    [
      { id: 'ref-1', target: 'message', sentence: '这是第一条结论。', sourceIds: ['source-1', 'missing'] },
      { id: 'ref-2', target: 'critical_analysis', sentence: '这是第二条结论。', sourceIds: ['legacy-2'] },
      { id: 'ref-3', target: 'message', sentence: '无效引用。', sourceIds: ['missing'] },
    ],
    sources,
    { target: 'message' },
  );

  assert.equal(references.length, 1);
  assert.equal(references[0].sourceIds[0], 'source-1');
  assert.equal(references[0].sources[0].preview, '第一段证据详细内容。');
  assert.equal(references[0].sources[0].pageIndex, 2);
  assert.equal(references[0].sources[0].sectionId, 'section-1');
  assert.equal(references[0].sources[0].canJumpToSource, true);

  assert.deepEqual(normalizeSentenceReferences(undefined, sources), []);
  assert.deepEqual(normalizeSentenceReferences([{ sentence: '旧响应兼容。', sourceIds: [] }], sources), []);

  console.log('evidence citation model smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
