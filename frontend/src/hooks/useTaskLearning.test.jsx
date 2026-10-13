import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useTaskLearning } from './useTaskLearning';

beforeEach(() => localStorage.clear());
const setup = (task) => {
  const api = { listOperations: vi.fn(async () => []), startOperation: vi.fn(async (taskId, request) => ({taskId, ...request, status: 'running'})),
    cancelOperation: vi.fn(async (taskId, requestId) => ({taskId, requestId, status:'cancelling'})) };
  const workspace = { activeTaskId: task.id, tasks: [task], adoptServerTask: vi.fn(), updateTask: vi.fn() };
  return {api, workspace};
};
describe('durable task learning', () => {
  it('returns to ordinary chat after an explicit answer succeeds and never resubmits its receipt', async () => {
    const task = { id: 't', revision: 1, activeActivity: { activityId: 'a', revision: 0 } };
    const { api, workspace } = setup(task);
    const { result } = renderHook(() => useTaskLearning(workspace, api));
    act(() => result.current.setInputMode('answer'));
    await act(async () => result.current.act(task, 'answer', '剪枝删除冗余高斯'));
    expect(result.current.inputMode).toBe('answer');
    const request = api.startOperation.mock.calls[0][1];
    api.listOperations.mockResolvedValue([{ taskId: 't', requestId: request.requestId, kind: 'learning.action', request: request.input, status: 'succeeded', task }]);
    await act(async () => result.current.refresh());
    expect(result.current.inputMode).toBe('chat');
    act(() => result.current.setInputMode('answer'));
    await act(async () => result.current.refresh());
    expect(result.current.inputMode).toBe('answer');
    expect(api.startOperation).toHaveBeenCalledTimes(1);
  });
  it('defaults to ordinary chat during learning and after all concepts are demonstrated', () => {
    const task = { id:'t', revision:1, activeActivity:{ activityId:'a', revision:1, concepts:[{ id:'c', status:'demonstrated' }] } };
    const { api, workspace } = setup(task);
    const { result, rerender } = renderHook(({ current }) => useTaskLearning(current, api), { initialProps:{ current:workspace } });
    expect(result.current.completionSuggested).toBe(true);
    expect(result.current.inputMode).toBe('chat');
    rerender({ current:{ ...workspace, tasks:[{ ...task, activeActivity:{ ...task.activeActivity, concepts:[{ id:'c', status:'needs_review' }] } }] } });
    expect(result.current.completionSuggested).toBe(false);
    expect(result.current.inputMode).toBe('chat');
  });
  it('keeps detour input mode within its task and activity', async () => {
    const taskA = { id:'A', revision:1, activeActivity:{ activityId:'a1', revision:0 } };
    const taskB = { id:'B', revision:1, activeActivity:{ activityId:'b1', revision:0 } };
    const { api, workspace } = setup(taskA);
    workspace.tasks = [taskA, taskB];
    const { result, rerender } = renderHook(({ current }) => useTaskLearning(current, api), { initialProps:{ current:workspace } });
    act(() => result.current.setInputMode('ask'));
    rerender({ current:{ ...workspace, activeTaskId:'B' } });
    expect(result.current.inputMode).toBe('chat');
    rerender({ current:workspace });
    expect(result.current.inputMode).toBe('ask');
    rerender({ current:{ ...workspace, tasks:[{ ...taskA, activeActivity:{ activityId:'a2', revision:0 } }, taskB] } });
    expect(result.current.inputMode).toBe('chat');
  });
  it('returns to ordinary chat only after the detour succeeds, without replaying a model call', async () => {
    const task = { id:'t', revision:1, activeActivity:{ activityId:'a', revision:0 } };
    const { api, workspace } = setup(task);
    const { result } = renderHook(() => useTaskLearning(workspace, api));
    act(() => result.current.setInputMode('ask'));
    await act(async () => result.current.act(task, 'ask', '术语是什么意思？'));
    expect(result.current.inputMode).toBe('ask');
    const request = api.startOperation.mock.calls[0][1];
    api.listOperations.mockResolvedValue([{ taskId:'t', requestId:request.requestId, kind:'learning.action',
      request:request.input, status:'succeeded', task }]);
    await act(async () => result.current.refresh());
    expect(result.current.inputMode).toBe('chat');
    act(() => result.current.setInputMode('ask'));
    await act(async () => result.current.refresh());
    expect(result.current.inputMode).toBe('ask');
    expect(api.startOperation).toHaveBeenCalledTimes(1);
  });
  it('persists request identity before calling the service and uses the saved activity paper', async () => {
    const task = {id:'t', revision:8, focusedPaperId:'B', activeActivity:{activityId:'lesson',revision:2,pdfId:'A'}};
    const {api,workspace} = setup(task);
    api.startOperation.mockImplementation(async (taskId, request) => {
      expect(localStorage.getItem(`pixiu-task-request-v1:${request.requestId}`)).toContain('lesson');
      return {taskId, ...request, status:'running'};
    });
    const {result} = renderHook(() => useTaskLearning(workspace,api));
    await act(async () => result.current.act(task,'hint'));
    expect(api.startOperation).toHaveBeenCalledWith('t',expect.objectContaining({kind:'learning.action',input:{activityId:'lesson',expectedRevision:2,expectedTaskRevision:8,action:'hint',text:''}}));
    expect(result.current.busyTasks.t).toBe(true);
    await act(async () => result.current.cancel('t'));
    expect(result.current.busyTasks.t).toBe(true); // HTTP cancellation acknowledgement is not worker completion.
    expect(Object.values(result.current.operations.records)[0].status).toBe('cancelling');
  });

  it('restores ordinary-chat mode without replaying an already handled detour receipt', async () => {
    const task = { id: 't', activeActivity: { activityId: 'a', revision: 1 } };
    const { api, workspace } = setup(task);
    api.listOperations.mockResolvedValue([{ taskId: 't', requestId: 'past-detour', kind: 'learning.action', request: { activityId: 'a', action: 'ask' }, status: 'succeeded', task }]);
    const first = renderHook(() => useTaskLearning(workspace, api));
    await act(async () => first.result.current.refresh());
    act(() => first.result.current.setInputMode('chat'));
    first.unmount();
    const restored = renderHook(() => useTaskLearning(workspace, api));
    await act(async () => restored.result.current.refresh());
    expect(restored.result.current.inputMode).toBe('chat');
    expect(api.startOperation).not.toHaveBeenCalled();
  });
  it('waits for explicit continuation after a dropped response and submits the original identity only after a missing receipt', async () => {
    const task = {id:'t',revision:1};
    const {api,workspace} = setup(task);
    api.startOperation.mockRejectedValueOnce(new Error('timeout'));
    const {result} = renderHook(() => useTaskLearning(workspace,api));
    await act(async () => result.current.start(task,'A','read','学习目标'));
    const request = api.startOperation.mock.calls[0][1];
    const saved = {...task, revision:2, messages:[{id:request.requestId+':ai',content:'问题'}]};
    api.startOperation.mockResolvedValueOnce({taskId:'t',requestId:request.requestId,kind:'learning.start',status:'succeeded',task:saved});
    await act(async () => result.current.refresh());
    expect(api.startOperation).toHaveBeenCalledTimes(1);
    expect(result.current.operations.records[request.requestId].status).toBe('awaiting_submission');
    expect(localStorage.getItem(`pixiu-task-request-v1:${request.requestId}`)).not.toBeNull();
    api.getOperation = vi.fn().mockRejectedValue({response:{status:404}});
    await act(async () => result.current.operations.submitSaved('t', request.requestId));
    expect(api.getOperation).toHaveBeenCalledWith('t', request.requestId);
    expect(api.startOperation.mock.calls[1][1]).toEqual(request);
    expect(api.getOperation.mock.invocationCallOrder[0]).toBeLessThan(api.startOperation.mock.invocationCallOrder[1]);
    expect(workspace.adoptServerTask).toHaveBeenCalledWith(saved);
    expect(workspace.updateTask).not.toHaveBeenCalled();
    expect(localStorage.getItem(`pixiu-task-request-v1:${request.requestId}`)).toBeNull();
    expect(result.current.busyTasks.t).toBeUndefined();
  });
  it('adopts an already completed learning response on refresh without another submission', async () => {
    const task = {id:'t',revision:1};
    const {api,workspace} = setup(task);
    api.startOperation.mockRejectedValueOnce(new Error('timeout'));
    const {result} = renderHook(() => useTaskLearning(workspace,api));
    await act(async () => result.current.start(task,'A','read','学习目标'));
    const request = api.startOperation.mock.calls[0][1];
    const saved = {...task, revision:2, messages:[{id:request.requestId+':ai',content:'问题'}]};
    api.listOperations.mockResolvedValue([{taskId:'t',requestId:request.requestId,kind:'learning.start',status:'succeeded',task:saved}]);
    await act(async () => result.current.refresh());
    expect(api.startOperation).toHaveBeenCalledTimes(1);
    expect(workspace.adoptServerTask).toHaveBeenCalledWith(saved);
    expect(workspace.updateTask).not.toHaveBeenCalled();
    expect(localStorage.getItem(`pixiu-task-request-v1:${request.requestId}`)).toBeNull();
    expect(result.current.busyTasks.t).toBeUndefined();
  });
  it('recovers server operations after remount even without a local request journal', async () => {
    const task = {id:'t',revision:1};
    const {api,workspace} = setup(task);
    api.listOperations.mockResolvedValue([{taskId:'t',requestId:'other-client',kind:'learning.start',status:'running'}]);
    const {result} = renderHook(() => useTaskLearning(workspace,api));
    await act(async () => result.current.refresh());
    expect(result.current.busyTasks.t).toBe(true);
    expect(api.startOperation).not.toHaveBeenCalled();
  });
  it('does not repeat an interrupted provider request and preserves task identity after switching', async () => {
    const task = {id:'A',revision:1};
    const {api,workspace} = setup(task);
    api.listOperations.mockResolvedValue([{taskId:'A',requestId:'lost',kind:'learning.start',status:'interrupted',error:'结果未确认'}]);
    const {result} = renderHook(() => useTaskLearning(workspace,api));
    await act(async () => result.current.refresh());
    expect(result.current.error).toContain('结果未确认');
    expect(api.startOperation).not.toHaveBeenCalled();
    expect(workspace.adoptServerTask).not.toHaveBeenCalled();
  });
});
