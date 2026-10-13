import { describe, it, expect } from 'vitest';
import { reviseDocument } from './documentVersions';

describe('research document versions', () => {
  it('marks a user revision and preserves the preceding machine text', () => {
    const machine = { id: 'a', sourceRunId: 'r', origin: 'latest', text: '机器原稿', reportVersionId: 'v1', versions: [] };
    const edited = reviseDocument(machine, '我的理解');
    expect(edited.edited).toBe(true);
    expect(edited.versions[0]).toMatchObject({ text: '机器原稿', edited: false });
    expect(edited.reportVersionId).toBe('v1');
    const restored = reviseDocument(edited, '机器原稿', { restoredFrom: 'v1' });
    expect(restored.edited).toBe(true);
    expect(restored.versions[1]).toMatchObject({ text: '我的理解', edited: true });
  });
  it('does not treat saving unchanged text as a user modification', () => {
    const result = reviseDocument({ sourceRunId: 'r', text: '原稿', edited: false, versions: [] }, '原稿');
    expect(result.edited).toBe(false);
    expect(result.versions).toEqual([]);
  });
});
