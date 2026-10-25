import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RotateCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error in component:', error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 bg-surface rounded-[12px] border border-line text-center flex flex-col items-center justify-center gap-3">
          <div className="w-10 h-10 rounded-full bg-madder-wash text-madder flex items-center justify-center">
            <AlertTriangle className="w-5 h-5" strokeWidth={1.5} />
          </div>
          <div>
            <h4 className="font-serif font-semibold text-ink text-body">
              {this.props.fallbackTitle || 'Unable to load card'}
            </h4>
            <p className="text-meta text-ink-3 mt-1 max-w-xs">
              {this.state.error?.message || 'An unexpected rendering error occurred.'}
            </p>
          </div>
          <button
            type="button"
            onClick={this.handleRetry}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-meta font-medium text-brand bg-brand-wash hover:bg-brand/10 border border-brand/30 rounded-control transition-colors"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Retry</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
