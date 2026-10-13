import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DocumentActions from './DocumentActions';

describe('research original versions', () => {
  it('keeps the original read-only and allows opening the current editable draft', () => {
    const original = { id: 'machine', sourceRunId: 'run', origin: 'machine', title: '报告' };
    const current = { id: 'latest', sourceRunId: 'run', origin: 'latest', title: '报告', edited: true };
    const open = vi.fn();
    render(<DocumentActions document={original} researchVersions={[original, current]} onOpenVersion={open} />);
    expect(screen.queryByRole('button', { name: '编辑' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '研究版本' }));
    fireEvent.click(screen.getByRole('button', { name: '我的修改稿' }));
    expect(open).toHaveBeenCalledWith(current);
    fireEvent.click(screen.getByRole('button', { name: '成果更多操作' }));
    expect(screen.queryByRole('button', { name: '重命名…' })).not.toBeInTheDocument();
  });
});
