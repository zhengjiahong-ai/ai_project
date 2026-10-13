import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import WorkbenchPopover from './WorkbenchPopover';

it('keeps secondary actions closed, supports keyboard escape and restores the trigger', () => {
  render(<WorkbenchPopover label="更多操作"><button type="button">查看历史</button></WorkbenchPopover>);
  expect(screen.queryByRole('button', { name: '查看历史' })).not.toBeInTheDocument();
  const trigger = screen.getByRole('button', { name: '更多操作' });
  fireEvent.click(trigger);
  expect(screen.getByRole('button', { name: '查看历史' })).toHaveFocus();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

it('allows forms inside the popover and closes on an outside pointer', () => {
  render(<WorkbenchPopover label="筛选"><input aria-label="关键词" /></WorkbenchPopover>);
  fireEvent.click(screen.getByRole('button', { name: '筛选' }));
  fireEvent.change(screen.getByRole('textbox', { name: '关键词' }), { target: { value: '论文' } });
  expect(screen.getByRole('textbox', { name: '关键词' })).toHaveValue('论文');
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole('textbox', { name: '关键词' })).not.toBeInTheDocument();
});

it('opens above a bottom toolbar and follows its position after content changes', () => {
  let anchorTop = 700;
  const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({ top: anchorTop, bottom: anchorTop + 32, left: 100, right: 132 }));
  const height = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(160);
  const width = vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(280);
  try {
    const view = render(<WorkbenchPopover label="材料"><button type="button">论文甲</button></WorkbenchPopover>);
    fireEvent.click(screen.getByRole('button', { name: '材料' }));
    expect(screen.getByRole('dialog', { name: '材料' })).toHaveStyle({ top: '534px' });
    anchorTop = 640;
    view.rerender(<WorkbenchPopover label="材料"><button type="button">论文乙</button></WorkbenchPopover>);
    expect(screen.getByRole('dialog', { name: '材料' })).toHaveStyle({ top: '474px' });
  } finally { bounds.mockRestore(); height.mockRestore(); width.mockRestore(); }
});
