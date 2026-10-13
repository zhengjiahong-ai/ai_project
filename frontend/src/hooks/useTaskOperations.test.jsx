import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useTaskOperations } from './useTaskOperations';

beforeEach(() => localStorage.clear());
afterEach(() => vi.useRealTimers());

it('clears a temporary query error once authoritative status can be read again', async () => {
  const api = { listOperations: vi.fn().mockRejectedValue(new Error('temporarily unavailable')) };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [{ id: 'A' }] }, api));
  await act(async () => { await result.current.refresh(); });
  expect(result.current.error).toContain('temporarily unavailable');
  api.listOperations.mockResolvedValue([]);
  await act(async () => { await result.current.refresh(); });
  expect(result.current.error).toBe('');
});

it('preserves a missing intent and only submits it after explicit continuation with the same ID', async () => {
  const intent = { taskId: 'A', requestId: 'missing', kind: 'learning.action', input: { action: 'pause' } };
  localStorage.setItem('pixiu-task-request-v1:missing', JSON.stringify(intent));
  const api = { listOperations: vi.fn(async () => [{ taskId: 'A', requestId: 'older', status: 'cancelled' }]),
    getOperation: vi.fn().mockRejectedValue({ response: { status: 404 } }),
    startOperation: vi.fn(async () => ({ ...intent, status: 'cancelled' })) };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [{ id: 'A' }] }, api));
  await act(async () => { await result.current.refresh(); });
  expect(api.startOperation).not.toHaveBeenCalled();
  expect(result.current.records.missing.status).toBe('awaiting_submission');
  expect(result.current.busyTasks.A).toBeUndefined();
  expect(localStorage.getItem('pixiu-task-request-v1:missing')).not.toBeNull();
  await act(async () => { await result.current.submitSaved('A', 'missing'); });
  expect(api.startOperation).toHaveBeenCalledWith('A', { requestId: 'missing', kind: intent.kind, input: intent.input });
  expect(result.current.error).toBe('');
  expect(localStorage.getItem('pixiu-task-request-v1:missing')).toBeNull();
});

it('adopts an existing receipt instead of submitting again after an explicit continuation', async () => {
  const intent = { taskId: 'A', requestId: 'r', kind: 'conversation.execute', input: { message: 'question' } };
  localStorage.setItem('pixiu-task-request-v1:r', JSON.stringify(intent));
  const api = { listOperations: vi.fn(async () => []), getOperation: vi.fn(async () => ({ ...intent, status: 'running' })), startOperation: vi.fn() };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [{ id: 'A' }] }, api));
  await act(async () => result.current.refresh());
  await act(async () => result.current.submitSaved('A', 'r'));
  expect(result.current.records.r.status).toBe('running');
  expect(api.startOperation).not.toHaveBeenCalled();
});

it('blocks duplicate saved submissions and keeps the original payload', async () => {
  const intent = { taskId: 'A', requestId: 'r', kind: 'conversation.execute', input: { message: 'original', allowedPaperIds: ['paper-A'], expectedTaskRevision: 4 } };
  localStorage.setItem('pixiu-task-request-v1:r', JSON.stringify(intent));
  let finish;
  const api = { listOperations: vi.fn(async () => []), getOperation: vi.fn().mockRejectedValue({ response: { status: 404 } }),
    startOperation: vi.fn(() => new Promise(resolve => { finish = resolve; })) };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [{ id: 'A' }] }, api));
  await act(async () => result.current.refresh());
  let pending;
  await act(async () => {
    pending = result.current.submitSaved('A', 'r');
    await result.current.submitSaved('A', 'r');
  });
  expect(api.startOperation).toHaveBeenCalledTimes(1);
  expect(api.startOperation).toHaveBeenCalledWith('A', { requestId: 'r', kind: intent.kind, input: intent.input });
  await act(async () => { finish({ ...intent, status: 'running' }); await pending; });
});

it('keeps delayed failure messages with their original task', async () => {
  let release;
  const api = { listOperations: vi.fn(async () => []), startOperation: vi.fn(() => new Promise((_, reject) => { release = reject; })) };
  const tasks = [{ id: 'A' }, { id: 'B' }];
  const { result, rerender } = renderHook(({ activeTaskId }) => useTaskOperations({ tasks, activeTaskId }, api), {
    initialProps: { activeTaskId: 'A' },
  });
  let request;
  await act(async () => { request = result.current.start(tasks[0], 'learning.start', {}); });
  rerender({ activeTaskId: 'B' });
  await act(async () => { release(new Error('A unavailable')); await request; });
  expect(result.current.error).toBe('');
  rerender({ activeTaskId: 'A' });
  expect(result.current.error).toContain('A unavailable');
  expect(localStorage.length).toBe(1);
});

