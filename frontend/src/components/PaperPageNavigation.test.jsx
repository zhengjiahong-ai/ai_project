import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import PaperPageNavigation from './PaperPageNavigation';

it('uses one-based user input and refuses out-of-range pages', () => {
  const jump = vi.fn();
  const view = render(<PaperPageNavigation pageIndex={0} totalPages={19} onJump={jump} />);
  expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();
  const input = screen.getByRole('textbox', { name: '跳转到页码' });
  fireEvent.change(input, { target: { value: '4' } });
  fireEvent.submit(screen.getByRole('form', { name: '论文页码' }));
  expect(jump).toHaveBeenCalledWith(3);
  fireEvent.change(input, { target: { value: '20' } });
  fireEvent.submit(screen.getByRole('form', { name: '论文页码' }));
  expect(jump).toHaveBeenCalledTimes(1);
  expect(input).toHaveValue('1');
  view.rerender(<PaperPageNavigation pageIndex={18} totalPages={19} onJump={jump} />);
  expect(input).toHaveValue('19');
  expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
});
