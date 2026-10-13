import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskRename from './TaskRename';

it('retains the attempted name on failure and closes only after a successful save', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('冲突，名称仍保留')).mockResolvedValueOnce({});
  render(<TaskRename task={{ id: 'A', title: '原名称' }} onRename={save} />);
  fireEvent.click(screen.getByRole('button', { name: '重命名' }));
  fireEvent.change(screen.getByRole('textbox', { name: '任务名称' }), { target: { value: ' 新名称 ' } });
  fireEvent.click(screen.getByRole('button', { name: '保存名称' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('冲突');
  expect(screen.getByRole('textbox', { name: '任务名称' })).toHaveValue(' 新名称 ');
  fireEvent.click(screen.getByRole('button', { name: '保存名称' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(save).toHaveBeenCalledWith('新名称');
});

it('does not save an empty name and supports keyboard cancellation', () => {
  const save = vi.fn();
  render(<TaskRename task={{ id: 'A', title: '原名称' }} onRename={save} />);
  fireEvent.click(screen.getByRole('button', { name: '重命名' }));
  fireEvent.change(screen.getByRole('textbox', { name: '任务名称' }), { target: { value: '  ' } });
  expect(screen.getByRole('button', { name: '保存名称' })).toBeDisabled();
  fireEvent.keyDown(screen.getByRole('textbox', { name: '任务名称' }), { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '重命名' })).toHaveFocus();
  expect(save).not.toHaveBeenCalled();
});

it('keeps keyboard focus inside the name dialog', () => {
  render(<TaskRename task={{ id: 'A', title: '原名称' }} onRename={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '重命名' }));
  const input = screen.getByRole('textbox', { name: '任务名称' });
  expect(input).toHaveFocus();
  fireEvent.keyDown(input, { key: 'Tab', shiftKey: true });
  expect(screen.getByRole('button', { name: '取消' })).toHaveFocus();
  fireEvent.keyDown(screen.getByRole('button', { name: '取消' }), { key: 'Tab' });
  expect(input).toHaveFocus();
});
