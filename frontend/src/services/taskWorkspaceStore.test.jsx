import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createTask, getTask, listTasks, migrateLegacyPaperTasks, saveTask, retainUnsyncedDraft, getUnsyncedDraft, clearUnsyncedDraft, identifyLegacyDocuments } from './taskWorkspaceStore.js';

const state = vi.hoisted(() => ({ db: null }));
vi.mock('./localDb.js', () => ({ initDB: async () => state.db }));

const makeDb = () => {
  const stores = new Map([
    'libraryStore', 'pdfStore', 'historyStore', 'notesStore', 'artifactStore',
    'taskWorkspaceStore', 'metaStore',
  ].map((name) => [name, new Map()]));
  return {
    stores,
    failStore: null,
    async get(name, key) { return stores.get(name).get(key); },
    async getAll(name) { return [...stores.get(name).values()]; },
    async getAllKeys(name) { return [...stores.get(name).keys()]; },
    async delete(name, key) { stores.get(name).delete(key); },
    transaction(name) {
      return { objectStore: () => ({
        get: async (key) => stores.get(name).get(key),
        put: async (value, key) => stores.get(name).set(key, value),
      }), done: Promise.resolve() };
    },
    async put(name, value, key) {
      if (this.failStore === name) throw new Error(`write failed: ${name}`);
      stores.get(name).set(key ?? value.id, value);
    },
  };
};