it('does not poll idle historical tasks even with a large task inventory', async () => {
  vi.useFakeTimers();
  const api = { listOperations: vi.fn(async () => []) };
  const workspace = { activeTaskId: 'A', tasks: [{ id: 'A' }, ...Array.from({ length: 60 }, (_, i) => ({ id: `B${i}` }))], adoptServerTask: vi.fn() };
  const { unmount } = renderHook(() => useTaskOperations(workspace, api));
  await act(async () => { await vi.advanceTimersByTimeAsync(12000); });
  expect(api.listOperations.mock.calls.map(call => call[0])).toEqual(['A']);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.listOperations.mock.calls.map(call => call[0])).toEqual(['A', 'A']);
  unmount();
});

it('queries a newly selected task immediately and continues recovering background requests', async () => {
  vi.useFakeTimers();
  const intent = { taskId: 'C', requestId: 'pending-C', kind: 'conversation.execute', input: {} };
  localStorage.setItem('pixiu-task-request-v1:pending-C', JSON.stringify(intent));
  const api = { listOperations: vi.fn(async id => id === 'C' ? [{ ...intent, status: 'running' }] : []) };
  const tasks = [{ id: 'A' }, { id: 'B' }, { id: 'C' }, { id: 'idle' }];
  const { rerender, unmount } = renderHook(({ activeTaskId }) => useTaskOperations({ tasks, activeTaskId }, api), {
    initialProps: { activeTaskId: 'A' },
  });
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(api.listOperations.mock.calls.map(call => call[0])).toEqual(['A', 'C']);
  rerender({ activeTaskId: 'B' });
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(api.listOperations.mock.calls.map(call => call[0])).toEqual(['A', 'C', 'B']);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.listOperations.mock.calls.map(call => call[0])).toEqual(['A', 'C', 'B', 'C']);
  expect(api.listOperations).not.toHaveBeenCalledWith('idle');
  unmount();
});

it('ignores a late poll from a removed task after task inventory changes', async () => {
  let release;
  const oldResponse = new Promise(resolve => { release = resolve; });
  const api = { listOperations: vi.fn(id => id === 'A' ? oldResponse : Promise.resolve([])), startOperation: vi.fn() };
  const adoptServerTask = vi.fn();
  const { result, rerender } = renderHook(({ tasks }) => useTaskOperations({ tasks, activeTaskId: tasks[0]?.id, adoptServerTask }, api), {
    initialProps: { tasks: [{ id: 'A' }] },
  });
  rerender({ tasks: [{ id: 'B' }] });
  await act(async () => release([{ taskId: 'A', requestId: 'old', status: 'succeeded', task: { id: 'A', revision: 2 } }]));
  expect(adoptServerTask).not.toHaveBeenCalled();
  expect(result.current.records.old).toBeUndefined();
  expect(api.startOperation).not.toHaveBeenCalled();
});

it('preserves the pending journal when an unmounted poll eventually succeeds', async () => {
  localStorage.setItem('pixiu-task-request-v1:r', JSON.stringify({ taskId: 'A', requestId: 'r', kind: 'learning.start', input: {} }));
  let release;
  const api = { listOperations: vi.fn(() => new Promise(resolve => { release = resolve; })), startOperation: vi.fn() };
  const adoptServerTask = vi.fn();
  const { unmount } = renderHook(() => useTaskOperations({ tasks: [{ id: 'A' }], adoptServerTask }, api));
  unmount();
  await act(async () => release([{ taskId: 'A', requestId: 'r', status: 'succeeded', task: { id: 'A' } }]));
  expect(localStorage.getItem('pixiu-task-request-v1:r')).not.toBeNull();
  expect(adoptServerTask).not.toHaveBeenCalled();
});

it('retries a confirmed failure through the server identity and preserves its original scope', async () => {
  const failed = { taskId: 'A', requestId: 'old', kind: 'conversation.execute', status: 'failed', paperIds: ['paper'],
    request: { capability: 'chat', message: 'original question', allowedPaperIds: ['paper'], expectedTaskRevision: 1 } };
  const currentTask = { id: 'A', revision: 3, paperIds: ['paper', 'new-paper'] };
  const api = { listOperations: vi.fn(async () => [failed]), getOperation: vi.fn(async () => failed),
    getTask: vi.fn(async () => currentTask), retryOperation: vi.fn(async () => ({ ...failed, requestId: 'retry', retryOf: 'old', status: 'queued' })) };
  const adoptServerTask = vi.fn();
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [currentTask], adoptServerTask }, api));
  await act(async () => { await result.current.refresh(); });
  await act(async () => { await result.current.retry(currentTask, 'old'); });
  expect(api.retryOperation).toHaveBeenCalledTimes(1);
  expect(api.retryOperation).toHaveBeenCalledWith('A', 'old');
  expect(result.current.records.old.retriedBy).toBe('retry');
  expect(result.current.records.retry.request.allowedPaperIds).toEqual(['paper']);
  expect(result.current.busyTasks.A).toBe(true);
});

