import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary.tsx';

// Suppress console.error during error-boundary tests
const originalError = console.error;
beforeAll(() => {
  console.error = vi.fn();
});
afterAll(() => {
  console.error = originalError;
});

function Boom() {
  throw new Error('simulated render failure');
}

function Safe() {
  return <div>安全内容</div>;
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary area="测试区">
        <Safe />
      </ErrorBoundary>,
    );
    expect(screen.getByText('安全内容')).toBeInTheDocument();
  });

  it('renders default error UI on child render failure', () => {
    render(
      <ErrorBoundary area="测试区">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/显示异常/)).toBeInTheDocument();
    expect(screen.getByText(/测试区/)).toBeInTheDocument();
    expect(screen.getByText('重试')).toBeInTheDocument();
  });

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary area="测试区" fallback={<div>自定义错误页</div>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText('自定义错误页')).toBeInTheDocument();
  });

  it('retry button clears error and shows children on rerender', () => {
    // Use a wrapper that conditionally renders Boom or Safe
    function Wrapper({ shouldThrow }) {
      return (
        <ErrorBoundary area="测试区">
          {shouldThrow ? <Boom /> : <Safe />}
        </ErrorBoundary>
      );
    }

    const { rerender } = render(<Wrapper shouldThrow />);

    expect(screen.getByText('重试')).toBeInTheDocument();

    // Rerender with Safe + click retry
    rerender(<Wrapper shouldThrow={false} />);
    fireEvent.click(screen.getByText('重试'));

    expect(screen.getByText('安全内容')).toBeInTheDocument();
  });
});
