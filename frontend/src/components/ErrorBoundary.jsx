import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * Error boundary that catches render errors in child components.
 * Each major UI area (PDF viewer, right panel, agent workspace) gets its own
 * boundary so a crash in one area does not bring down the whole application.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error(
      `[ErrorBoundary${this.props.area ? ` ${this.props.area}` : ''}]`,
      error,
      errorInfo?.componentStack || '',
    );
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
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
            </div>
            <button
              type="button"
              onClick={this.handleRetry}
              className="theme-button-secondary inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium"
            >
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
