import * as localStore from './taskWorkspaceStore';
import { taskWorkspaceApi } from './taskWorkspaceApi';

const payload = (task) => ({
  id: task.id, title: task.title, archived: task.archived === true, paperIds: task.paperIds || [], messages: task.messages || [],
  notes: task.notes || [], artifacts: task.artifacts || [], focusedPaperId: task.focusedPaperId ?? null,
  activeActivity: task.activeActivity ?? null,
  researchRuns: task.researchRuns || [],
  activityHistory: task.activityHistory || [],
  ...(task.legacyMigration ? { legacyMigration: task.legacyMigration } : {}),
  ...(task.legacyArchive ? { legacyArchive: task.legacyArchive } : {}),
  ...(task.revision !== undefined ? { revision: task.revision } : {}),
});
const sameContent = (a, b) => JSON.stringify({ ...payload(a), revision: undefined })
  === JSON.stringify({ ...payload(b), revision: undefined });
const conflict = () => Object.assign(new Error('任务已在其他位置更新。本地草稿已保留，请刷新后核对并重新提交。'), { code: 'TASK_CONFLICT' });

export function createRemoteTaskStore(api = taskWorkspaceApi, cache = localStore) {
  let loadPromise = null;
  const read = async () => {
    const local = await cache.listTasks();
    try {
      const remote = await api.listTasks();
      const byId = new Map(remote.map((task) => [task.id, task]));
      let migrationWarning = '';
      for (const task of remote) {
        const missingIds = [...(task.notes || []), ...(task.artifacts || [])].some(item => !item.id && !item.artifactId);
        if (missingIds && api.identifyDocuments) {
          try {
            const repaired = await api.identifyDocuments(task.id, task.revision);
            byId.set(task.id, repaired.task);
          } catch {
            migrationWarning = '旧笔记标识尚未补全，正文保留；请刷新后重试整理。';
          }
        }
      }
      // Existing server records are never overwritten during a local import.
      for (const task of local.filter((value) => value.revision === undefined)) {
        let imported = byId.get(task.id);
        if (imported && !sameContent(task, imported)) {
          await cache.retainUnsyncedDraft(task, 'migration-conflict');
          migrationWarning = conflict().message;
          continue;
        }
        if (!imported) {
          try { imported = await api.createTask(payload(task)); }
          catch (failure) {
            if (failure?.response?.status !== 409) throw failure;
            imported = await api.getTask(task.id);
            if (!sameContent(task, imported)) {
              await cache.retainUnsyncedDraft(task, 'migration-conflict');
              migrationWarning = conflict().message;
              byId.set(imported.id, imported);
              continue;
            }
          }
          // Per-record progress survives an interrupted import; retries are idempotent.
          await cache.cacheTask(imported);
          byId.set(imported.id, imported);
        }
      }
      const tasks = [...byId.values()];
      await cache.replaceServerCache(tasks);
      return tasks.map((task) => ({ ...task, persistenceStatus: 'synced',
        ...(migrationWarning ? { persistenceError: migrationWarning } : {}) }));
    } catch (failure) {
      const cached = await cache.listTasks();
      if (!cached.length) throw failure;
      return cached.map((task) => ({ ...task, persistenceStatus: 'cached', persistenceError:
        failure.code === 'TASK_CONFLICT' ? failure.message : '服务端暂不可用，当前显示本地缓存；修改须成功同步后才算保存。' }));
    }
  };
  const write = async (task, create) => {
    // Stable IDs allow an ambiguous network failure to be checked on the next load.
    const input = task.id ? task : { ...task, id: `task:${globalThis.crypto.randomUUID()}` };
    let saved;
    try { saved = await (create ? api.createTask(payload(input)) : api.saveTask(payload(input))); }
    catch (failure) {
      const isConflict = failure?.response?.status === 409;
      const message = isConflict ? conflict().message : '服务端保存失败，本地草稿已保留，尚未同步。请连接服务后重试。';
      try { await cache.retainUnsyncedDraft(input, isConflict ? 'conflict' : 'offline'); }
      catch { throw new Error(`${message} 本地草稿保存也失败，请保留当前内容。`); }
      throw Object.assign(new Error(message), { code: isConflict ? 'TASK_CONFLICT' : 'TASK_SAVE_FAILED' });
    }
    // A cache failure must not turn a confirmed server commit into an unsynced write.
    try {
      await cache.cacheTask(saved);
      return { ...saved, persistenceStatus: 'synced' };
    } catch {
      return { ...saved, persistenceStatus: 'synced', persistenceError: '任务已保存到服务端，但本地缓存更新失败。' };
    }
  };
  return {
    listTasks() {
      if (!loadPromise) loadPromise = read().finally(() => { loadPromise = null; });
      return loadPromise;
    },
    async getTask(id) { return (await api.getTask(id)); },
    cacheConfirmedTask: (task) => cache.cacheTask(task),
    createTask: (task = {}) => write(task, true),
    saveTask: (task) => write(task, false),
    getUnsyncedDraft: (id) => cache.getUnsyncedDraft(id),
    listUnsyncedDrafts: () => cache.listUnsyncedDrafts(),
    retainUnsyncedDraft: (task, reason) => cache.retainUnsyncedDraft(task, reason),
    // Only an explicit user decision may discard preserved draft versions.
    clearUnsyncedDraft: (id) => cache.clearUnsyncedDraft(id),
  };
}

export const taskWorkspaceRemoteStore = createRemoteTaskStore();
