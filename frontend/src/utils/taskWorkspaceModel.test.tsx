import { describe, expect, it } from 'vitest';
import { resolveTaskContext, type TaskWorkspace } from './taskWorkspaceModel';

const task: TaskWorkspace = {
  id: 'task-1', title: '比较任务', paperIds: ['A', 'B'], messages: [], notes: [], artifacts: [],
  focusedPaperId: 'A', activeActivity: null, updatedAt: '2026-10-04T00:00:00.000Z',
};

describe('resolveTaskContext', () => {
  it('uses explicit papers first and rejects a paper outside the task', () => {
    expect(resolveTaskContext({ ...task, activeActivity: { id: 'reading-A', paperIds: ['A'] } }, {
      paperIds: ['B'], text: '这篇的方法',
    })).toEqual({ taskId: 'task-1', allowedPaperIds: ['B'], primaryPaperId: 'B', strictScope: false });
    expect(() => resolveTaskContext(task, { paperIds: ['C'] })).toThrow('不属于当前任务');
  });

  it('keeps an activity snapshot even when reading focus changes', () => {
    const activeTask = {
      ...task, focusedPaperId: 'B',
      activeActivity: { id: 'reading-A', snapshot: { paperIds: ['A'], primaryPaperId: 'A', strictScope: true } },
    };
    expect(resolveTaskContext(activeTask, { text: '继续精读这篇' })).toEqual({
      taskId: 'task-1', allowedPaperIds: ['A'], primaryPaperId: 'A', strictScope: true, activityId: 'reading-A',
    });
  });

  it('uses focus as primary for a single-paper reference while retaining task materials', () => {
    expect(resolveTaskContext(task, { text: '这篇论文的方法是什么？' })).toEqual({
      taskId: 'task-1', allowedPaperIds: ['A', 'B'], primaryPaperId: 'A', strictScope: false,
    });
    expect(resolveTaskContext(task, { text: '比较方法' }).allowedPaperIds).toEqual(['A', 'B']);
  });

  it('limits only-this-paper requests to the focused paper', () => {
    expect(resolveTaskContext(task, { text: '只根据这篇分析局限' })).toEqual({
      taskId: 'task-1', allowedPaperIds: ['A'], primaryPaperId: 'A', strictScope: true,
    });
    expect(() => resolveTaskContext({ ...task, focusedPaperId: null }, { strictScope: true }))
      .toThrow('请明确指定');
    const activeTask = { ...task, activeActivity: { id: 'reading-B', paperIds: ['B'] } };
    expect(resolveTaskContext(activeTask, { text: '只根据这篇回答' })).toEqual({
      taskId: 'task-1', allowedPaperIds: ['A'], primaryPaperId: 'A', strictScope: true,
    });
  });

  it('asks for clarification on a single-paper reference without a focus', () => {
    expect(() => resolveTaskContext({ ...task, focusedPaperId: null }, { text: '这篇的方法是什么？' }))
      .toThrow('请明确指定');
  });

  it('never expands an empty task into the global library', () => {
    expect(resolveTaskContext({ ...task, paperIds: [], focusedPaperId: null }, { text: '找相关论文' }))
      .toEqual({ taskId: 'task-1', allowedPaperIds: [], primaryPaperId: null, strictScope: false });
  });

  it('lets explicit all-task material override an ongoing single-paper lesson', () => {
    expect(resolveTaskContext({ ...task, activeActivity: { activityId: 'lesson', paperIds: ['A'] } }, {
      text: '解释任务中的所有论文用到的方法',
    })).toEqual({ taskId: 'task-1', allowedPaperIds: ['A', 'B'], primaryPaperId: null, strictScope: false });
  });
  it('uses all task materials when explicitly restricting to the task', () => {
    expect(resolveTaskContext(task, { text: '只根据任务中的所有论文做比较' })).toEqual({
      taskId: 'task-1', allowedPaperIds: ['A', 'B'], primaryPaperId: null, strictScope: true,
    });
  });
  it('lets a new capability use task materials without discarding the lesson', () => {
    const activity = { id: 'reading-A', paperIds: ['A'], primaryPaperId: 'A' };
    const activeTask = { ...task, activeActivity: activity };
    expect(resolveTaskContext(activeTask, { text: '比较论文方法', activity: null }).allowedPaperIds).toEqual(['A', 'B']);
    expect(resolveTaskContext(activeTask, { text: '这个术语是什么意思' }).activityId).toBe('reading-A');
    expect(activeTask.activeActivity).toBe(activity);
  });
});
