import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Skeleton, SkeletonLine, SkeletonCard } from './Skeleton.jsx';

describe('Skeleton', () => {
  it('renders with default classes and aria-hidden', () => {
    const { container } = render(<Skeleton />);
    const el = container.firstChild;
    expect(el).toHaveClass('animate-pulse');
    expect(el).toHaveClass('rounded');
    expect(el).toHaveAttribute('aria-hidden', 'true');
  });

  it('merges custom className', () => {
    const { container } = render(<Skeleton className="h-10 w-20" />);
    expect(container.firstChild).toHaveClass('h-10');
    expect(container.firstChild).toHaveClass('w-20');
  });
});

describe('SkeletonLine', () => {
  it('renders a single line skeleton', () => {
    const { container } = render(<SkeletonLine />);
    expect(container.firstChild).toHaveClass('h-4');
    expect(container.firstChild).toHaveClass('w-full');
  });

  it('merges custom className', () => {
    const { container } = render(<SkeletonLine className="w-3/4" />);
    expect(container.firstChild).toHaveClass('w-3/4');
  });
});

describe('SkeletonCard', () => {
  it('renders a card with header and body lines', () => {
    const { container } = render(<SkeletonCard />);
    expect(container.firstChild).toHaveClass('theme-card');
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');

    // Should contain header skeleton (w-1/3) + 3 body lines
    const children = container.firstChild.children;
    expect(children.length).toBeGreaterThanOrEqual(3);
  });

  it('merges custom className', () => {
    const { container } = render(<SkeletonCard className="my-card" />);
    expect(container.firstChild).toHaveClass('my-card');
  });
});
