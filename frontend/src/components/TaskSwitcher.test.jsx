import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TaskSwitcher from './TaskSwitcher';

it('closes after an actual parent task change while the selection promise completes', async () => {
  const tasks = [{ id: 'first', title: '任务一' }, { id: 'second', title: '任务二' }];
  function Wrapper() {
    const [active, setActive] = React.useState(tasks[0]);
    return <TaskSwitcher tasks={tasks} activeTask={active} onSelect={async id => { setActive(tasks.find(task => task.id === id)); await Promise.resolve(); }} />;
  }
  render(<Wrapper />);
  fireEvent.click(screen.getByRole('button', { name: '切换任务' }));
  fireEvent.click(screen.getByRole('button', { name: '任务二' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: '切换任务' })).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: '切换任务' })).toHaveTextContent('任务二');
});

it('finds archived tasks, restores explicitly and never deletes them', async () => {
  const tasks = [{ id: 'a', title: '进行中' }, { id: 'b', title: '已读论文', archived: true }];
  const select = vi.fn(), archive = vi.fn();
  const view = render(<TaskSwitcher tasks={tasks} activeTask={tasks[0]} onSelect={select} onArchive={archive} />);
  fireEvent.click(screen.getByRole('button', { name: '切换任务' }));
  expect(screen.queryByRole('button', { name: '已读论文 · 已归档' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '查看归档任务' }));
  fireEvent.click(screen.getByRole('button', { name: '已读论文 · 已归档' }));
  await waitFor(() => expect(select).toHaveBeenCalledWith('b'));
  view.rerender(<TaskSwitcher tasks={tasks} activeTask={tasks[1]} onSelect={select} onArchive={archive} />);
  fireEvent.click(screen.getByRole('button', { name: '切换任务' }));
  fireEvent.click(screen.getByRole('button', { name: '恢复任务' }));
  await waitFor(() => expect(archive).toHaveBeenCalledWith(false));
});

it('searches tasks and switches by identity without creating a task', async () => {
  const tasks = [{ id: 'a', title: '压缩阅读' }, { id: 'b', title: '实验方案' }];
  const select = vi.fn(), create = vi.fn();
  render(<TaskSwitcher tasks={tasks} activeTask={tasks[0]} onSelect={select} onCreate={create} />);
  fireEvent.click(screen.getByRole('button', { name: '切换任务' }));
  fireEvent.change(screen.getByRole('textbox', { name: '搜索任务' }), { target: { value: '实验' } });
  fireEvent.click(screen.getByRole('button', { name: '实验方案' }));
  await waitFor(() => expect(select).toHaveBeenCalledWith('b'));
  expect(create).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByRole('button', { name: '切换任务' })).toHaveFocus());
});

it('retains a failed rename and its draft instead of presenting it as saved', async () => {
  const task = { id: 'a', title: '原名称' };
  const rename = vi.fn(async () => { throw new Error('服务离线'); });
  render(<TaskSwitcher tasks={[task]} activeTask={task} onRename={rename} />);
  fireEvent.click(screen.getByRole('button', { name: '切换任务' }));
  fireEvent.click(screen.getByRole('button', { name: '重命名' }));
  fireEvent.change(screen.getByRole('textbox', { name: '任务名称' }), { target: { value: '未保存名称' } });
  fireEvent.click(screen.getByRole('button', { name: '保存名称' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('服务离线');
  expect(screen.getByRole('textbox', { name: '任务名称' })).toHaveValue('未保存名称');
  expect(task.title).toBe('原名称');
});
