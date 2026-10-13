import { useEffect, useRef, useState } from 'react';
import { taskWorkspaceApi } from '../services/taskWorkspaceApi';
import { useTaskOperations } from './useTaskOperations';

const readHandledDetours = () => {
  try { return new Set(JSON.parse(localStorage.getItem('pixiu-learning-handled-detours') || '[]')); }
  catch { return new Set(); }
};

export function useTaskLearning(workspace, api = taskWorkspaceApi) {
  const operations = useTaskOperations(workspace, api);
  const [inputModes, setInputModes] = useState(() => {
    try { return JSON.parse(localStorage.getItem('pixiu-learning-input-modes') || '{}'); } catch { return {}; }
  });
  useEffect(() => { try { localStorage.setItem('pixiu-learning-input-modes', JSON.stringify(inputModes)); } catch { /* Drafts and saved learning remain available. */ } }, [inputModes]);
  const handledDetours = useRef(readHandledDetours());
  const activityKey = task => `${task.id}:${task.activeActivity?.activityId || ''}`;
  const activeTask = workspace.tasks?.find(task => task.id === workspace.activeTaskId);
  const currentKey = activeTask ? activityKey(activeTask) : '';
  const concepts = activeTask?.activeActivity?.concepts || [];
  const completionSuggested = concepts.length > 0 && concepts.every(concept => concept.status === 'demonstrated');
  const inputMode = completionSuggested ? 'chat' : inputModes[currentKey] || 'chat';
  const setInputMode = mode => setInputModes(previous => ({ ...previous, [currentKey]: mode }));
  useEffect(() => {
    for (const record of Object.values(operations.records)) {
      if (record.kind !== 'learning.action' || record.status !== 'succeeded'
          || !['ask', 'answer'].includes(record.request?.action) || handledDetours.current.has(record.requestId)) continue;
      handledDetours.current.add(record.requestId);
      try { localStorage.setItem('pixiu-learning-handled-detours', JSON.stringify([...handledDetours.current])); } catch { /* Recovery remains available in the current session. */ }
      const key = `${record.taskId}:${record.request.activityId}`;
      // A successful answer or detour completes its turn; restore ordinary chat once.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setInputModes(previous => ({ ...previous, [key]: 'chat' }));
    }
  }, [operations.records]);
  const start = (task, pdfId, mode, goal) => {
    setInputModes(previous => ({ ...previous, [activityKey(task)]: 'chat' }));
    return operations.start(task, 'learning.start', { pdfId, mode, goal: goal || '理解论文的关键问题、方法和证据', expectedTaskRevision: task.revision });
  };
  const act = (task, action, text = '') => {
    if (action === 'resume' || action === 'retry') setInputModes(previous => ({ ...previous, [activityKey(task)]: action === 'retry' ? 'answer' : 'chat' }));
    return operations.start(task, 'learning.action', { activityId: task.activeActivity.activityId,
      expectedRevision: task.activeActivity.revision, expectedTaskRevision: task.revision, action, text });
  };
  return { start, act, refresh: operations.refresh, cancel: operations.cancel,
    busyTasks: operations.busyTasks, error: operations.error, inputMode, setInputMode, completionSuggested, operations };
}