describe('taskWorkspaceStore', () => {
  beforeEach(() => { state.db = makeDb(); });

  it('adds stable separate document identities without losing duplicate text, versions or existing IDs', () => {
    const input = { id: '旧任务'.repeat(200), notes: [
      { content: '相同正文', versions: [{ text: '旧版本' }], sources: [{ pdfId: 'A' }] },
      { content: '相同正文' }, { id: 'known', content: '原标识' },
    ], artifacts: [{ artifactId: 'existing-artifact', text: '保留成果' }] };
    const result = identifyLegacyDocuments(input);
    expect(result.notes[0]).toMatchObject(input.notes[0]);
    expect(result.notes[0].id.length).toBeLessThan(255);
    expect(result.notes[0].id).not.toBe(result.notes[1].id);
    expect(result.notes[2]).toEqual(input.notes[2]);
    expect(result.artifacts).toEqual(input.artifacts);
    expect(identifyLegacyDocuments(result)).toEqual(result);
    expect(identifyLegacyDocuments(input)).toEqual(result);
    expect(identifyLegacyDocuments({ ...input, id: '另一任务' }).notes[0].id).not.toBe(result.notes[0].id);
    expect(input.notes[0].id).toBeUndefined();
  });

  it('migrates one task per legacy PDF, copies user data, and leaves old records intact', async () => {
    const { stores } = state.db;
    stores.get('libraryStore').set('paper-a', { id: 'paper-a', filename: '论文 A.pdf', timestamp: 1000 });
    stores.get('pdfStore').set('paper-a', { name: '论文 A.pdf' });
    stores.get('pdfStore').set('paper-b', { name: '论文 B.pdf' });
    stores.get('historyStore').set('paper-a', [{ role: 'user', content: '问题' }]);
    stores.get('notesStore').set('paper-a', [{ content: '我的笔记' }]);
    stores.get('artifactStore').set('paper-a', [{ title: '成果' }]);

    const tasks = await listTasks();
    expect(tasks).toHaveLength(2);
    expect(await getTask('legacy:paper-a')).toMatchObject({
      title: '论文 A.pdf', paperIds: ['paper-a'], focusedPaperId: 'paper-a',
      messages: [{ role: 'user', content: '问题', taskId: 'legacy:paper-a', context: {
        taskId: 'legacy:paper-a', allowedPaperIds: ['paper-a'], primaryPaperId: 'paper-a', strictScope: true,
      } }],
      notes: [{ content: '我的笔记', paperIds: ['paper-a'] }], artifacts: [{ title: '成果', paperIds: ['paper-a'] }],
    });
    expect(stores.get('historyStore').get('paper-a')).toEqual([{ role: 'user', content: '问题' }]);
    expect(stores.get('pdfStore').has('paper-a')).toBe(true);
    expect(await migrateLegacyPaperTasks()).toBe(0);
    expect((await listTasks()).length).toBe(2);
  });

  it('does not create a duplicate legacy task for a paper already in a task', async () => {
    state.db.stores.get('libraryStore').set('paper-a', { id: 'paper-a' });
    await createTask({ title: '跨论文任务', paperIds: ['paper-a'] });
    expect(await migrateLegacyPaperTasks()).toBe(0);
    expect(await listTasks()).toHaveLength(1);
  });

  it('repairs migrated records even when v1 markers already exist, without guessing multi-paper history', async () => {
    const { stores } = state.db;
    stores.get('pdfStore').set('paper-a', { name: 'A.pdf' });
    stores.get('metaStore').set('legacyPaperTask:paper-a', { migratedAt: 'old' });
    stores.get('taskWorkspaceStore').set('legacy:paper-a', {
      id: 'legacy:paper-a', paperIds: [], messages: [{ content: '旧问题' }],
      notes: [{ content: '旧笔记' }], artifacts: [{ title: '旧成果' }],
    });
    await createTask({ id: 'ignored', paperIds: ['A', 'B'], messages: [{ content: '未知来源' }, { content: '已知来源', pdfId: 'B' }] });
    await migrateLegacyPaperTasks();
    const legacy = stores.get('taskWorkspaceStore').get('legacy:paper-a');
    expect(legacy.messages[0].context.allowedPaperIds).toEqual(['paper-a']);
    expect(legacy.notes[0].paperIds).toEqual(['paper-a']);
    expect(legacy.artifacts[0].paperIds).toEqual(['paper-a']);
    const other = [...stores.get('taskWorkspaceStore').values()].find((task) => task.id !== legacy.id);
    expect(other.messages[0].context).toBeUndefined();
    expect(other.messages[1].context.allowedPaperIds).toEqual(['B']);
    const snapshot = JSON.stringify(legacy);
    await migrateLegacyPaperTasks();
    expect(JSON.stringify(stores.get('taskWorkspaceStore').get(legacy.id))).toBe(snapshot);
  });

  it('does not recreate a migrated task after its paper is moved away', async () => {
    state.db.stores.get('pdfStore').set('paper-a', { name: 'A.pdf' });
    expect(await migrateLegacyPaperTasks()).toBe(1);
    const original = await getTask('legacy:paper-a');
    await saveTask({ ...original, paperIds: [], focusedPaperId: null });
    expect(await migrateLegacyPaperTasks()).toBe(0);
    expect(await listTasks()).toHaveLength(1);
    expect((await getTask('legacy:paper-a')).paperIds).toEqual([]);
  });

  it('saves empty messages and exposes the persisted version', async () => {
    const created = await createTask({ title: '阅读', paperIds: ['paper-a'], messages: [{ content: 'old' }] });
    const saved = await saveTask({ ...created, messages: [], notes: [{ content: '保留' }] });
    expect(saved.messages).toEqual([]);
    expect((await getTask(created.id)).messages).toEqual([]);
    const persisted = await getTask(created.id);
    expect(persisted.notes).toMatchObject([{ content: '保留' }]);
    expect(persisted.notes[0].id).toBeTruthy();
    expect((await getTask(created.id)).notes[0].id).toBe(persisted.notes[0].id);
  });

  it('rejects storage failures and never returns a fabricated success', async () => {
    state.db.failStore = 'taskWorkspaceStore';
    await expect(createTask({ title: '失败任务' })).rejects.toThrow('write failed');
    expect(state.db.stores.get('taskWorkspaceStore').size).toBe(0);
    state.db.failStore = null;
    const task = await createTask({ title: '可保存任务' });
    state.db.failStore = 'taskWorkspaceStore';
    await expect(saveTask({ ...task, messages: [] })).rejects.toThrow('write failed');
  });

  it('can safely retry after migration fails mid-way', async () => {
    state.db.stores.get('pdfStore').set('paper-a', { name: 'A.pdf' });
    state.db.failStore = 'metaStore';
    await expect(migrateLegacyPaperTasks()).rejects.toThrow('write failed');
    expect(state.db.stores.get('taskWorkspaceStore').size).toBe(1);
    state.db.failStore = null;
    expect(await migrateLegacyPaperTasks()).toBe(0);
    expect(await listTasks()).toHaveLength(1);
  });
  it('retains distinct failed draft versions until explicitly discarded', async () => {
    const first = { id: 'draft-task', messages: [{ content: 'first answer' }] };
    const second = { id: 'draft-task', messages: [{ content: 'second answer' }] };
    await retainUnsyncedDraft(first, 'offline');
    await retainUnsyncedDraft(second, 'conflict');
    await retainUnsyncedDraft(second, 'conflict');
    const draft = await getUnsyncedDraft(first.id);
    expect(draft.task).toEqual(second);
    expect(draft.versions.map((version) => version.task)).toEqual([first, second]);
    await clearUnsyncedDraft(first.id);
    expect(await getUnsyncedDraft(first.id)).toBeNull();
  });
});
