import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskProcessingHistory from './TaskProcessingHistory';

const run = { researchId: 'research', question: '剪枝实验方案' };
const task = { id: 't', researchRuns: [run] };
const done = { taskId: 't', requestId: 'done', status: 'succeeded', request: { message: '解释注意力' } };
const failed = { taskId: 't', requestId: 'failed', status: 'failed', request: { message: '比较方法' }, error: '网络中断' };
const records = { done, failed, other: { taskId: 'other', requestId: 'other', status: 'failed', request: { message: '别的任务' } } };
const result = { status: 'succeeded', title: '剪枝实验方案', report: '报告正文' };
const research = { action: vi.fn(), runs: { 't/research': result } };

it('searches and filters all task requests and research, including successful history', () => {
  render(<TaskProcessingHistory task={task} records={records} research={research} />);
  expect(screen.getByText('3 条处理记录')).toBeInTheDocument();
  expect(screen.queryByText('别的任务')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('搜索处理记录'), { target: { value: '剪枝' } });
  expect(screen.getByText('1 条处理记录')).toBeInTheDocument();
  expect(screen.queryByText('解释注意力')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('搜索处理记录'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('处理状态筛选'), { target: { value: 'failed' } });
  expect(screen.getByText('1 条处理记录')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '比较方法' })).toBeInTheDocument();
});

it('locates original entries and reuses request recovery without automatic retries', () => {
  const locate = vi.fn(), locateResearch = vi.fn(), retry = vi.fn(), open = vi.fn();
  render(<TaskProcessingHistory task={task} records={records} research={research} onLocateOperation={locate} onLocateResearch={locateResearch} onRetry={retry} onOpenReport={open} />);
  expect(retry).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '解释注意力' }));
  expect(locate).toHaveBeenCalledWith(done);
  fireEvent.click(screen.getByRole('button', { name: '剪枝实验方案' }));
  expect(locateResearch).toHaveBeenCalledWith(run);
  const failureRow = screen.getByRole('button', { name: '比较方法' }).closest('article');
  fireEvent.click(within(failureRow).getByRole('button', { name: '重试' }));
  expect(retry).toHaveBeenCalledWith('failed');
  fireEvent.click(screen.getByRole('button', { name: '打开研究报告' }));
  expect(open).toHaveBeenCalledWith(run, result);
  expect(screen.queryByText('报告正文')).not.toBeInTheDocument();
});

it('names learning actions for users and represents the research creation once', () => {
  const task = { id: 't', researchRuns: [{ ...run, requestId: 'start' }] };
  render(<TaskProcessingHistory task={task} records={{
    start: { taskId: 't', requestId: 'start', kind: 'research.start', status: 'succeeded', request: { question: '剪枝实验方案' } },
    pause: { taskId: 't', requestId: 'pause', kind: 'learning.action', status: 'succeeded', request: { action: 'pause' } },
  }} research={research} />);
  expect(screen.getByText('2 条处理记录')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '暂停学习' })).toBeInTheDocument();
  expect(screen.queryByText('learning.action')).not.toBeInTheDocument();
});
