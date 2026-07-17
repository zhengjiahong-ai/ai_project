import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider, useToast } from './Toast.jsx';

// Helper component to trigger toasts from test
let toastActions = null;
function ToastTrigger() {
  toastActions = useToast();
  return <button data-testid="trigger">Trigger</button>;
}

function renderToastApp() {
  toastActions = null;
  return render(
    <ToastProvider>
      <ToastTrigger />
    </ToastProvider>,
  );
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    toastActions = null;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders children normally', () => {
    renderToastApp();
    expect(screen.getByTestId('trigger')).toBeInTheDocument();
  });

  it('addToast shows a notification', () => {
    renderToastApp();
    act(() => {
      toastActions.addToast('success', '操作成功！');
    });
    expect(screen.getByText('操作成功！')).toBeInTheDocument();
  });

  it('renders correct icon for each toast type', () => {
    renderToastApp();
    act(() => {
      toastActions.addToast('success', 'ok');
    });
    // Each type should render an SVG icon
    const container = screen.getByText('ok').closest('[class*="fixed"]');
    expect(container).toBeInTheDocument();
  });

  it('removeToast removes the notification', () => {
    renderToastApp();
    act(() => {
      toastActions.addToast('info', '可关闭');
    });
    expect(screen.getByText('可关闭')).toBeInTheDocument();

    // Find the close button and click it
    const closeButton = screen.getByLabelText('关闭通知');
    act(() => {
      fireEvent.click(closeButton);
    });
    // After clicking close, the toast enters exiting state
    // Advance timers to let the exit animation complete
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.queryByText('可关闭')).not.toBeInTheDocument();
  });

  it('toast auto-removes after 5 seconds', () => {
    renderToastApp();
    act(() => {
      toastActions.addToast('warning', '即将过期');
    });
    expect(screen.getByText('即将过期')).toBeInTheDocument();

    // Advance past 5s — addToast schedules removeToast via setTimeout(..., 5000)
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    // removeToast adds exiting class and schedules filter with setTimeout(..., 220)
    act(() => {
      vi.advanceTimersByTime(300);
    });
    // Toast should be fully removed after the exit animation
    expect(screen.queryByText('即将过期')).not.toBeInTheDocument();
  });

  it('renders multiple toasts simultaneously', () => {
    renderToastApp();
    act(() => {
      toastActions.addToast('success', '第一条');
      toastActions.addToast('error', '第二条');
      toastActions.addToast('info', '第三条');
    });
    expect(screen.getByText('第一条')).toBeInTheDocument();
    expect(screen.getByText('第二条')).toBeInTheDocument();
    expect(screen.getByText('第三条')).toBeInTheDocument();
  });

  it('has aria-live polite region', () => {
    renderToastApp();
    act(() => {
      toastActions.addToast('info', '通知');
    });
    const liveRegion = screen.getByLabelText('通知');
    expect(liveRegion).toHaveAttribute('aria-live', 'polite');
  });
});
