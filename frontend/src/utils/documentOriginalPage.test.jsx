import { expect, it } from 'vitest';
import { documentOriginalPage } from './documentOriginalPage';

it('uses saved page associations rather than the current reader', () => {
  expect(documentOriginalPage({ paperIds: ['A'], pageIndex: 3 })).toEqual({ pdfId: 'A', pageIndex: 3 });
  expect(documentOriginalPage({ sources: [{ pdfId: 'A', pageIndex: 2 }, { pdfId: 'A', pageIndex: 2 }] }))
    .toEqual({ pdfId: 'A', pageIndex: 2 });
});
it('rejects ambiguous, missing and negative saved page identities', () => {
  for (const value of [null, {}, { paperIds: ['A', 'B'], pageIndex: 3 }, { paperIds: ['A'], pageIndex: -1 },
    { sources: [{ pdfId: 'A', pageIndex: 0 }, { pdfId: 'A', pageIndex: 1 }] },
    { sources: [{ pdfId: 'A', pageIndex: 0 }, { pdfId: 'B' }] }]) {
    expect(documentOriginalPage(value)).toBeNull();
  }
});
