import React from 'react';
import { AlertTriangle, RefreshCw, Send } from 'lucide-react';

interface ErrorBoundaryProps {
  area?: string;
  fallback?: React.ReactNode;
  children?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  reportSent: boolean;
}

/**
 * Error boundary that catches render errors in child components.
 * Each major UI area (PDF viewer, right panel, agent workspace) gets its own
 * boundary so a crash in one area does not bring down the whole application.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, reportSent: false };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error, reportSent: false };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error(
      `[ErrorBoundary${this.props.area ? ` ${this.props.area}` : ''}]`,
      error,
      errorInfo?.componentStack || '',
    );
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null, reportSent: false });
  };

  handleReport = (): void => {
    const payload = {
      error: this.state.error?.message || 'Unknown error',
      componentStack: this.state.error?.stack || '',
      area: this.props.area || 'unknown',
      timestamp: new Date().toISOString(),
    };

    // Fire-and-forget: don't block the UI on the report
    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {
      // Silently fail — reporting is best-effort
    });

    this.setState({ reportSent: true });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex h-full min-h-0 w-full items-center justify-center p-6">
          <div className="theme-card theme-border flex max-w-md flex-col items-center gap-4 rounded-lg border border-l-4 border-l-amber-500 p-6 shadow-lg">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50">
              <AlertTriangle size={24} className="text-amber-600" />
            </div>
            <div className="text-center">
              <p className="theme-text-primary text-sm font-semibold">
                显示异常
                {this.props.area ? ` · ${this.props.area}` : ''}
              </p>
              <p className="theme-text-muted mt-1 text-xs">
                此区域渲染时发生错误，您可以尝试重新加载。
              </p>
              {this.state.reportSent && (
                <p className="mt-2 text-xs text-emerald-500">错误报告已发送，感谢反馈</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={this.handleRetry}
                className="theme-button-secondary inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium"
              >
                <RefreshCw size={14} />
                重试
              </button>
              {!this.state.reportSent && (
                <button
                  type="button"
                  onClick={this.handleReport}
                  className="theme-button-secondary inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium"
                >
                  <Send size={14} />
                  报告问题
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    return this.props.children as React.ReactNode;
  }
}

export default ErrorBoundary;
