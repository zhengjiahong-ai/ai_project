import { describe, expect, it } from 'vitest';
import { taskDocumentNavigation } from './taskDocumentNavigation';

describe('research document navigation', () => {
  it('keeps removed machine history persisted without bringing it back into the library', () => {
    const task = { artifacts: [{ id: 'a', origin: 'machine', sourceRunId: 'r', hiddenFromLibrary: true }] };
    expect(taskDocumentNavigation(task)).toEqual([]);
    expect(task.artifacts).toHaveLength(1);
  });
  const baseTask = { notes: [], artifacts: [] };

  it('returns all items when no machine duplicates exist', () => {
    const task = { ...baseTask, artifacts: [
      { id: 'a1', title: '报告A', origin: 'machine', sourceResearchId: 'r1' },
      { id: 'a2', title: '报告B', origin: 'user', sourceResearchId: 'r2' },
    ] };
    const result = taskDocumentNavigation(task);
    expect(result).toHaveLength(2);
  });

  it('hides machine artifact when user version exists for same research', () => {
    const task = { ...baseTask, artifacts: [
      { id: 'a1', title: '消融实验方案', origin: 'machine', sourceResearchId: 'r1', createdAt: '2026-10-12T10:00:00Z' },
      { id: 'a2', title: '消融实验方案', origin: 'user', sourceResearchId: 'r1', createdAt: '2026-10-12T11:00:00Z' },
    ] };
    const result = taskDocumentNavigation(task);
    expect(result).toHaveLength(1);
    expect(result[0].item.id).toBe('a2');
  });

  it('keeps machine artifact when no user version exists', () => {
    const task = { ...baseTask, artifacts: [
      { id: 'a1', title: '消融实验方案', origin: 'machine', sourceResearchId: 'r1' },
    ] };
    const result = taskDocumentNavigation(task);
    expect(result).toHaveLength(1);
    expect(result[0].item.id).toBe('a1');
  });

  it('keeps all versions when none are machine origin', () => {
    const task = { ...baseTask, artifacts: [
      { id: 'a1', title: '报告', origin: 'user', sourceResearchId: 'r1' },
      { id: 'a2', title: '报告', origin: 'latest', sourceResearchId: 'r1' },
    ] };
    const result = taskDocumentNavigation(task);
    expect(result).toHaveLength(2);
  });

  it('does not filter items without sourceResearchId', () => {
    const task = { ...baseTask, artifacts: [
      { id: 'a1', title: '笔记', origin: 'machine' },
      { id: 'a2', title: '笔记', origin: 'user' },
    ] };
    const result = taskDocumentNavigation(task);
    expect(result).toHaveLength(2);
  });

  it('handles mixed notes and artifacts', () => {
    const task = {
      notes: [{ id: 'n1', title: '用户笔记', type: 'note' }],
      artifacts: [
        { id: 'a1', title: '研究报告', origin: 'machine', sourceResearchId: 'r1' },
        { id: 'a2', title: '研究报告', origin: 'user', sourceResearchId: 'r1' },
      ],
    };
    const result = taskDocumentNavigation(task);
    expect(result).toHaveLength(2);
    const ids = result.map(r => r.item.id);
    expect(ids).toContain('n1');
    expect(ids).toContain('a2');
    expect(ids).not.toContain('a1');
  });
});
