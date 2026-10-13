import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ConversationExecution, { OperationRecord } from './ConversationExecution';

it('shows concise failure recovery with original question and folded details', () => {
  const retry = vi.fn();
  render(<ConversationExecution task={{ id: 'task' }} records={{ failed: { taskId: 'task', requestId: 'failed', status: 'failed',
    request: { message: 'original question' }, error: 'long diagnostic' } }} onRetry={retry} />);
  expect(screen.getByText('original question')).toBeInTheDocument();
  expect(screen.getByText('long diagnostic').closest('details')).not.toHaveAttribute('open');
  fireEvent.click(screen.getByRole('button', { name: '重试' }));
  expect(retry).toHaveBeenCalledWith('failed');
});

it('offers status checking and stopping instead of retry while the result is unconfirmed', () => {
  render(<ConversationExecution task={{ id: 'task' }} records={{ pending: { taskId: 'task', requestId: 'pending', status: 'unknown' } }} />);
  expect(screen.getByText('暂时无法确认结果')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查询状态' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
});

it('keeps normal processing compact and moves manual checking behind more actions', () => {
  const cancel = vi.fn(), refresh = vi.fn();
  render(<OperationRecord record={{ requestId: 'running-id', status: 'running' }} onCancel={cancel} onRefresh={refresh} />);
  expect(screen.getAllByRole('status')).toHaveLength(1);
  expect(screen.queryByRole('button', { name: '查询状态' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '停止', exact: true }));
  expect(cancel).toHaveBeenCalledExactlyOnceWith('running-id');
  fireEvent.click(screen.getByRole('button', { name: '请求更多操作' }));
  fireEvent.click(screen.getByRole('button', { name: '查询状态' }));
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('does not offer paid retry for a generated result that could not be applied', () => {
  const open = vi.fn();
  const record = { taskId: 'task', requestId: 'conflict', status: 'conflicted', result: { artifact: { text: 'complete report' } } };
  render(<ConversationExecution task={{ id: 'task' }} records={{ conflict: record }} onOpenResult={open} />);
  fireEvent.click(screen.getByRole('button', { name: '打开已生成结果' }));
  expect(open).toHaveBeenCalledWith(record);
  expect(screen.queryByText('complete report')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
});

it('keeps an unsubmitted intent behind an explicit continue action and cancels its own ID', () => {
  const submit = vi.fn(), cancel = vi.fn();
  render(<ConversationExecution task={{ id: 'A' }} records={{ r: { taskId: 'A', requestId: 'r', status: 'awaiting_submission',
    request: { message: '原问题' } } }} onSubmitSaved={submit} onCancel={cancel} />);
  expect(screen.getByText('暂时无法确认结果')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '继续发送' }));
  expect(submit).toHaveBeenCalledWith('r');
  fireEvent.click(screen.getByRole('button', { name: '停止' }));
  expect(cancel).toHaveBeenCalledWith('r');
  expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
});


it('can render one completed request without repeating its question and locate the original message', () => {
  const locate = vi.fn();
  const record = { requestId: 'done', status: 'succeeded', request: { message: '原问题' } };
  render(<OperationRecord record={record} showQuestion={false} onLocate={locate} />);
  expect(screen.getByText('已完成')).toBeInTheDocument();
  expect(screen.queryByText('原问题')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '打开对应对话' }));
  expect(locate).toHaveBeenCalledWith(record);
});

it('keeps asynchronous recovery errors local instead of creating another request', async () => {
  const retry = vi.fn().mockRejectedValue(new Error('原请求状态尚未确认'));
  render(<OperationRecord record={{ requestId: 'failed', status: 'failed', request: { message: '原问题' } }} onRetry={retry} />);
  expect(retry).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '重试' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('原请求状态尚未确认'));
  expect(retry).toHaveBeenCalledTimes(1);
});
