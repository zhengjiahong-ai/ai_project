import { describe, expect, it, vi } from 'vitest';
import { createRemoteTaskStore } from './taskWorkspaceRemoteStore';
import { createTaskWorkspaceApi } from './taskWorkspaceApi';

const task = (id, extra = {}) => ({ id, title: id, paperIds: [], messages: [], notes: [], artifacts: [], focusedPaperId: null, activeActivity: null, ...extra });
const setup = (initial = [], server = []) => {
  const tasks = new Map(initial.map((t) => [t.id, t]));
  const drafts = new Map();
  const cache = {
    listTasks: vi.fn(async () => [...tasks.values()]),
    cacheTask: vi.fn(async (t) => { tasks.set(t.id, t); }),
    replaceServerCache: vi.fn(async (loaded) => {
      for (const [id, t] of tasks) if (t.revision !== undefined && !loaded.some((value) => value.id === id)) tasks.delete(id);
      loaded.forEach((t) => tasks.set(t.id, t));
    }),
    retainUnsyncedDraft: vi.fn(async (t, reason) => { drafts.set(t.id, { task: t, reason }); }),
    clearUnsyncedDraft: vi.fn(async (id) => { drafts.delete(id); }),
    getUnsyncedDraft: vi.fn(async (id) => drafts.get(id)),
  };
  const api = {
    listTasks: vi.fn(async () => server),
    getTask: vi.fn(async (id) => server.find((t) => t.id === id)),
    createTask: vi.fn(async (t) => ({ ...t, revision: 0 })),
    saveTask: vi.fn(async (t) => ({ ...t, revision: t.revision + 1 })),
  };
  return { tasks, drafts, cache, api, store: createRemoteTaskStore(api, cache) };
};

describe('authoritative remote task storage', () => {
  it('sends archive state with revision and retains all content in the confirmed cache', async () => {
    const saved = task('archive', { revision: 2, notes: [{ id: 'note', text: '保留笔记' }] });
    const state = setup([saved]);
    const archived = await state.store.saveTask({ ...saved, archived: true });
    expect(state.api.saveTask.mock.calls[0][0]).toMatchObject({ archived: true, revision: 2, notes: saved.notes });
    expect(state.tasks.get('archive')).toMatchObject({ archived: true, notes: saved.notes });
    await state.store.saveTask({ ...archived, archived: false });
    expect(state.api.saveTask.mock.calls[1][0]).toMatchObject({ archived: false, revision: 3 });
  });
  it('repairs authoritative old document IDs before caching, without sending stale local content', async () => {
    const original = task('old', { revision: 3, notes: [{ content: '原文', versions: [{ text: '旧版' }] }] });
    const repaired = { ...original, revision: 4, notes: [{ ...original.notes[0], id: 'stable' }] };
    const state = setup([], [original]);
    state.api.identifyDocuments = vi.fn(async () => ({ task: repaired, identified: 1, backupId: 'backup' }));
    const loaded = await state.store.listTasks();
    expect(state.api.identifyDocuments).toHaveBeenCalledWith('old', 3);
    expect(loaded[0].notes).toEqual(repaired.notes);
    expect(state.tasks.get('old').revision).toBe(4);
    expect(state.api.saveTask).not.toHaveBeenCalled();
  });
  it('routes encoded task IDs through the shared Java client', async () => {
    const client = { get: vi.fn(), post: vi.fn(), put: vi.fn() };
    const api = createTaskWorkspaceApi(client);
    await api.getTask('legacy:A/B');
    expect(client.get.mock.calls[0][0]).toBe('/task-workspaces/legacy%3AA%2FB');
    await api.saveTask(task('task:1', { revision: 2 }));
    expect(client.put.mock.calls[0].slice(0, 2)).toEqual(['/task-workspaces/task%3A1', task('task:1', { revision: 2 })]);
  });
  it('imports local tasks once and retries safely after a partial network failure', async () => {
    const state = setup([task('A'), task('B')]);
    state.api.createTask.mockRejectedValueOnce(new Error('offline'));
    const offline = await state.store.listTasks();
    expect(offline[0].persistenceStatus).toBe('cached');
    const loaded = await state.store.listTasks();
    expect(loaded.every((t) => t.revision === 0)).toBe(true);
    state.api.listTasks.mockResolvedValue(loaded);
    await state.store.listTasks();
    expect(state.api.createTask).toHaveBeenCalledTimes(3);
  });
  it('keeps a conflicting imported draft while returning the authoritative server record', async () => {
    const state = setup([task('A', { title: 'local edit' })], [task('A', { title: 'server edit', revision: 4 })]);
    const loaded = await state.store.listTasks();
    expect(loaded[0].title).toBe('server edit');
    expect(loaded[0].persistenceError).toContain('本地草稿已保留');
    expect(state.drafts.get('A').task.title).toBe('local edit');
    expect(state.api.saveTask).not.toHaveBeenCalled();
    expect(state.api.createTask).not.toHaveBeenCalled();
  });
  it('does not claim offline saves succeeded, and exposes the failed draft for recovery', async () => {
    const saved = task('A', { title: 'saved', revision: 1 });
    const state = setup([saved]);
    state.api.saveTask.mockRejectedValue(new Error('offline'));
    await expect(state.store.saveTask({ ...saved, title: 'draft' })).rejects.toThrow('尚未同步');
    expect(state.tasks.get('A').title).toBe('saved');
    expect((await state.store.getUnsyncedDraft('A')).task.title).toBe('draft');
  });
  it('does not retry conflicts with a newer revision or silently overwrite either version', async () => {
    const saved = task('A', { revision: 1 });
    const state = setup([saved]);
    state.api.saveTask.mockRejectedValue({ response: { status: 409 } });
    await expect(state.store.saveTask({ ...saved, title: 'draft' })).rejects.toMatchObject({ code: 'TASK_CONFLICT' });
    expect(state.api.saveTask).toHaveBeenCalledTimes(1);
    expect(state.tasks.get('A')).toEqual(saved);
    expect(state.drafts.get('A').reason).toBe('conflict');
  });
  it('preserves an earlier failed answer draft when a later rename succeeds', async () => {
    const saved = task('A', { revision: 1 });
    const state = setup([saved]);
    state.api.saveTask.mockRejectedValueOnce({ response: { status: 409 } });
    await expect(state.store.saveTask({ ...saved, messages: [{ content: 'unsaved answer' }] })).rejects.toThrow();
    await state.store.saveTask({ ...saved, revision: 2, title: 'renamed' });
    expect((await state.store.getUnsyncedDraft('A')).task.messages[0].content).toBe('unsaved answer');
    expect(state.cache.clearUnsyncedDraft).not.toHaveBeenCalled();
    await state.store.clearUnsyncedDraft('A');
    expect(await state.store.getUnsyncedDraft('A')).toBeUndefined();
  });
  it('removes deleted server cache entries without reimporting them', async () => {
    const state = setup([task('deleted', { revision: 2 })], []);
    expect(await state.store.listTasks()).toEqual([]);
    expect(state.tasks.size).toBe(0);
    expect(state.api.createTask).not.toHaveBeenCalled();
  });
  it('keeps confirmed server success when the subsequent cache write fails', async () => {
    const state = setup();
    state.cache.cacheTask.mockRejectedValue(new Error('quota'));
    const saved = await state.store.createTask(task('A'));
    expect(saved.persistenceStatus).toBe('synced');
    expect(saved.persistenceError).toContain('本地缓存更新失败');
    expect(state.cache.retainUnsyncedDraft).not.toHaveBeenCalled();
  });
});
