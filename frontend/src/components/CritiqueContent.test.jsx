import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import ChatPanel from './ChatPanel';
import CritiqueContent from './CritiqueContent';

const source = { sourceId: 's1', pdfId: 'p1', pageIndex: 3, text: '原文报告的实验条件。' };
const text1 = `第一点完整判断。${'完整必要条件。'.repeat(80)}`;
const fixture = {
  role: 'ai', capability: 'critique', artifactId: 'a1', content: 'stored summary', rag_sources: [source],
  critique: { schemaVersion: 2, lead: '总判断。',
    claims: [{ id: 'c1', text: '论文事实', references: [{ sourceId: 's1', quote: source.text }] }],
    issues: [{ id: 'i1', title: '条件', conclusionClaimId: 'c1', supportClaimIds: [] }, { id: 'i2', title: '范围' }],
    presentation: { chatIssueIds: ['i1', 'i2'], artifactIssueIds: ['i1', 'i2'], standalone: true },
    chatBlocks: [{ issueId: 'i1', text: text1 }, { issueId: 'i2', text: '第二点的事实与推断都完整。' }],
    artifactBlocks: [{ issueId: 'i1', text: text1 }, { issueId: 'i2', text: '第二点详细理由。' }],
    pending: [{ id: 'pending1', whatToCheck: '次要核查目标' }] },
};

describe('grouped critique presentation', () => {
  beforeEach(() => localStorage.clear());
  it('opens only the cited point or lead evidence and keeps source identity without model execution', async () => {
    const second = { ...source, sourceId: 's2', pdfId: 'p2', text: '第二篇论文的独立依据。' };
    const value = { ...fixture, sources: [source, second], critique: { ...fixture.critique,
      lead: '总判断。[2]', claims: [...fixture.critique.claims,
        { id: 'c2', references: [{ sourceId: 's2', quote: second.text }] },
        { id: 'lead-claim', references: [{ sourceId: 's2', quote: '总判断的独立原文摘录。' }] }],
      issues: [fixture.critique.issues[0], { id: 'i2', conclusionClaimId: 'c2' }],
      artifactBlocks: [{ issueId: 'i1', text: '第一点。[1]' }, { issueId: 'i2', text: '第二点。[2]' }],
      presentation: { ...fixture.critique.presentation, leadClaimIds: ['lead-claim'] },
    } };
    const jump = vi.fn();
    const view = render(<CritiqueContent value={value} text="" target="artifact" storageKey="citation-check" onJumpToSource={jump} />);
    const point = view.container.querySelector('[data-critique-issue-id="i2"]');
    fireEvent.click(within(point).getByRole('button', { name: '查看引用 2 的依据' }));
    await waitFor(() => expect(point.querySelector('details')).toHaveAttribute('open'));
    expect(view.container.querySelector('[data-critique-issue-id="i1"] details')).not.toHaveAttribute('open');
    expect(within(point).getByText(second.text)).toBeInTheDocument();
    expect(jump).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByRole('button', { name: '查看引用 2 的依据' })[0]);
    expect(await screen.findByText('总判断的独立原文摘录。')).toBeInTheDocument();
    const lead = screen.getByText('总判断 查看依据 · 1 处').closest('details');
    await waitFor(() => expect(lead).toHaveAttribute('open'));
    expect(lead.querySelector('summary')).toHaveFocus();
    expect(jump).not.toHaveBeenCalled();
    await waitFor(() => expect(localStorage.getItem('citation-check:issue:lead')).toBe('open'));
    view.unmount();
    render(<CritiqueContent value={value} text="" target="artifact" storageKey="citation-check" onJumpToSource={jump} />);
    expect(screen.getByText('总判断 查看依据 · 1 处').closest('details')).toHaveAttribute('open');
    expect(screen.getByText('总判断 查看依据 · 1 处')).not.toHaveFocus();
  });
  it('shows paper identity and restores expanded evidence when returning to the same document', async () => {
    const props = { value: fixture, text: '', target: 'artifact', papers: [{ id: 'p1', title: 'LightGaussian: Compression' }], storageKey: 'task:a:document:a1' };
    const view = render(<CritiqueContent {...props} />);
    const details = screen.getByText('查看依据 · 1 处').closest('details');
    fireEvent.click(screen.getByText('查看依据 · 1 处'));
    await waitFor(() => expect(localStorage.getItem('task:a:document:a1:issue:i1')).toBe('open'));
    expect(screen.getByText('LightGaussian')).toBeInTheDocument();
    expect(screen.queryByText(/p\.4/u)).not.toBeInTheDocument();
    expect(details).toHaveAttribute('open');
    view.unmount();
    const returned = render(<CritiqueContent {...props} />);
    expect(screen.getByText('查看依据 · 1 处').closest('details')).toHaveAttribute('open');
    returned.unmount();
    render(<CritiqueContent {...props} storageKey="task:b:document:a1" />);
    expect(screen.getByText('查看依据 · 1 处').closest('details')).not.toHaveAttribute('open');
  });
  it('preserves both complete chat points beyond the old preview budget and expands source locally', () => {
    const jump = vi.fn();
    const send = vi.fn();
    const follow = vi.fn();
    render(<ChatPanel messages={[fixture]} onSendMessage={send} onJumpToSource={jump} onFollowupIssue={follow} />);
    expect(screen.getByText(text1)).toBeInTheDocument();
    expect(screen.getByText('第二点的事实与推断都完整。')).toBeInTheDocument();
    expect(screen.queryByText('次要核查目标')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('查看依据 · 1 处'));
    expect(screen.getByText(source.text)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '跳回原文 · 按摘录定位' }));
    expect(jump).toHaveBeenCalledWith(expect.objectContaining({ pdfId: 'p1', pageIndex: 3, sourceId: 's1' }));
    expect(jump).toHaveBeenCalledWith(expect.objectContaining({ literalQuote: source.text }));
    fireEvent.click(screen.getAllByRole('button', { name: '追问这一点' })[1]);
    expect(follow).toHaveBeenCalledWith(fixture, 'i2');
    expect(send).not.toHaveBeenCalled();
  });

  it('keeps edited and legacy document text without inferring claim relationships', () => {
    const view = render(<CritiqueContent value={{ ...fixture, edited: true }} text="用户修改后的判断" target="artifact" />);
    expect(screen.getByText('用户修改后的判断')).toBeInTheDocument();
    expect(screen.queryByText(text1)).not.toBeInTheDocument();
    expect(screen.getByText(/修改内容不作为论文原文依据/u)).toBeInTheDocument();
    view.rerender(<CritiqueContent value={{}} text="旧成果原始正文" target="artifact" />);
    expect(screen.getByText('旧成果原始正文')).toBeInTheDocument();
    expect(screen.queryByText(/查看依据/u)).not.toBeInTheDocument();
  });

  it('preserves the full composed response instead of replacing it with critique-only blocks', () => {
    render(<CritiqueContent value={{ ...fixture, capability: 'compose', critique: { ...fixture.critique, presentation: { ...fixture.critique.presentation, standalone: false } } }} text="完整解释、比较与批判正文" />);
    expect(screen.getByText('完整解释、比较与批判正文')).toBeInTheDocument();
    expect(screen.queryByText(text1)).not.toBeInTheDocument();
  });
});
