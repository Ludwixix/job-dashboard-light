import React from 'react';

export default class SafeErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 my-4 bg-rose-950/40 border border-rose-800 rounded-xl text-rose-200">
          <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
          <p className="text-sm opacity-80">{this.state.error?.message || 'Unexpected application error.'}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 px-4 py-2 bg-rose-800 hover:bg-rose-700 text-white rounded-lg text-sm font-semibold transition"
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
