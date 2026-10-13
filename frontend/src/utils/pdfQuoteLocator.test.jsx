import { describe, it, expect } from 'vitest';
import { locateQuotePage } from './pdfQuoteLocator';

describe('literal PDF quote location', () => {
  const quote = 'Pruning removes redundant Gaussians while preserving rendering accuracy.';
  it('uses the actual unique PDF page even when the index points elsewhere', () => {
    expect(locateQuotePage(['Unrelated indexed page', quote], quote)).toBe(1);
  });
  it('does not guess from partial keywords, short text or duplicate matches', () => {
    expect(locateQuotePage([quote], 'Pruning')).toBeNull();
    expect(locateQuotePage([quote, quote], quote)).toBeNull();
    expect(locateQuotePage(['Pruning removes Gaussians.'], quote)).toBeNull();
  });
  it('normalizes PDF ligatures and line hyphenation without changing the words', () => {
    expect(locateQuotePage(['Pruning removes redun-\ndant Gaussians while preserving rendering accuracy.'], quote)).toBe(0);
  });
});
