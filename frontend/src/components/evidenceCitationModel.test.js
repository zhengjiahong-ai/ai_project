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

  // ── External academic sources ──
  const externalSources = normalizeEvidenceSources([
    {
      sourceId: 'ext-1',
      sourceType: 'external_academic',
      provider: 'crossref',
      providerId: 'cr-123',
      title: 'Effect Size Estimation in Meta-Analysis',
      authors: ['Smith J', 'Wang L'],
      year: 2024,
      doi: '10.1234/example',
      url: 'https://doi.org/10.1234/example',
      retrievedAt: '2026-06-26T14:30:00Z',
      license: 'CC BY 4.0',
      abstract: 'This paper examines methods for effect size estimation.',
      text: 'External evidence text content.',
    },
    {
      sourceId: 'ext-2',
      sourceType: 'external_academic',
      provider: 'semantic_scholar',
      title: 'A Study Without URL',
      year: 2023,
      doi: '',
      url: '',
    },
    {
      // source with provider field but unknown sourceType — should still be detected as external
      sourceId: 'ext-3',
      sourceType: 'unknown',
      provider: 'crossref',
      doi: '10.5678/other',
      title: 'Provider-detected source',
      year: 2022,
    },
    {
      // Internal source should remain internal
      sourceId: 'int-1',
      sourceType: 'current_paper',
      text: 'Internal evidence text.',
      pageIndex: 5,
    },
  ]);

  assert.equal(externalSources.length, 4);

  const ext1 = externalSources.find((s) => s.sourceId === 'ext-1');
  assert.equal(ext1.isExternal, true);
  assert.equal(ext1.sourceType, 'external_academic');
  assert.equal(ext1.provider, 'crossref');
  assert.equal(ext1.year, 2024);
  assert.equal(ext1.doi, '10.1234/example');
  assert.equal(ext1.url, 'https://doi.org/10.1234/example');
  assert.equal(ext1.externalUrl, 'https://doi.org/10.1234/example');
  assert.equal(ext1.canJumpToSource, true);
  assert.equal(ext1.locationLabel, 'crossref · 2024');
  assert.deepEqual(ext1.authors, ['Smith J', 'Wang L']);
  assert.equal(ext1.title, 'Effect Size Estimation in Meta-Analysis');
  assert.equal(ext1.retrievedAt, '2026-06-26T14:30:00Z');
  assert.equal(ext1.license, 'CC BY 4.0');
  assert.equal(ext1.abstract, 'This paper examines methods for effect size estimation.');

  // External source without URL/DOI: canJumpToSource = false, no fabricated link
  const ext2 = externalSources.find((s) => s.sourceId === 'ext-2');
  assert.equal(ext2.isExternal, true);
  assert.equal(ext2.canJumpToSource, false);
  assert.equal(ext2.externalUrl, '');
  assert.equal(ext2.url, '');
  assert.equal(ext2.doi, '');

  // Provider-detected external source (sourceType was 'unknown' but provider field present)
  const ext3 = externalSources.find((s) => s.sourceId === 'ext-3');
  assert.equal(ext3.isExternal, true);
  assert.equal(ext3.sourceType, 'external_academic');
  assert.equal(ext3.provider, 'crossref');
  assert.equal(ext3.canJumpToSource, true);
  assert.equal(ext3.externalUrl, 'https://doi.org/10.5678/other');

  // Internal source should remain internal
  const int1 = externalSources.find((s) => s.sourceId === 'int-1');
  assert.equal(int1.isExternal, false);
  assert.equal(int1.sourceType, 'current_paper');
  assert.equal(int1.canJumpToSource, true);
  assert.equal(int1.pageIndex, 5);
  assert.equal(int1.locationLabel, 'p.6');

  // DOI-only external source creates a doi.org link
  const doiOnlySources = normalizeEvidenceSources([
    { sourceId: 'doi-only', sourceType: 'external_academic', provider: 'crossref', doi: '10.9999/test', title: 'DOI Only Paper', year: 2025 },
  ]);
  assert.equal(doiOnlySources[0].canJumpToSource, true);
  assert.equal(doiOnlySources[0].externalUrl, 'https://doi.org/10.9999/test');

  // External source with no meaningful content should be filtered out
  const emptyExternal = normalizeEvidenceSources([
    { sourceId: 'empty-ext', sourceType: 'external_academic' },
  ]);
  assert.equal(emptyExternal.length, 0);

  console.log('evidence citation model smoke tests passed');
};

run().catch((error) => {
  console.error(error);
  globalThis.process.exit(1);
});
