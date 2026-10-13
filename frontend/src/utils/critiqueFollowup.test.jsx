import { describe, it, expect } from 'vitest';
import { resolveCritiqueFollowup } from './critiqueFollowup';

const task = { id: 't1', messages: [{ id: 'm1', role: 'ai', artifactId: 'a1', critique: { schemaVersion: 2, presentation: { chatIssueIds: ['i1', 'i2'] } } }],
  artifacts: [{ id: 'a1', updatedAt: 'saved-version', edited: true, critique: { schemaVersion: 2 } }] };
describe('critique followup identity', () => {
  it('binds an ordinal to the displayed stable issue and latest saved artifact version', () => {
    expect(resolveCritiqueFollowup(task, '解释一下第二点')).toEqual({ artifactId: 'a1', issueId: 'i2', version: 'saved-version' });
    expect(resolveCritiqueFollowup(task, '第三点为什么')).toBeNull();
    expect(resolveCritiqueFollowup(task, '换个问题')).toBeNull();
  });
  it('does not infer a legacy critique or reuse another task selection', () => {
    expect(resolveCritiqueFollowup({ ...task, messages: [{ role: 'ai', content: '第一点' }] }, '第二点为什么')).toBeNull();
    expect(resolveCritiqueFollowup(task, '换个问题', { taskId: 'other', followup: { artifactId: 'foreign' } })).toBeNull();
  });
  it('does not silently rebind an old chat answer after artifact regeneration', () => {
    const changed = { ...task, messages: [{ ...task.messages[0], sourceRequestId: 'old' }],
      artifacts: [{ ...task.artifacts[0], sourceRequestId: 'new' }] };
    expect(resolveCritiqueFollowup(changed, '第二点为什么')).toEqual({ error: expect.stringContaining('旧版本') });
  });
});