it('does not retry an unconfirmed request or retarget a saved answer to a new learning question', async () => {
  const failed = { taskId: 'A', requestId: 'old', kind: 'learning.action', status: 'failed', paperIds: ['paper'],
    request: { activityId: 'lesson', expectedRevision: 1, action: 'answer', text: 'old answer' } };
  const currentTask = { id: 'A', revision: 3, paperIds: ['paper'], activeActivity: { activityId: 'lesson', revision: 2 } };
  const api = { listOperations: vi.fn(async () => [failed]), getOperation: vi.fn(async () => failed),
    getTask: vi.fn(async () => currentTask), retryOperation: vi.fn() };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [currentTask], adoptServerTask: vi.fn() }, api));
  await act(async () => { await result.current.refresh(); });
  await act(async () => { await result.current.retry(currentTask, 'old'); });
  expect(api.retryOperation).not.toHaveBeenCalled();
  expect(result.current.error).toContain('学习位置已变化');
  api.getOperation.mockResolvedValue({ ...failed, status: 'running' });
  await act(async () => { await result.current.retry(currentTask, 'old'); });
  expect(api.retryOperation).not.toHaveBeenCalled();
  expect(result.current.records.old.status).toBe('running');
});

it('keeps the failure intent across refresh even after removing the pending journal', async () => {
  const failed = { taskId: 'A', requestId: 'old', kind: 'conversation.execute', status: 'failed', error: 'failure' };
  const intent = { taskId: 'A', requestId: 'old', kind: failed.kind, input: { message: 'keep this', allowedPaperIds: ['paper'] } };
  localStorage.setItem('pixiu-task-request-v1:old', JSON.stringify(intent));
  const api = { listOperations: vi.fn(async () => [failed]) };
  const workspace = { activeTaskId: 'A', tasks: [{ id: 'A' }] };
  const first = renderHook(() => useTaskOperations(workspace, api));
  await act(async () => { await first.result.current.refresh(); });
  expect(localStorage.getItem('pixiu-task-request-v1:old')).toBeNull();
  first.unmount();
  const second = renderHook(() => useTaskOperations(workspace, api));
  await act(async () => { await second.result.current.refresh(); });
  expect(second.result.current.records.old.request.message).toBe('keep this');
});

it('restores a pending stop by cancelling the same identity instead of submitting it', async () => {
  const intent = { taskId: 'A', requestId: 'lost', kind: 'conversation.execute', input: { message: 'question' }, cancelRequested: true };
  localStorage.setItem('pixiu-task-request-v1:lost', JSON.stringify(intent));
  const api = { listOperations: vi.fn(async () => []), startOperation: vi.fn(),
    cancelOperation: vi.fn(async () => ({ taskId: 'A', requestId: 'lost', kind: intent.kind, status: 'cancelled' })) };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [{ id: 'A' }] }, api));
  await act(async () => { await result.current.refresh(); });
  expect(api.startOperation).not.toHaveBeenCalled();
  expect(api.cancelOperation).toHaveBeenCalledWith('A', 'lost', { kind: intent.kind, input: intent.input });
  expect(result.current.records.lost.status).toBe('cancelled');
  expect(localStorage.getItem('pixiu-task-request-v1:lost')).toBeNull();
});

it('persists a stop even if its response is lost and prevents a late queued response from reviving it', async () => {
  let release;
  const input = { message: 'question' };
  const api = { listOperations: vi.fn(async () => []), startOperation: vi.fn(() => new Promise(resolve => { release = resolve; })),
    cancelOperation: vi.fn().mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValue({ taskId: 'A', requestId: 'lost', status: 'cancelled' }) };
  const { result } = renderHook(() => useTaskOperations({ activeTaskId: 'A', tasks: [{ id: 'A' }] }, api));
  let submission;
  await act(async () => { submission = result.current.start({ id: 'A' }, 'conversation.execute', input); });
  const id = Object.keys(result.current.records)[0];
  await act(async () => { await result.current.cancel('A'); });
  expect(JSON.parse(localStorage.getItem('pixiu-task-request-v1:' + id)).cancelRequested).toBe(true);
  api.cancelOperation.mockResolvedValue({ taskId: 'A', requestId: id, status: 'cancelled' });
  await act(async () => { release({ taskId: 'A', requestId: id, kind: 'conversation.execute', status: 'queued' }); await submission; });
  expect(result.current.records[id].status).toBe('cancelled');
  expect(api.cancelOperation).toHaveBeenCalledTimes(2);
});
