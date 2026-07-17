import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { axe } from 'jest-axe';

import { Skeleton, SkeletonLine, SkeletonCard } from './Skeleton.jsx';
import { EmptyState } from './EmptyState.jsx';
import { ErrorBoundary } from './ErrorBoundary.tsx';
import { ToastProvider } from './Toast.jsx';
import ChatPanel from './ChatPanel.tsx';

function Safe() {
  return <div>安全内容</div>;
}

const noop = () => {};

describe('a11y audit', () => {
  it('Skeleton has no critical a11y violations', async () => {
    const { container } = render(<Skeleton />);
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('SkeletonLine has no critical a11y violations', async () => {
    const { container } = render(<SkeletonLine />);
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('SkeletonCard has no critical a11y violations', async () => {
    const { container } = render(<SkeletonCard />);
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('EmptyState has no critical a11y violations', async () => {
    const { container } = render(<EmptyState title="空状态" description="测试描述" />);
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('ErrorBoundary has no critical a11y violations', async () => {
    const { container } = render(
      <ErrorBoundary area="测试区">
        <Safe />
      </ErrorBoundary>,
    );
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('ErrorBoundary error state has no critical a11y violations', async () => {
    function Boom() {
      throw new Error('test error');
    }
    // Suppress console.error during error boundary test
    const original = console.error;
    console.error = () => {};
    const { container } = render(
      <ErrorBoundary area="测试区">
        <Boom />
      </ErrorBoundary>,
    );
    const results = await axe(container);
    console.error = original;
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('ToastProvider has no critical a11y violations', async () => {
    const { container } = render(
      <ToastProvider>
        <div>测试内容</div>
      </ToastProvider>,
    );
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });

  it('ChatPanel empty state has no critical a11y violations', async () => {
    const { container } = render(
      <ChatPanel
        messages={[]}
        onSendMessage={noop}
        isLoading={false}
        contextTitle="测试论文"
      />,
    );
    const results = await axe(container);
    expect(results.violations.filter((v) => v.impact === 'critical')).toEqual([]);
  });
});
