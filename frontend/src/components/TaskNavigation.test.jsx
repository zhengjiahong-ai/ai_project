import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TaskNavigation from './TaskNavigation';

const props = () => ({ tasks: [{ id: 'a', title: '任务 A' }, { id: 'b', title: '任务 B' }],
  activeTask: { id: 'a', paperIds: ['p1'], notes: [], artifacts: [] },
  papers: [{ id: 'p1', title: '论文一' }, { id: 'p2', title: '论文二' }], collapsed: false,
  onToggle: vi.fn(), onSelectTask: vi.fn(), onCreateTask: vi.fn(), onOpenPaper: vi.fn(),
  onAddPaper: vi.fn(), onRemovePaper: vi.fn(), onOpenArtifact: vi.fn() });
beforeEach(() => localStorage.clear());

it('finds source metadata and explicitly opens other task documents without adding materials', () => {
  const handlers = props();
  const onOpenTaskDocument = vi.fn();
  const note = { id: 'note-b', title: '实验建议', text: '做对照', sources: [{ title: 'LightGaussian', doi: '10.test/paper' }] };
  render(<TaskNavigation {...handlers} onOpenTaskDocument={onOpenTaskDocument}
    tasks={[handlers.activeTask, { id: 'b', title: '对照实验任务', paperIds: [], notes: [note], artifacts: [] }]} />);
  fireEvent.change(screen.getByRole('textbox', { name: '搜索材料与记录' }), { target: { value: '10.test/paper' } });
  expect(screen.queryByRole('button', { name: /实验建议/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox', { name: '搜索范围' }), { target: { value: 'all' } });
  fireEvent.click(screen.getByRole('button', { name: /实验建议/ }));
  expect(onOpenTaskDocument).toHaveBeenCalledWith('b', note);
  expect(handlers.onAddPaper).not.toHaveBeenCalled();
});

describe('task navigation', () => {
  it('distinguishes opening a paper from adding a task material', async () => {
    const handlers = props();
    render(<TaskNavigation {...handlers} />);
    fireEvent.click(screen.getByRole('button', { name: '论文一' }));
    expect(handlers.onOpenPaper).toHaveBeenCalledWith('p1');
    expect(handlers.onAddPaper).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText('添加已有论文'));
    fireEvent.click(screen.getByRole('button', { name: '论文二' }));
    await waitFor(() => expect(handlers.onAddPaper).toHaveBeenCalledWith('p2'));
  });
  it('shows a persistence failure instead of hiding it', async () => {
    render(<TaskNavigation {...props()} onCreateTask={async () => { throw new Error('保存失败'); }} />);
    fireEvent.click(screen.getByLabelText('新任务'));
    expect(await screen.findByRole('alert')).toHaveTextContent('保存失败');
  });
  it('keeps an accessible restore control when collapsed', () => {
    const handlers = props();
    render(<TaskNavigation {...handlers} collapsed />);
    fireEvent.click(screen.getByLabelText('展开导航'));
    expect(handlers.onToggle).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText('当前任务')).not.toBeInTheDocument();
  });
  it('distinguishes duplicate saved results and opens the selected original document', () => {
    const handlers = props();
    const old = { id: 'old', title: '第4页译文', createdAt: '2026-10-08T12:00:00Z', pageIndex: 3, text: '旧译文' };
    const recent = { id: 'recent', title: '第4页译文', createdAt: '2026-10-09T12:00:00Z', pageIndex: 3, text: '新译文' };
    const task = { ...handlers.activeTask, artifacts: [old, recent] };
    const snapshot = JSON.stringify(task);
    render(<TaskNavigation {...handlers} activeTask={task} />);
    const results = screen.getAllByRole('button', { name: /第4页译文/ });
    expect(results[0]).toHaveTextContent('10/09');
    expect(results[1]).toHaveTextContent('10/08');
    fireEvent.click(results[0]);
    expect(handlers.onOpenArtifact).toHaveBeenCalledWith(recent);
    expect(JSON.stringify(task)).toBe(snapshot);
  });
  it('keeps undated notes distinguishable without inventing save times', () => {
    const handlers = props();
    const notes = [{ id: 'n1', title: '原文笔记', source: { text: '第一处选区' } },
      { id: 'n2', title: '原文笔记', createdAt: 'invalid', source: { text: '第二处选区', sourcePageIndex: 2 } }];
    render(<TaskNavigation {...handlers} activeTask={{ ...handlers.activeTask, notes }} />);
    const results = screen.getAllByRole('button', { name: /原文笔记/ });
    expect(results[0]).toHaveTextContent('第一处选区');
    expect(results[1]).toHaveTextContent('第二处选区');
    expect(results[1]).not.toHaveTextContent('Invalid Date');
    fireEvent.click(results[1]);
    expect(handlers.onOpenArtifact).toHaveBeenCalledWith(notes[1]);
  });
});


it('searches document bodies and opens the retained document with the current identity', () => {
  const handlers=props();
  const document={id:'report',type:'research',title:'实验报告',text:'**正文**中的消融对比'};
  render(<TaskNavigation {...handlers} activeTask={{...handlers.activeTask,artifacts:[document]}} selectedDocumentId="report"/>);
  fireEvent.change(screen.getByRole('textbox',{name:'搜索材料与记录'}),{target:{value:'消融对比'}});
  const link=screen.getByRole('button',{name:'实验报告 · 报告'});
  expect(link).toHaveTextContent('正文中的消融对比');
  expect(link).toHaveAttribute('aria-current','page');
  expect(screen.queryByRole('button',{name:'论文一'})).not.toBeInTheDocument();
  fireEvent.click(link);
  expect(handlers.onOpenArtifact).toHaveBeenCalledWith(document);
  expect(screen.getByRole('textbox',{name:'搜索材料与记录'})).toHaveValue('');
  expect(screen.getByRole('button',{name:'论文一'})).toBeInTheDocument();
});

it('retains recent visits across reloads, excludes unavailable records and keeps tasks separate', () => {
  const handlers = props(), document = { id: 'note', title: '实验条件', text: '固定预算' };
  const task = { ...handlers.activeTask, notes: [document] };
  const first = render(<TaskNavigation {...handlers} activeTask={task} />);
  fireEvent.click(screen.getByRole('button', { name: '实验条件 · 笔记' }));
  first.unmount();
  const second = render(<TaskNavigation {...handlers} activeTask={task} />);
  fireEvent.focus(screen.getByRole('textbox', { name: '搜索材料与记录' }));
  const recent = screen.getByRole('region', { name: '最近访问' });
  expect(recent).toHaveTextContent('实验条件');
  fireEvent.click(recent.querySelector('button'));
  expect(handlers.onOpenArtifact).toHaveBeenLastCalledWith(document);
  expect(screen.queryByRole('region', { name: '最近访问' })).not.toBeInTheDocument();
  second.rerender(<TaskNavigation {...handlers} activeTask={{ ...task, notes: [] }} />);
  fireEvent.focus(screen.getByRole('textbox', { name: '搜索材料与记录' }));
  expect(screen.getByRole('region', { name: '最近访问' })).not.toHaveTextContent('实验条件');
  second.rerender(<TaskNavigation {...handlers} activeTask={{ ...task, id: 'b' }} />);
  fireEvent.focus(screen.getByRole('textbox', { name: '搜索材料与记录' }));
  expect(screen.getByRole('region', { name: '最近访问' })).not.toHaveTextContent('实验条件');
});

it('restores the list position when search closes without switching the reading object', () => {
  const handlers = props();
  render(<TaskNavigation {...handlers} />);
  const papers = screen.getByRole('region', { name: '论文与材料列表' }).querySelector('.workbench-paper-list');
  const records = screen.getByRole('region', { name: '笔记与成果列表' }).querySelector('.workbench-record-list');
  papers.scrollTop = 37; records.scrollTop = 120;
  const input = screen.getByRole('textbox', { name: '搜索材料与记录' });
  fireEvent.change(input, { target: { value: '没有命中' } });
  papers.scrollTop = 0; records.scrollTop = 0;
  fireEvent.keyDown(input, { key: 'Escape' });
  expect(input).toHaveValue('');
  expect(papers.scrollTop).toBe(37); expect(records.scrollTop).toBe(120);
  expect(handlers.onOpenPaper).not.toHaveBeenCalled();
  expect(handlers.onOpenArtifact).not.toHaveBeenCalled();
});

it('filters learning records and searches their questions, answers and feedback', () => {
  const handlers=props(),open=vi.fn();
  const activity={activityId:'learning',pdfId:'p1',status:'paused',concepts:[{id:'c',question:'如何解释稀疏性？'}],
    turns:[{conceptId:'c',action:'answer',text:'计算资源会减少',feedback:'需要补充误差边界'}]};
  render(<TaskNavigation {...handlers} learningRecords={[activity]} onOpenLearning={open} selectedLearningId="learning"/>);
  fireEvent.click(screen.getByRole('button', { name: '筛选成果' }));
  fireEvent.change(screen.getByRole('combobox',{name:'成果类型'}),{target:{value:'translation'}});
  expect(screen.queryByText('学习记录（1）')).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox',{name:'成果类型'}),{target:{value:'learning'}});
  const search=screen.getByRole('textbox',{name:'搜索材料与记录'});
  for(const query of ['稀疏性','计算资源','误差边界']) {
    fireEvent.change(search,{target:{value:query}});
    const link=screen.getByRole('button',{name:'精读 · 论文一：如何解释稀疏性 · 已暂停'});
    expect(link.closest('details')).toHaveAttribute('open');
    expect(link).toHaveAttribute('aria-current','page');
    fireEvent.click(link);
    expect(open).toHaveBeenLastCalledWith(activity);
  }
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('does not infer translation from a page anchor and shows a global empty search state', () => {
  const handlers=props();
  const anchored={id:'evidence',pageIndex:3,title:'方法证据',text:'正文'};
  const translation={id:'old-translation',pageIndex:3,title:'第4页译文',text:'中文'};
  render(<TaskNavigation {...handlers} activeTask={{...handlers.activeTask,artifacts:[anchored,translation]}}/>);
  fireEvent.click(screen.getByRole('button', { name: '筛选成果' }));
  fireEvent.change(screen.getByRole('combobox',{name:'成果类型'}),{target:{value:'translation'}});
  expect(screen.getByRole('button',{name:'第4页译文 · 译文'})).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/方法证据/})).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox',{name:'搜索材料与记录'}),{target:{value:'不存在的关键词'}});
  expect(screen.getByRole('status')).toHaveTextContent('没有匹配的论文、成果或学习记录');
  expect(screen.getByRole('combobox',{name:'成果类型'})).toHaveTextContent('学习记录');
});

it('keeps parsing and failed material state beside its paper without a persistent success badge', () => {
  const handlers = props();
  render(<TaskNavigation {...handlers} activeTask={{ ...handlers.activeTask, paperIds: ['p1', 'p2', 'p3'] }} papers={[
    { id: 'p1', title: '解析中论文', processingStatus: 'parsing', questionReady: false },
    { id: 'p2', title: '失败论文', processingStatus: 'failed', questionReady: false },
    { id: 'p3', title: '可用论文', processingStatus: 'completed', questionReady: true },
  ]} />);
  expect(screen.getByRole('button', { name: '解析中论文' })).toHaveTextContent('正在解析');
  expect(screen.getByRole('button', { name: '失败论文' })).toHaveTextContent('正文未就绪 · 打开处理');
  expect(screen.getByRole('button', { name: '可用论文' }).textContent).toBe('可用论文');
  fireEvent.click(screen.getByRole('button', { name: '失败论文' }));
  expect(handlers.onOpenPaper).toHaveBeenCalledWith('p2');
});
