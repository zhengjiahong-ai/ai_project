import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ResearchResultCard from './ResearchResultCard';

const props = { taskId: 't', run: { researchId: 'r' }, result: {
  contractVersion: 2, runRevision: 4, status: 'running', outcome: 'none', title: '对照实验设计',
  activity: { label: '核对消融实验' }, allowedActions: ['cancel'], plan: [{ itemId: 'p', question: '区分两个因素' }],
} };

describe('versioned research result', () => {
  it('does not repeat a long user request as the card heading', () => {
    render(<ResearchResultCard {...props} result={{ ...props.result, title: '研究质量并明确说明所有适用条件。'.repeat(8), outputKind: 'claim_verification' }} />);
    expect(screen.getByText('主张核查')).toBeInTheDocument();
    expect(screen.queryByText(/研究质量并明确说明所有适用条件/)).not.toBeInTheDocument();
  });
  it('renders structured failures and a versioned plan without crashing', () => {
    render(<ResearchResultCard {...props} result={{ ...props.result, status: 'paused',
      error: { code: 'unknown_call', message: '上次调用结果未确认' },
      plan: { revision: 2, items: [{ itemId: 'p', question: '核对实验条件' }] } }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('上次调用结果未确认');
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(screen.getByText('核对实验条件')).toBeInTheDocument();
  });
  it('keeps progress compact and exposes only server-authorized actions', () => {
    render(<ResearchResultCard {...props} onAction={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('正在研究');
    expect(screen.getByText('核对消融实验')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '继续研究' })).not.toBeInTheDocument();
    expect(screen.queryByText('区分两个因素')).not.toBeInTheDocument();
  });

  it('closes details with Escape and restores focus to the trigger', () => {
    render(<ResearchResultCard {...props} />);
    const trigger = screen.getByRole('button', { name: '详情' });
    fireEvent.click(trigger);
    expect(screen.getByText('区分两个因素')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('region', { name: '研究详情' }), { key: 'Escape' });
    expect(screen.queryByRole('region', { name: '研究详情' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('retains partial results without demanding artificial human approval', () => {
    const open = vi.fn();
    const result = { ...props.result, status: 'completed', outcome: 'partial', summary: '可执行四组对照，缺少统一设置下的实测数据。',
      report: { versionId: 'v1' }, allowedActions: ['open_report', 'continue'], sourceCount: 2 };
    render(<ResearchResultCard {...props} result={result} onOpenReport={open} />);
    expect(screen.getByRole('status')).toHaveTextContent('已完成部分研究');
    expect(screen.queryByRole('button', { name: '停止' })).not.toBeInTheDocument();
    expect(screen.queryByText('确认并保存结果')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看已有结果' }));
    expect(open).toHaveBeenCalledWith(props.run, result);
  });

  it('reuses action identity after an uncertain response rather than creating a new action', async () => {
    const action = vi.fn().mockRejectedValueOnce(new Error('网络断开')).mockResolvedValueOnce(undefined);
    render(<ResearchResultCard {...props} onAction={action} />);
    fireEvent.click(screen.getByRole('button', { name: '停止' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('网络断开');
    fireEvent.click(screen.getByRole('button', { name: '停止' }));
    await waitFor(() => expect(action).toHaveBeenCalledTimes(2));
    expect(action.mock.calls[0]).toEqual(action.mock.calls[1]);
    expect(action.mock.calls[0][3]).toEqual(expect.objectContaining({ expectedRunRevision: 4, requestId: expect.any(String) }));
  });

  it('distinguishes abstracts from full text when opening material details', () => {
    render(<ResearchResultCard {...props} result={{ ...props.result, sources: [{ workId: 'w', title: '公开论文', accessLevel: 'abstract' }] }} />);
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    fireEvent.click(screen.getByRole('tab', { name: '资料' }));
    expect(screen.getByText('仅摘要')).toBeInTheDocument();
  });
});

describe('external source management', () => {
  it('shows Add to task button only for external sources not yet added', () => {
    const result = { ...props.result, status: 'completed', outcome: 'complete',
      sources: [
        { sourceId: 'ext-1', title: '外部论文A', sourceKind: 'external', url: 'https://example.com/a', accessLevel: 'fulltext' },
        { sourceId: 'ext-2', title: '外部论文B', sourceKind: 'external', url: 'https://example.com/b', accessLevel: 'abstract', addedToTask: true },
        { sourceId: 'local-1', title: '任务论文', pdfId: 'p1' },
      ],
      allowedActions: ['open_report'] };
    const onAddSource = vi.fn();
    render(<ResearchResultCard {...props} result={result} onAddSource={onAddSource} />);
    fireEvent.click(screen.getByRole('button', { name: /来源与详情/ }));
    fireEvent.click(screen.getByRole('tab', { name: '资料' }));
    expect(screen.getByText('外部论文A')).toBeInTheDocument();
    const addButtons = screen.getAllByRole('button', { name: /加入任务材料/ });
    expect(addButtons).toHaveLength(1);
    expect(screen.getByText('已加入任务')).toBeInTheDocument();
  });

  it('calls onAddSource with correct parameters', async () => {
    const onAddSource = vi.fn().mockResolvedValue(undefined);
    const result = { ...props.result, status: 'completed', outcome: 'complete',
      sources: [{ sourceId: 'ext-1', title: '外部论文', sourceKind: 'external', url: 'https://example.com', accessLevel: 'fulltext' }],
      allowedActions: [] };
    render(<ResearchResultCard {...props} result={result} onAddSource={onAddSource} />);
    fireEvent.click(screen.getByRole('button', { name: /来源与详情/ }));
    fireEvent.click(screen.getByRole('tab', { name: '资料' }));
    fireEvent.click(screen.getByRole('button', { name: /加入任务材料/ }));
    await waitFor(() => expect(onAddSource).toHaveBeenCalledWith('t', 'r', 'ext-1'));
  });

  it('shows external link for external sources with URL', () => {
    const result = { ...props.result, status: 'completed', outcome: 'complete',
      sources: [{ sourceId: 'ext-1', title: '外部论文', sourceKind: 'external', url: 'https://arxiv.org/abs/1234', accessLevel: 'abstract' }],
      allowedActions: [] };
    render(<ResearchResultCard {...props} result={result} />);
    fireEvent.click(screen.getByRole('button', { name: /来源与详情/ }));
    fireEvent.click(screen.getByRole('tab', { name: '资料' }));
    const link = screen.getByRole('link', { name: /来源页面/ });
    expect(link).toHaveAttribute('href', 'https://arxiv.org/abs/1234');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('does not show Add to task button for local task materials', () => {
    const result = { ...props.result, status: 'completed', outcome: 'complete',
      sources: [{ sourceId: 'local-1', title: '任务论文', pdfId: 'p1' }],
      allowedActions: [] };
    const onAddSource = vi.fn();
    render(<ResearchResultCard {...props} result={result} onAddSource={onAddSource} />);
    fireEvent.click(screen.getByRole('button', { name: /来源与详情/ }));
    fireEvent.click(screen.getByRole('tab', { name: '资料' }));
    expect(screen.queryByRole('button', { name: /加入任务材料/ })).not.toBeInTheDocument();
  });
});

describe('plan editor in paused state', () => {
  it('lets a followup specify its goal and explicitly select a fresh task snapshot', async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    render(<ResearchResultCard {...props} result={{ ...props.result, status: 'completed', allowedActions: ['continue'] }} onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', { name: '补查缺口' }));
    expect(onAction).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: '继续研究什么？' }), { target: { value: '用新增论文核对反对证据' } });
    fireEvent.click(screen.getByRole('checkbox', { name: '使用当前任务材料（含新加入的论文）' }));
    fireEvent.click(screen.getByRole('button', { name: '开始补查' }));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('t', 'r', 'continue', expect.objectContaining({
      question: '用新增论文核对反对证据', materialSelection: { mode: 'task_default' }, expectedRunRevision: 4,
    })));
  });
  it('edits executable obligations and preserves dependency and source identities', async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    const result = { ...props.result, status: 'paused', allowedActions: ['plan'],
      plan: [{ itemId: 'p1', question: '原问题', dependencies: ['prior'],
        obligations: [{ obligationId: 'o1', question: '原检索问题', requiredSources: ['paper-b'] }] }] };
    render(<ResearchResultCard {...props} result={result} onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    fireEvent.change(screen.getByDisplayValue('原问题'), { target: { value: '核对失败条件' } });
    fireEvent.click(screen.getByRole('button', { name: '提交修改' }));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('t', 'r', 'plan', expect.objectContaining({
      plan: [expect.objectContaining({ dependencies: ['prior'], obligations: [expect.objectContaining({
        obligationId: 'o1', question: '核对失败条件', requiredSources: ['paper-b'],
      })] })],
    })));
  });
  it('shows editable plan inputs when paused with plan action available', () => {
    const result = { ...props.result, status: 'paused', allowedActions: ['plan', 'resume'],
      plan: { revision: 3, items: [{ itemId: 'p1', question: '核对实验条件', status: 'pending' }] } };
    const onAction = vi.fn();
    render(<ResearchResultCard {...props} result={result} onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(screen.getByDisplayValue('核对实验条件')).toBeInTheDocument();
  });

  it('submits plan modifications with planRevision', async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    const result = { ...props.result, status: 'paused', allowedActions: ['plan', 'resume'],
      plan: { revision: 3, items: [{ itemId: 'p1', question: '核对实验条件', status: 'pending' }] } };
    render(<ResearchResultCard {...props} result={result} onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    fireEvent.click(screen.getByRole('button', { name: '提交修改' }));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('t', 'r', 'plan', expect.objectContaining({
      expectedRunRevision: 4, planRevision: 3,
      plan: expect.arrayContaining([expect.objectContaining({ itemId: 'p1', question: '核对实验条件' })]),
    })));
  });

  it('does not show plan editor when not paused', () => {
    const result = { ...props.result, status: 'running', allowedActions: ['cancel'],
      plan: [{ itemId: 'p1', question: '核对实验条件' }] };
    render(<ResearchResultCard {...props} result={result} />);
    fireEvent.click(screen.getByRole('button', { name: '详情' }));
    expect(screen.queryByRole('button', { name: '提交修改' })).not.toBeInTheDocument();
  });
});

describe('execution events', () => {
  it('renders actual events without fabricating stages', () => {
    const result = { ...props.result, status: 'completed', outcome: 'complete',
      events: [
        { eventId: 'e1', label: '阅读论文', summary: 'LightGaussian 消融表', status: 'completed' },
        { eventId: 'e2', kind: 'extract', summary: '提取四组对照数据', status: 'completed' },
      ],
      allowedActions: [] };
    render(<ResearchResultCard {...props} result={result} />);
    fireEvent.click(screen.getByRole('button', { name: /来源与详情/ }));
    fireEvent.click(screen.getByRole('tab', { name: '执行记录' }));
    expect(screen.getByText('阅读论文')).toBeInTheDocument();
    expect(screen.getByText(/LightGaussian 消融表/)).toBeInTheDocument();
    expect(screen.getByText('extract')).toBeInTheDocument();
  });

  it('shows empty state when no events are provided', () => {
    const result = { ...props.result, status: 'completed', outcome: 'complete', events: [], allowedActions: [] };
    render(<ResearchResultCard {...props} result={result} />);
    fireEvent.click(screen.getByRole('button', { name: /来源与详情/ }));
    fireEvent.click(screen.getByRole('tab', { name: '执行记录' }));
    expect(screen.getByText('尚无执行记录。')).toBeInTheDocument();
  });
});
