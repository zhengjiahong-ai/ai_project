import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DocumentOrganizer from './DocumentOrganizer';
import DocumentActions from './DocumentActions';

const tasks = [{ id: 'a', title: '原任务' }, { id: 'b', title: '目标任务' }];
const props = { document: { id: 'doc', title: '笔记', paperIds: ['paper'] }, kind: '笔记', action: 'move', taskId: 'a', tasks, onRename: vi.fn(), onClose: vi.fn() };
describe('document organization', () => {
  it('keeps the menu short and opens only the requested operation', () => {
    render(<DocumentActions {...props} onMove={vi.fn()} onExport={vi.fn()} onLocate={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '笔记更多操作' }));
    expect(screen.getByRole('button', { name: '在对话中查看' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下载 Markdown' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText('整理成果')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重命名…' }));
    expect(screen.getByRole('dialog', { name: '重命名笔记' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '笔记更多操作' })).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByLabelText('笔记名称'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '笔记更多操作' })).toHaveFocus();
  });
  it('requires saved text and explicitly carries the optional associated papers', async () => {
    const move = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<DocumentOrganizer {...props} dirty onMove={move} />);
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '检查是否已移动' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('移动到任务'), { target: { value: 'b' } });
    expect(screen.getByRole('button', { name: '移动笔记' })).toBeDisabled();
    rerender(<DocumentOrganizer {...props} dirty={false} onMove={move} />);
    fireEvent.click(screen.getByLabelText('同时添加关联论文'));
    fireEvent.click(screen.getByRole('button', { name: '移动笔记' }));
    await waitFor(() => expect(move).toHaveBeenCalledWith('b', true, false));
  });
  it('queries the retained request after an uncertain move without submitting another move', async () => {
    let pending = null;
    const move = vi.fn().mockImplementation(async (target, include, query) => {
      if (!query) { pending = { targetTaskId: target, includeMaterials: include }; throw new Error('连接中断，结果未确认'); }
    });
    render(<DocumentOrganizer {...props} onMove={move} getPendingMove={() => pending} />);
    fireEvent.change(screen.getByLabelText('移动到任务'), { target: { value: 'b' } });
    fireEvent.click(screen.getByRole('button', { name: '移动笔记' }));
    await screen.findByRole('alert');
    expect(screen.queryByLabelText('移动到任务')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '检查是否已移动' }));
    await waitFor(() => expect(move).toHaveBeenLastCalledWith(null, false, true));
    expect(move).toHaveBeenCalledTimes(2);
  });
  it('restores a pending move when reopening and traps keyboard focus', () => {
    render(<DocumentOrganizer {...props} onMove={vi.fn()} getPendingMove={() => ({ targetTaskId: 'b' })} />);
    expect(screen.getByText('目标任务：目标任务')).toBeInTheDocument();
    const cancel = screen.getByRole('button', { name: '取消' });
    expect(cancel).toHaveFocus();
    fireEvent.keyDown(cancel, { key: 'Tab', shiftKey: true });
    expect(screen.getByRole('button', { name: '检查是否已移动' })).toHaveFocus();
  });
  it('preserves the rename input when saving fails and submits the entered name', async () => {
    const rename = vi.fn().mockRejectedValueOnce(new Error('保存失败')).mockResolvedValue(undefined);
    render(<DocumentOrganizer {...props} action="rename" onRename={rename} />);
    fireEvent.change(screen.getByLabelText('笔记名称'), { target: { value: '新名称' } });
    fireEvent.click(screen.getByRole('button', { name: '保存名称' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('笔记名称')).toHaveValue('新名称');
    fireEvent.click(screen.getByRole('button', { name: '保存名称' }));
    await waitFor(() => expect(rename).toHaveBeenCalledTimes(2));
    expect(rename).toHaveBeenLastCalledWith('新名称');
  });
});
