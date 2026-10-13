import { describe, expect, it } from 'vitest';
import { taskChatHistory } from './taskChatHistory';

const scope = { taskId: 'task', allowedPaperIds: ['A'], primaryPaperId: 'A', strictScope: true };
describe('taskChatHistory', () => {
  it('excludes earlier mixed-paper answers and their questions after scope narrows', () => {
    expect(taskChatHistory([
      { role: 'user', content: 'compare', context: { ...scope, allowedPaperIds: ['A', 'B'] } },
      { role: 'ai', content: 'B evidence', context: { ...scope, allowedPaperIds: ['A', 'B'] } },
      { role: 'user', content: 'A question', context: scope },
      { role: 'ai', content: 'A answer', context: scope },
    ], scope)).toEqual([{ role: 'user', content: 'A question' }, { role: 'assistant', content: 'A answer' }]);
  });
  it('excludes unknown provenance, other tasks, and system failures', () => {
    expect(taskChatHistory([
      { role: 'ai', content: 'legacy' },
      { role: 'ai', content: 'other', context: { ...scope, taskId: 'other' } },
      { role: 'ai', content: 'error', context: scope, isSystem: true },
    ], scope)).toEqual([]);
  });
  it('retains a prior single-paper discussion when broadening to the task', () => {
    expect(taskChatHistory([{ role: 'ai', content: 'A', context: scope }], {
      ...scope, allowedPaperIds: ['A', 'B'], strictScope: false,
    })).toEqual([{ role: 'assistant', content: 'A' }]);
  });
});
