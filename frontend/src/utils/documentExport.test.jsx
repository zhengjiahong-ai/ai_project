import { expect, it } from 'vitest';
import { documentMarkdownExport } from './documentExport';
it('exports the live draft while retaining original paper identities', () => {
  const document = { text: '旧正文', sources: [{ pdfId: 'A', sourceId: 'A-chunk-2', pageIndex: 1 }] };
  const result = documentMarkdownExport(document, '当前正文', [{ id: 'A', title: '论文甲' }]);
  expect(result.startsWith('当前正文\n')).toBe(true);
  expect(result).toContain('论文甲，第 2 页，A-chunk-2');
  expect(document.text).toBe('旧正文');
});
it('does not infer sources when no saved material association exists', () => {
  expect(documentMarkdownExport({}, '', [{ id: 'B', title: '当前阅读论文' }])).toBe('');
});
it('exports saved page artifact associations without inventing an excerpt', () => {
  const result = documentMarkdownExport({ paperIds: ['A'], pageIndex: 3 },
    '> 请以原图为准。\n\n译文', [{ id: 'A', title: '来源论文' }, { id: 'B', title: '当前阅读论文' }]);
  expect(result).toContain('<summary>材料来源</summary>');
  expect(result).toContain('来源论文，第 4 页');
  expect(result).not.toContain('当前阅读论文');
  expect(result).not.toContain('chunk');
});
it('does not attribute a multi-paper artifact page to every material', () => {
  const result = documentMarkdownExport({ paperIds: ['A', 'B'], pageIndex: 3 }, '正文');
  expect(result).toContain('- A');
  expect(result).toContain('- B');
  expect(result).not.toContain('第 4 页');
});
it('keeps detailed saved references when a material association also exists', () => {
  const result = documentMarkdownExport({ paperIds: ['A', 'B'],
    sources: [{ pdfId: 'A', sourceId: 'excerpt-1', pageIndex: 1 }] }, '正文');
  expect(result).toContain('A，第 2 页，excerpt-1');
  expect(result).not.toContain('- B');
});
