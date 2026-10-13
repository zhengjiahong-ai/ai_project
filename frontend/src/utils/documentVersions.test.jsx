import { describe, it, expect } from 'vitest';
import { reviseDocument } from './documentVersions';

describe('document version preservation', () => {
  it('marks edited critique text without changing the original claim structure', () => {
    const critique = { schemaVersion: 2, issues: [{ id: 'stable-id' }] };
    const next = reviseDocument({ text: 'generated', critique, versions: [] }, 'user assertion', { now: 'edited-version' });
    expect(next.edited).toBe(true);
    expect(next.critique).toEqual(critique);
    expect(next.versions[0]).toMatchObject({ text: 'generated', critique, edited: false });
  });
  it('restores old text while retaining both saved text and unsaved edits', () => {
    const original = { text: 'saved', paperIds: ['a'], versions: [{ text: 'old', savedAt: 'before' }] };
    const next = reviseDocument(original, 'old', { draft: 'unsaved', restoredFrom: 'before', now: 'now' });
    expect(next.text).toBe('old');
    expect(next.versions.map((item) => item.text)).toEqual(['old', 'saved', 'unsaved']);
    expect(next.paperIds).toEqual(['a']);
    expect(original.versions).toHaveLength(1);
  });
  it('preserves intentional empty text and avoids redundant history on unchanged saves', () => {
    const next = reviseDocument({ content: 'legacy', versions: [] }, '');
    expect(next.text).toBe('');
    expect(next.versions[0].text).toBe('legacy');
    expect(reviseDocument(next, '').versions).toHaveLength(1);
  });
});
