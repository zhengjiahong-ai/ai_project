import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TaskDraftRecovery, { recoveryTask } from './TaskDraftRecovery';

const snapshot = { id: 'old', title: '研究', revision: 3, paperIds: ['a'],
  messages: [{ role: 'ai', content: '未保存的答案', context: { taskId: 'old', allowedPaperIds: ['a'] } }],
  notes: [{ title: '我的总结', text: '笔记正文' }], artifacts: [], activeActivity: { id: 'lesson', taskId: 'old', status: 'active' } };
const version = { task: snapshot, reason: 'conflict', savedAt: '2026-10-04T00:00:00Z' };

describe('draft recovery', () => {
  it('finds a failed new task draft after refresh even when there is no active task', async () => {
    const store = { listUnsyncedDrafts: vi.fn(async () => [version]) };
    render(<TaskDraftRecovery taskId={null} store={store} onCreateTask={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '未同步草稿' }));
    expect(screen.getByText('未保存的答案', { exact: false })).toBeInTheDocument();
  });
  it('copies material and dialogue provenance into a new task without overwriting the original', () => {
    const copy = recoveryTask(snapshot, 'new');
    expect(copy.id).toBe('new');
    expect(copy.revision).toBeUndefined();
    expect(copy.messages[0].context.taskId).toBe('new');
    expect(copy.activeActivity.status).toBe('paused');
    expect(snapshot.activeActivity.status).toBe('active');
    expect(snapshot.messages[0].context.taskId).toBe('old');
  });
  it('previews a retained answer and creates a copy only on request', async () => {
    const store = { getUnsyncedDraft: vi.fn(async () => ({ ...version, versions: [version] })), clearUnsyncedDraft: vi.fn() };
    const create = vi.fn(async () => ({}));
    render(<TaskDraftRecovery taskId="old" store={store} onCreateTask={create} />);
    fireEvent.click(await screen.findByRole('button', { name: '未同步草稿' }));
    expect(screen.getByText('未保存的答案', { exact: false })).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '复制为新任务' }));
    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(create.mock.calls[0][0].id).not.toBe('old');
    expect(store.clearUnsyncedDraft).not.toHaveBeenCalled();
  });
  it('preserves the draft and shows failure when the copy cannot reach the server', async () => {
    const store = { getUnsyncedDraft: vi.fn(async () => version) };
    render(<TaskDraftRecovery taskId="old" store={store} onCreateTask={vi.fn(async () => { throw new Error('服务不可用'); })} />);
    fireEvent.click(await screen.findByRole('button', { name: '未同步草稿' }));
    fireEvent.click(screen.getByRole('button', { name: '复制为新任务' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('服务不可用');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
