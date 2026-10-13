import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConversationResearch, { ResearchCard } from './ConversationResearch';

const task = { id: 't', researchRuns: [{ researchId: 'r', question: '比较方法' }] };
beforeEach(() => localStorage.clear());
describe('research review in conversation', () => {
  it('requires a user action before approving the research plan', async () => {
    const action = vi.fn(async () => {});
    render(<ConversationResearch task={task} research={{ action, runs: { 't/r': {
      status: 'awaiting_plan_review', plan: [{ question: '方法的假设是什么？' }],
    } } }} />);
    expect(action).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: '研究问题列表' }), { target: { value: '实验是否公平？' } });
    fireEvent.click(screen.getByRole('button', { name: '按这些问题研究' }));
    await waitFor(() => expect(action).toHaveBeenCalledWith('t', 'r', 'plan-review', { subQuestions: ['实验是否公平？'], reviewNotes: '' }));
  });
  it('does not silently mark unresolved evidence risks as reviewed', async () => {
    const action = vi.fn(async () => {});
    render(<ConversationResearch task={task} research={{ action, runs: { 't/r': {
      status: 'awaiting_final_review', report: '结论', reviewRisks: [{ riskId: 'risk', label: '证据缺口', detail: '缺少对照' }],
    } } }} />);
    expect(screen.getByRole('button', { name: '确认并保存结果' })).toBeDisabled();
    fireEvent.change(screen.getByRole('combobox', { name: '核对：缺少对照' }), { target: { value: 'needs_follow_up' } });
    fireEvent.click(screen.getByRole('button', { name: '确认并保存结果' }));
    await waitFor(() => expect(action).toHaveBeenCalledWith('t', 'r', 'final-review', { reviewNotes: '', riskReviews: [{ riskId: 'risk', reviewStatus: 'needs_follow_up' }] }));
  });
  it('opens the full draft outside the conversation instead of expanding a long report inline', () => {
    const open = vi.fn();
    const result = { status: 'awaiting_final_review', report: '完整研究正文'.repeat(300), reviewRisks: [] };
    render(<ConversationResearch task={task} research={{ action: vi.fn(), runs: { 't/r': result } }} onOpenReport={open} />);
    expect(screen.queryByText(result.report)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '打开研究报告' }));
    expect(open).toHaveBeenCalledWith(task.researchRuns[0], result);
  });
});


it('renders a completed research as one saved report entry without full question or sources', () => {
  const open = vi.fn();
  const run = { researchId: 'finished', question: '完整研究问题'.repeat(20) };
  const result = { status: 'succeeded', title: '消融实验方案', report: '完整报告', findings: [{ sources: [{ title: '论文来源', text: '证据原文' }] }] };
  render(<ResearchCard taskId="t" run={run} result={result} onOpenReport={open} />);
  expect(screen.getByText('消融实验方案')).toBeInTheDocument();
  expect(screen.getByText('已保存')).toBeInTheDocument();
  expect(screen.queryByText(run.question)).not.toBeInTheDocument();
  expect(screen.queryByText('论文来源')).not.toBeInTheDocument();
  expect(screen.queryByText('完整报告')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '打开研究报告' }));
  expect(open).toHaveBeenCalledWith(run, result);
});

it('keeps an action failure local and permits an explicit retry', async () => {
  const action = vi.fn().mockRejectedValueOnce(new Error('计划保存失败')).mockResolvedValueOnce(undefined);
  render(<ResearchCard taskId="t" run={{ researchId: 'r', question: '长问题'.repeat(30) }} result={{ status: 'awaiting_plan_review', plan: ['实验公平吗？'] }} onAction={action} compactTitle="实验核对" />);
  expect(screen.getByText('实验核对')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '按这些问题研究' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('计划保存失败');
  fireEvent.click(screen.getByRole('button', { name: '按这些问题研究' }));
  await waitFor(() => expect(action).toHaveBeenCalledTimes(2));
});

it('restores an edited plan after leaving and reopening without starting research', () => {
  const action = vi.fn();
  const props = { taskId: 't', run: { researchId: 'r' }, result: { status: 'awaiting_plan_review', plan: ['原问题'] }, onAction: action };
  const first = render(<ResearchCard {...props} />);
  fireEvent.change(screen.getByRole('textbox', { name: '研究问题列表' }), { target: { value: '编辑后只做一个对照' } });
  first.unmount(); render(<ResearchCard {...props} />);
  expect(screen.getByRole('textbox', { name: '研究问题列表' })).toHaveValue('编辑后只做一个对照');
  expect(action).not.toHaveBeenCalled();
});

it('offers a status query at the affected research when its service cannot be read', () => {
  const refresh = vi.fn();
  render(<ResearchCard taskId="t" run={{ researchId: 'r' }} error={{ poll: '服务暂不可用' }} onRefresh={refresh} />);
  fireEvent.click(screen.getByText('研究状态需确认'));
  fireEvent.click(screen.getByRole('button', { name: '查询研究状态' }));
  expect(refresh).toHaveBeenCalledWith('t', 'r');
});
