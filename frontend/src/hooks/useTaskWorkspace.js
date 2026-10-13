import { useCallback, useEffect, useRef, useState } from 'react';
import { taskWorkspaceRemoteStore as taskStore } from '../services/taskWorkspaceRemoteStore';

const ACTIVE_TASK_KEY = 'pixiu-active-task-v1';
const readActiveTask = () => {
  try { return localStorage.getItem(ACTIVE_TASK_KEY); } catch { return null; }
};
const rememberActiveTask = (id) => {
  try { localStorage.setItem(ACTIVE_TASK_KEY, id); } catch { /* Selection is a best-effort preference. */ }
};

/** Task updates are serialized per task so late responses never target the visible task. */
export function useTaskWorkspace(store = taskStore) {
  const [tasks, setTasks] = useState([]);
  const [activeTaskId, setActiveTaskId] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const records = useRef(new Map());
  const queues = useRef(new Map());
  const alive = useRef(true);

  const publish = useCallback(() => {
    const timestamp = (value) => typeof value === 'number' ? value : Date.parse(value) || 0;
    if (alive.current) setTasks([...records.current.values()].sort((a, b) => timestamp(b.updatedAt) - timestamp(a.updatedAt)));
  }, []);

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    store.listTasks().then((loaded) => {
      if (cancelled) return;
      records.current = new Map(loaded.map((task) => [task.id, task]));
      setError(loaded.find((task) => task.persistenceError)?.persistenceError || '');
      publish();
      setActiveTaskId((current) => {
        const remembered = current || readActiveTask();
        return records.current.has(remembered) ? remembered : loaded[0]?.id || null;
      });
      setReady(true);
    }).catch((failure) => {
      if (!cancelled) { setError(failure.message || '任务读取失败'); setReady(true); }
    });
    return () => { cancelled = true; alive.current = false; };
  }, [store, publish]);

  const createTask = useCallback(async (input = {}) => {
    try {
      const task = await store.createTask(input);
      records.current.set(task.id, task);
      rememberActiveTask(task.id);
      publish();
      if (alive.current) { setActiveTaskId(task.id); setError(task.persistenceError || ''); }
      return task;
    } catch (failure) {
      if (alive.current) setError(failure.message || '任务保存失败');
      throw failure;
    }
  }, [store, publish]);

  const updateTask = useCallback((taskId, updater) => {
    const previous = queues.current.get(taskId) || Promise.resolve();
    const operation = previous.catch(() => {}).then(async () => {
      const task = records.current.get(taskId);
      if (!task) throw new Error('任务不存在');
      const patch = typeof updater === 'function' ? updater(task) : updater;
      const saved = await store.saveTask({ ...task, ...patch, id: taskId, updatedAt: Date.now() });
      records.current.set(taskId, saved);
      publish();
      if (alive.current) setError(saved.persistenceError || '');
      return saved;
    }).catch((failure) => {
      if (alive.current) setError(failure.message || '任务保存失败');
      throw failure;
    });
    queues.current.set(taskId, operation);
    void operation.finally(() => {
      if (queues.current.get(taskId) === operation) queues.current.delete(taskId);
    }).catch(() => {});
    return operation;
  }, [store, publish]);

  const selectTask = useCallback((id) => {
    if (!records.current.has(id)) return false;
    rememberActiveTask(id);
    setActiveTaskId(id);
    return true;
  }, []);

  const adoptServerTask = useCallback(async (task) => {
    await (queues.current.get(task.id) || Promise.resolve()).catch(() => {});
    const current = records.current.get(task.id);
    if (current?.revision > task.revision) throw new Error('任务已更新，请重新加载活动');
    records.current.set(task.id, task);
    publish();
    try { await store.cacheConfirmedTask?.(task); }
    catch { if (alive.current) setError('任务已保存，缓存更新失败'); }
    return task;
  }, [store, publish]);

  return { tasks, activeTaskId, activeTask: tasks.find((task) => task.id === activeTaskId) || null,
    ready, error, createTask, updateTask, selectTask, adoptServerTask };
}
