import { Component } from 'react'
import type { ReactNode } from 'react'

interface Props {
  onBack: () => void
  children: ReactNode
}

interface State {
  hasError: boolean
}

export default class LiveErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-root">
          <header className="app-header">
            <button className="btn back-btn" onClick={this.props.onBack} aria-label="Back to replay list">
              ← Back
            </button>
          </header>
          <main className="app-main">
            <div className="bundle-error">
              <p className="bundle-error-msg">Something went wrong in the live view.</p>
              <button className="btn btn-primary" onClick={this.props.onBack}>
                Back to replays
              </button>
            </div>
          </main>
        </div>
      )
    }
    return this.props.children
  }
}
