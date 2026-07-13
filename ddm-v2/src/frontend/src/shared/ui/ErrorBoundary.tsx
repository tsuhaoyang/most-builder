import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  /** Called when the user clicks「回儀表板」; parent should navigate to a safe tab. */
  onReset?: () => void
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * Tab-level error boundary (audit §0.1 root cause C).
 *
 * Without this, any render-phase exception in a feature tab unmounts the whole
 * React tree → full white screen with no recovery. This boundary contains the
 * failure to the tab content area and offers a way back to the dashboard.
 *
 * Mount it with `key={tab}` so switching tabs automatically remounts the
 * boundary and clears any previous error state.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the stack in console for debugging; no silent swallowing.
    console.error('[ErrorBoundary] tab render error:', error, info.componentStack)
  }

  private handleReset = () => {
    this.setState({ error: null })
    this.props.onReset?.()
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <div className="bg-white rounded-xl border p-6">
          <h2 className="text-base font-semibold text-slate-800 mb-2">此分頁發生錯誤</h2>
          <p className="text-sm text-red-600 mb-4 break-all font-mono">
            {error.message || String(error)}
          </p>
          <button
            onClick={this.handleReset}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700"
          >
            回儀表板
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
