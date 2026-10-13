import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useTaskWorkspace } from './useTaskWorkspace';

const task = (id) => ({ id, title: id, paperIds: [], messages: [], notes: [], artifacts: [], updatedAt: 0 });
const makeStore = () => ({ listTasks: vi.fn(async () => [task('a'), task('b')]),
  createTask: vi.fn(async (input) => ({ ...task('new'), ...input })),
  saveTask: vi.fn(async (value) => value) });

describe('task workspace updates', () => {
  beforeEach(() => localStorage.clear());

  it('restores the selected task on remount and ignores a removed task preference', async () => {
    const store = makeStore();
    const first = renderHook(() => useTaskWorkspace(store));
    await waitFor(() => expect(first.result.current.ready).toBe(true));
    act(() => first.result.current.selectTask('b'));
    first.unmount();
    const second = renderHook(() => useTaskWorkspace(store));
    await waitFor(() => expect(second.result.current.ready).toBe(true));
    expect(second.result.current.activeTaskId).toBe('b');
    second.unmount();
    store.listTasks.mockResolvedValueOnce([task('a')]);
    const third = renderHook(() => useTaskWorkspace(store));
    await waitFor(() => expect(third.result.current.ready).toBe(true));
    expect(third.result.current.activeTaskId).toBe('a');
  });
  it('keeps late responses in their originating task after switching', async () => {
    const store = makeStore();
    const { result } = renderHook(() => useTaskWorkspace(store));
    await waitFor(() => expect(result.current.ready).toBe(true));
    act(() => result.current.selectTask('b'));
    await act(async () => { await result.current.updateTask('a', (previous) => ({ messages: [...previous.messages, { content: 'A result' }] })); });
    expect(result.current.activeTask.id).toBe('b');
    expect(result.current.activeTask.messages).toEqual([]);
    expect(result.current.tasks.find((item) => item.id === 'a').messages[0].content).toBe('A result');
  });

  it('serializes concurrent changes and persists an empty conversation', async () => {
    const store = makeStore();
    const { result } = renderHook(() => useTaskWorkspace(store));
    await waitFor(() => expect(result.current.ready).toBe(true));
    await act(async () => {
      await Promise.all(['first', 'second'].map((content) => result.current.updateTask('a', (previous) => ({ messages: [...previous.messages, { content }] }))));
    });
    expect(result.current.activeTask.messages.map((item) => item.content)).toEqual(['first', 'second']);
    await act(async () => { await result.current.updateTask('a', { messages: [] }); });
    expect(store.saveTask.mock.calls.at(-1)[0].messages).toEqual([]);
  });

  it('does not present failed persistence as saved and allows a later retry', async () => {
    const store = makeStore();
    const { result } = renderHook(() => useTaskWorkspace(store));
    await waitFor(() => expect(result.current.ready).toBe(true));
    store.saveTask.mockRejectedValueOnce(new Error('disk full'));
    await act(async () => { await expect(result.current.updateTask('a', { title: 'unsaved' })).rejects.toThrow('disk full'); });
    expect(result.current.activeTask.title).toBe('a');
    expect(result.current.error).toBe('disk full');
    await act(async () => { await result.current.updateTask('a', { title: 'saved' }); });
    expect(result.current.activeTask.title).toBe('saved');
    expect(result.current.error).toBe('');
  });
});
