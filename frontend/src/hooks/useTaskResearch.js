import { useEffect, useRef, useState } from 'react';
import { taskResearchApi } from '../services/taskResearchApi';
import { clearResearchIntent, getResearchIntent, researchIntentKey } from '../services/researchStartIntent';

const terminal = new Set(['succeeded', 'completed', 'failed', 'cancelled']);
export function useTaskResearch(workspace, api = taskResearchApi, operations = null) {
  const [runs, setRuns] = useState({});
  const [errors, setErrors] = useState({});
  const setRunError = (key, channel, message) => setErrors(previous => ({
    ...previous, [key]: { ...previous[key], [channel]: message },
  }));
  const visibleTaskId = workspace.activeTaskId || workspace.tasks[0]?.id;
  const error = Object.entries(errors).filter(([key]) => {
    try { return JSON.parse(key)[0] === visibleTaskId; }
    catch { return false; } // Ignore old transient keys retained by development hot reload.
  })
    .map(([, value]) => value.action || value.poll).find(Boolean) || '';
  const [starting, setStarting] = useState(false);
  const latest = useRef(workspace);
  latest.current = workspace;
  const finished = useRef(new Set());
  const actionVersions = useRef(new Map());
  const pendingActions = useRef(new Set());
  const runRevisions = useRef(new Map());
  const startingRef = useRef(false);
  const startIntents = useRef(new Map());
  // Server publication can reorder tasks by updatedAt. Membership, not that
  // incidental order, controls poll lifetime; otherwise older GETs repeatedly
  // restart the loop before recent runs are ever reached.
  const runKey = JSON.stringify(workspace.tasks.flatMap((task) => (task.researchRuns || []).map((run) => [task.id, run.researchId]))
    .sort(([ta, ra], [tb, rb]) => ta.localeCompare(tb) || ra.localeCompare(rb)));
  const publish = async (taskId, researchId, result, isCurrent = () => true) => {
    if (!isCurrent()) return null;
    const research = result?.task;
    if (!research || (research.runId || research.taskId) !== researchId
      || (research.contractVersion === 2 && research.runId && research.taskId !== taskId)) throw new Error('研究服务返回的任务不匹配');
    const key = `${taskId}/${researchId}`;
    const revision = research.runRevision ?? research.revision;
    if (research.contractVersion === 2 && Number.isInteger(revision) && revision < (runRevisions.current.get(key) ?? -1)) return null;
    if (result.workspace) {
      if (result.workspace.id !== taskId) throw new Error('研究成果返回的任务不匹配');
      await latest.current.adoptServerTask(result.workspace);
    } else if (research.status === 'succeeded' || (research.status === 'completed' && research.outcome !== 'none')) {
      throw new Error('研究已完成，成果保存尚未确认，请重新查询');
    }
    if (!isCurrent()) return null;
    if (research.contractVersion === 2 && Number.isInteger(revision)) runRevisions.current.set(key, revision);
    setRuns((previous) => ({ ...previous, [key]: research }));
    if (terminal.has(research.status)) finished.current.add(key);
    else finished.current.delete(key);
    return research;
  };
  useEffect(() => {
    let disposed = false;
    let timer;
    const poll = async () => {
      const ordered = [...latest.current.tasks].sort((a, b) => Number(b.id === visibleTaskId) - Number(a.id === visibleTaskId));
      const queue = ordered.flatMap(task => [...(task.researchRuns || [])].reverse().map(run => [task.id, run.researchId]));
      let cursor = 0;
      const worker = async () => {
        while (!disposed && cursor < queue.length) {
          const [taskId, researchId] = queue[cursor++];
          const key = `${taskId}/${researchId}`;
          if (disposed || finished.current.has(key) || pendingActions.current.has(key)) continue;
          const version = actionVersions.current.get(key) || 0;
          const isCurrent = () => !disposed && !pendingActions.current.has(key)
            && (actionVersions.current.get(key) || 0) === version;
          try {
            const response = await api.get(taskId, researchId);
            if (!isCurrent()) continue;
            await publish(taskId, researchId, response, isCurrent);
            if (isCurrent()) setRunError(JSON.stringify([taskId, researchId]), 'poll', '');
          } catch (failure) { if (isCurrent()) {
            const missing = failure.response?.status === 404;
            if (missing) finished.current.add(key);
            setRunError(JSON.stringify([taskId, researchId]), 'poll', missing
              ? '执行记录当前不可用；已保存的成果仍可查看。' : failure.message || '研究状态读取失败');
          } }
        }
      };
      // A slow historical request must not block the currently visible run.
      // Bound concurrency instead of issuing one request per saved research.
      await Promise.all(Array.from({ length: Math.min(3, queue.length) }, worker));
      if (!disposed) timer = setTimeout(poll, 4000);
    };
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [runKey, api, visibleTaskId]);
  const start = async (task, question, context) => {
    const v2 = context.engineVersion ? context.engineVersion === 'deep-research-v2' : import.meta.env.VITE_DEEP_RESEARCH_V2_ENABLED === 'true';
    if (operations && !v2) return operations.start(task, 'research.start', { question, allowedPaperIds: context.allowedPaperIds,
      pdfId: context.primaryPaperId || task.focusedPaperId || context.allowedPaperIds[0],
      expectedTaskRevision: task.revision, allowExternalSearch: false, allowWebSearch: false });
    if (startingRef.current) return;
    startingRef.current = true; setStarting(true); setRunError(JSON.stringify([task.id, '$start']), 'action', '');
    try {
      if (v2) {
        const input = { question, engineVersion: 'deep-research-v2', contractVersion: 2,
          materialSelection: { mode: context.allowedPaperIds.length ? 'explicit' : 'external_only', materialIds: context.allowedPaperIds },
          focusPaperIds: context.primaryPaperId ? [context.primaryPaperId] : [],
          sourcePolicy: context.sourcePolicy || { mode: 'task_only' },
          ...(context.contextRefs?.length ? { contextRefs: context.contextRefs } : {}),
          budgetProfile: context.budgetProfile || 'standard', outputKind: context.outputKind || 'general',
          expectedTaskRevision: task.revision };
        const intentKey = researchIntentKey(task.id, input);
        const intent = startIntents.current.get(intentKey) || getResearchIntent(intentKey, input);
        startIntents.current.set(intentKey, intent);
        const response = await api.start(task.id, { ...intent.input, requestId: intent.requestId });
        if (!response?.workspace || response.workspace.id !== task.id) throw new Error('研究创建结果未确认，请查询任务记录');
        await publish(task.id, response.task?.runId, response);
        startIntents.current.delete(intentKey);
        clearResearchIntent(intentKey);
        return response;
      }
      const response = await api.start(task.id, { question, allowedPaperIds: context.allowedPaperIds,
        pdfId: context.primaryPaperId || task.focusedPaperId || context.allowedPaperIds[0],
        expectedTaskRevision: task.revision, allowExternalSearch: false, allowWebSearch: false });
      await latest.current.adoptServerTask(response.task);
      await publish(task.id, response.result.task.taskId, response.result);
    } catch (failure) {
      setRunError(JSON.stringify([task.id, '$start']), 'action', failure.message || '研究创建失败');
      if (v2) throw failure;
    }
    finally { startingRef.current = false; setStarting(false); }
  };
  const action = async (taskId, researchId, name, payload) => {
    // An explicit action may reopen a finished run or have an uncertain result.
    // Resume GET recovery; never resubmit the action automatically.
    const key = `${taskId}/${researchId}`;
    const version = (actionVersions.current.get(key) || 0) + 1;
    actionVersions.current.set(key, version);
    pendingActions.current.add(key);
    finished.current.delete(key);
    const isCurrent = () => actionVersions.current.get(key) === version;
    setRunError(JSON.stringify([taskId, researchId]), 'action', '');
    const actionIntentKey = name === 'continue' && payload?.materialSelection && payload.requestId
      ? JSON.stringify(['research-action', taskId, researchId, name, payload.requestId]) : null;
    try {
      const actionPayload = actionIntentKey ? getResearchIntent(actionIntentKey, { ...payload,
        expectedTaskRevision: latest.current.tasks?.find(task => task.id === taskId)?.revision }).input : payload;
      const response = await api.action(taskId, researchId, name, actionPayload);
      if (name === 'continue' && response?.task?.contractVersion === 2 && response.task.runId !== researchId) {
        if (response.task.parentRunId !== researchId || !response.workspace?.researchRuns?.some(run => (run.runId || run.researchId) === response.task.runId)) {
          throw new Error('后续研究的任务绑定未确认');
        }
        await publish(taskId, response.task.runId, response, isCurrent);
      } else await publish(taskId, researchId, response, isCurrent);
      if (actionIntentKey) clearResearchIntent(actionIntentKey);
    }
    catch (failure) {
      if (isCurrent()) setRunError(JSON.stringify([taskId, researchId]), 'action', failure.message || '研究操作失败');
      if (payload?.expectedRunRevision !== undefined) throw failure;
    }
    finally { if (isCurrent()) pendingActions.current.delete(key); }
  };
  const refresh = async (taskId, researchId) => {
    const key = `${taskId}/${researchId}`;
    const version = actionVersions.current.get(key) || 0;
    const isCurrent = () => !pendingActions.current.has(key) && (actionVersions.current.get(key) || 0) === version;
    try {
      await publish(taskId, researchId, await api.get(taskId, researchId), isCurrent);
      if (isCurrent()) setRunError(JSON.stringify([taskId, researchId]), 'poll', '');
    } catch (failure) { if (isCurrent()) setRunError(JSON.stringify([taskId, researchId]), 'poll', failure.message || '研究状态读取失败'); }
  };
  return { runs, start, action, refresh, starting, error, errors };
}
