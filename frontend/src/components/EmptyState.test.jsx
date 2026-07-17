import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EmptyState } from './EmptyState.jsx';

describe('EmptyState', () => {
  it('renders default title when no title provided', () => {
    render(<EmptyState />);
    expect(screen.getByText('暂无内容')).toBeInTheDocument();
  });

  it('renders custom title', () => {
    render(<EmptyState title="还没有论文" />);
    expect(screen.getByText('还没有论文')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(<EmptyState description="请先上传一篇论文开始阅读。" />);
    expect(screen.getByText('请先上传一篇论文开始阅读。')).toBeInTheDocument();
  });

  it('does not render description when empty', () => {
    const { container } = render(<EmptyState title="空" />);
    // Only the title paragraph should be present (description paragraph omitted)
    const titleEls = container.querySelectorAll('.theme-text-primary');
    expect(titleEls.length).toBe(1);
  });

  it('renders with custom className', () => {
    const { container } = render(<EmptyState className="my-empty" />);
    expect(container.firstChild).toHaveClass('my-empty');
  });

  it('renders default Info icon', () => {
    const { container } = render(<EmptyState />);
    // The icon is rendered as an SVG inside the container
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });
});
