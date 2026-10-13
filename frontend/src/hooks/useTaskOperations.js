import { useEffect, useRef, useState } from 'react';

const prefix = 'pixiu-task-request-v1:';
const active = new Set(['queued', 'running', 'cancelling', 'unknown']);
const terminal = new Set(['succeeded', 'failed', 'cancelled', 'interrupted', 'conflicted']);
const retryable = new Set(['failed', 'cancelled', 'interrupted']);
const historyPrefix = 'pixiu-task-request-history-v1:';
const readJournal = () => {
  const entries = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(prefix)) {
      try { entries.push(JSON.parse(localStorage.getItem(key))); } catch { /* Preserve unreadable records. */ }
    }
  }
  return entries;
};

/** Persist intent before sending; reconcile lost responses with the same request ID. */
export function useTaskOperations(workspace, api) {
  const [records, setRecords] = useState({});
  const [errors, setErrors] = useState({});
  const setTaskError = (taskId, message) => setErrors(previous => ({ ...previous, [taskId]: message }));
  const setError = message => setTaskError(latest.current.activeTaskId, message);
  const latest = useRef(workspace);
  const alive = useRef(true);
  const submitting = useRef(new Set());
  const retrying = useRef(new Set());
  const [retryingTasks, setRetryingTasks] = useState({});
  const recordsRef = useRef(records);
  recordsRef.current = records;
  const polledAt = useRef(new Map());
  latest.current = workspace;
  const taskKey = JSON.stringify((workspace.tasks || []).map(task => task.id).sort());
  const publish = async (receipt, isCurrent = () => alive.current) => {
    if (!isCurrent()) return receipt;
    if (!receipt?.requestId || !receipt?.taskId) throw new Error('服务未返回请求标识');
    if (receipt.status === 'succeeded') {
      if (!receipt.task || receipt.task.id !== receipt.taskId) throw new Error('请求结果与任务不匹配');
      await latest.current.adoptServerTask(receipt.task);
    }
    if (!isCurrent()) return receipt;
    let savedIntent;
    try {
      savedIntent = JSON.parse(localStorage.getItem(prefix + receipt.requestId) || localStorage.getItem(historyPrefix + receipt.requestId) || 'null');
    } catch { /* Server intent remains authoritative when local recovery is unreadable. */ }
    if (savedIntent?.cancelRequested && active.has(receipt.status) && receipt.status !== 'cancelling') {
      return publish(await api.cancelOperation(receipt.taskId, receipt.requestId,
        { kind: savedIntent.kind, input: savedIntent.input }), isCurrent);
    }
    const intent = receipt.request || savedIntent?.input || receipt.input;
    const record = { ...receipt, ...(intent ? { request: intent } : {}) };
    setRecords(previous => ({ ...previous, [receipt.requestId]: { ...previous[receipt.requestId], ...record },
      ...(receipt.retryOf ? { [receipt.retryOf]: { ...previous[receipt.retryOf], taskId: receipt.taskId,
        requestId: receipt.retryOf, retriedBy: receipt.requestId } } : {}) }));
    if (terminal.has(receipt.status)) {
      if (retryable.has(receipt.status) && intent) {
        // Keep rejected-before-scheduling requests across refresh too. Server
        // receipts provide the same recovery on another client.
        localStorage.setItem(historyPrefix + receipt.requestId, JSON.stringify(record));
      }
      localStorage.removeItem(prefix + receipt.requestId);
      if (receipt.error && alive.current) setTaskError(receipt.taskId, receipt.error);
    }
    return record;
  };
  const reconcile = async (isCurrent = () => alive.current, force = true) => {
    const ids = JSON.parse(taskKey);
    let journal;
    try { journal = readJournal(); } catch { setError('请求备份暂不可读取，请保留当前内容。'); return; }
    for (const taskId of ids) {
      if (!isCurrent()) return;
      const pending = journal.some(item => item.taskId === taskId)
        || Object.values(recordsRef.current).some(item => item.taskId === taskId && active.has(item.status));
      // Read other clients' receipts when their task is selected. Idle tasks
      // need no background polling; the local journal still recovers every
      // unconfirmed request, including requests outside the visible task.
      if (!pending && taskId !== latest.current.activeTaskId) continue;
      const interval = pending ? 3000 : 15000;
      if (!force && Date.now() - (polledAt.current.get(taskId) || 0) < interval) continue;
      polledAt.current.set(taskId, Date.now());
      try {
        const receipts = await api.listOperations(taskId);
        if (!isCurrent()) return;
        setTaskError(taskId, '');
        for (const receipt of receipts) await publish(receipt, isCurrent);
        for (const intent of journal.filter(intent => intent.taskId === taskId && !receipts.some(receipt => receipt.requestId === intent.requestId))) {
          if (!isCurrent()) return;
          if (submitting.current.has(taskId)) continue;
          if (!intent.cancelRequested) {
            // A missing receipt does not prove the original submission was accepted.
            // Preserve the original identity and ask for an explicit continuation;
            // opening or refreshing the app must not start a fresh paid execution.
            setRecords(previous => ({ ...previous, [intent.requestId]: { ...previous[intent.requestId],
              ...intent, request: intent.input, status: 'awaiting_submission' } }));
            continue;
          }
          try { await publish(await api.cancelOperation(taskId, intent.requestId,
            { kind: intent.kind, input: intent.input }), isCurrent); }
          catch (failure) {
            if (failure.response?.status >= 400 && failure.response?.status < 500) {
              await publish({ ...intent, status: 'failed', error: failure.response?.data?.message || failure.message }, isCurrent);
            } else throw failure;
          }
        }
      } catch (failure) { if (isCurrent()) setTaskError(taskId, failure.response?.data?.message || failure.message || '请求状态暂不可读取'); }
    }
  };
  useEffect(() => {
    alive.current = true;
    let stopped = false;
    let timer;
    try {
      const pending = readJournal();
      const restored = [];
      for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (key?.startsWith(historyPrefix)) {
          try { restored.push(JSON.parse(localStorage.getItem(key))); } catch { /* Preserve unreadable records. */ }
        }
      }
      setRecords(previous => ({ ...previous, ...Object.fromEntries(restored.map(item => [item.requestId, item])),
        ...Object.fromEntries(pending.map(item => [item.requestId, { ...item, status: item.cancelRequested ? 'cancelling' : 'unknown' }])) }));
    } catch { setError('请求备份暂不可读取'); }
    const poll = async () => { await reconcile(() => !stopped, false); if (!stopped) timer = setTimeout(poll, 3000); };
    void poll();
    return () => { stopped = true; alive.current = false; clearTimeout(timer); };
  }, [taskKey, workspace.activeTaskId, api]);
  const start = async (task, kind, input) => {
    if (submitting.current.has(task.id) || Object.values(records).some(item => item.taskId === task.id && active.has(item.status))) return;
    submitting.current.add(task.id);
    const request = { taskId: task.id, requestId: crypto.randomUUID(), kind, input, createdAt: new Date().toISOString() };
    try { localStorage.setItem(prefix + request.requestId, JSON.stringify(request)); }
    catch { submitting.current.delete(task.id); setTaskError(task.id, '请求备份保存失败，请恢复本地存储后再开始。'); return; }
    setTaskError(task.id, '');
    setRecords(previous => ({ ...previous, [request.requestId]: { ...request, status: 'unknown' } }));
    try { return await publish(await api.startOperation(task.id, { requestId: request.requestId, kind, input })); }
    catch (failure) {
      setTaskError(task.id, failure.response?.data?.message || `${failure.message || '响应未确认'}。请求已备份，将按原请求标识核对。`);
      if (failure.response?.status >= 400 && failure.response?.status < 500) {
        await publish({ ...request, status: 'failed', rejectedBeforeScheduling: true, error: failure.response?.data?.message || failure.message });
      }
    } finally { submitting.current.delete(task.id); }
  };
  const retry = async (task, requestId) => {
    const previous = recordsRef.current[requestId];
    if (!previous || previous.taskId !== task.id || !retryable.has(previous.status)
        || submitting.current.has(task.id) || retrying.current.has(task.id)
        || Object.values(recordsRef.current).some(item => item.taskId === task.id && active.has(item.status))) return;
    retrying.current.add(task.id); setRetryingTasks(current => ({ ...current, [task.id]: true }));
    try {
      let confirmed;
      let rejectedLocally = false;
      try { confirmed = await api.getOperation(task.id, requestId); }
      catch (failure) {
        if (failure.response?.status !== 404 || !previous.rejectedBeforeScheduling) throw failure;
        confirmed = previous;
        rejectedLocally = true;
      }
      if (!retryable.has(confirmed.status)) {
        await publish(confirmed);
        return;
      }
      const currentTask = await api.getTask(task.id);
      if (!currentTask || currentTask.id !== task.id) throw new Error('任务状态未确认，请稍后重试');
      await latest.current.adoptServerTask(currentTask);
      const input = confirmed.request || previous.request;
      if (!input) throw new Error('原问题未保存，请重新输入');
      const scope = confirmed.paperIds || previous.paperIds || input.allowedPaperIds || (input.pdfId ? [input.pdfId] : []);
      if (scope.some(id => !currentTask.paperIds.includes(id))) throw new Error('原材料已移出任务，请先恢复材料或重新提出问题');
      // A lesson action answers one specific question. Do not retarget a saved
      // answer to a newer activity or a newer question after a concurrent edit.
      if (previous.kind === 'learning.action' && (input.activityId !== currentTask.activeActivity?.activityId
          || input.expectedRevision !== currentTask.activeActivity?.revision)) throw new Error('学习位置已变化，请回到当前问题继续');
      const replacement = rejectedLocally
        ? await start(currentTask, previous.kind, { ...input, expectedTaskRevision: currentTask.revision })
        : await publish(await api.retryOperation(task.id, requestId));
      if (replacement) {
        setRecords(current => ({ ...current, [requestId]: { ...current[requestId], retriedBy: replacement.requestId } }));
        const stored = { ...previous, retriedBy: replacement.requestId };
        localStorage.setItem(historyPrefix + requestId, JSON.stringify(stored));
      }
      return replacement;
    } catch (failure) { setTaskError(task.id, failure.response?.data?.message || failure.message || '重试未确认，请稍后查询'); }
    finally { retrying.current.delete(task.id); setRetryingTasks(current => ({ ...current, [task.id]: false })); }
  };
  const submitSaved = async (taskId, requestId) => {
    const record = recordsRef.current[requestId];
    if (record?.taskId !== taskId || record.status !== 'awaiting_submission'
        || submitting.current.has(taskId)
        || Object.values(recordsRef.current).some(item => item.taskId === taskId && active.has(item.status))) return;
    submitting.current.add(taskId);
    setTaskError(taskId, '');
    try {
      let receipt;
      try { receipt = await api.getOperation(taskId, requestId); }
      catch (failure) { if (failure.response?.status !== 404) throw failure; }
      if (receipt) return await publish(receipt);
      const intent = JSON.parse(localStorage.getItem(prefix + requestId) || 'null');
      if (intent?.taskId !== taskId || !intent.input || intent.cancelRequested)
        throw new Error('原问题无法恢复，请保留当前内容并查询状态。');
      setRecords(previous => ({ ...previous, [requestId]: { ...previous[requestId], status: 'unknown' } }));
      // The server checks the original material scope and revisions before execution.
      return await publish(await api.startOperation(taskId, { requestId, kind: intent.kind, input: intent.input }));
    } catch (failure) {
      setTaskError(taskId, failure.response?.data?.message || failure.message || '提交未确认，请查询状态。');
      if (failure.response?.status >= 400 && failure.response?.status < 500) {
        await publish({ ...record, status: 'failed', rejectedBeforeScheduling: true,
          error: failure.response?.data?.message || failure.message });
      }
    } finally { submitting.current.delete(taskId); }
  };
  const cancel = async (taskId, requestId = null) => {
    const taskRecords = Object.values(recordsRef.current).filter(item => item.taskId === taskId);
    const pending = requestId ? taskRecords.find(item => item.requestId === requestId &&
      (active.has(item.status) || item.status === 'awaiting_submission'))
      : taskRecords.find(item => active.has(item.status)) || taskRecords.find(item => item.status === 'awaiting_submission');
    if (!pending) return;
    try {
      const key = prefix + pending.requestId;
      const saved = JSON.parse(localStorage.getItem(key) || 'null');
      const input = pending.request || pending.input || saved?.input;
      if (input) localStorage.setItem(key, JSON.stringify({ taskId, requestId: pending.requestId,
        kind: pending.kind, input, cancelRequested: true }));
      setRecords(current => ({ ...current, [pending.requestId]: { ...current[pending.requestId], status: 'cancelling' } }));
      await publish(await api.cancelOperation(taskId, pending.requestId, input ? { kind: pending.kind, input } : {}));
    }
    catch (failure) { setTaskError(taskId, `${failure.message || '停止请求未确认'}。将继续核对后台状态。`); }
  };
  const busyTasks = { ...Object.fromEntries(Object.entries(retryingTasks).filter(([, value]) => value)),
    ...Object.fromEntries(Object.values(records).filter(item => active.has(item.status)).map(item => [item.taskId, true])) };
  const recoverResult = async (taskId, requestId) => {
    const receipt = await publish(await api.recoverOperationResult(taskId, requestId));
    setTaskError(taskId, '');
    return receipt;
  };
  return { start, retry, submitSaved, cancel, recoverResult, refresh: reconcile, busyTasks, records, error: errors[workspace.activeTaskId] || '' };
}
