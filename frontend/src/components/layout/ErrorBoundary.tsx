import React from 'react';

interface State {
  hasError: boolean;
  errorMessage: string;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode; fallbackTitle?: string }, State> {
  constructor(props: { children: React.ReactNode; fallbackTitle?: string }) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error?.message || 'Unexpected rendering error' };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="panel-surface p-6 text-xs space-y-2 border-rose-500/40">
          <div className="tech-label text-rose-400">{this.props.fallbackTitle || 'Component Boundary Fallback'}</div>
          <p className="text-[var(--text-secondary)]">{this.state.errorMessage}</p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, errorMessage: '' })}
            className="arch-btn px-3 py-1.5 border border-[var(--border-strong)] bg-[var(--bg-elevated)] font-mono text-[11px]"
          >
            Reset Module
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
