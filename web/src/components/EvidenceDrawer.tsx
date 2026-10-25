import { useEffect } from 'react'
import type { LedgerData, OverlayData } from '../types.ts'

interface EvidenceDrawerProps {
  ledger: LedgerData
  overlay: OverlayData
  onClose: () => void
  onSeek: (t: number) => void
}

function fmtClock(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

function fmt3(n: number) { return n.toFixed(3) }

export default function EvidenceDrawer({ ledger, overlay, onClose, onSeek }: EvidenceDrawerProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const runSource = ledger.run.source === 'agent'
    ? 'Written by the agents, checked against the evidence'
    : `Template used: ${ledger.run.fallback_reason ?? 'no reason given'}`

  const errors = ledger.run.errors_attempt1 ?? []

  return (
    <div className="evidence-panel moment-panel" role="dialog" aria-modal="true" aria-label="Why do we say this?">
      <div className="evidence-panel-header">
        <span className="evidence-panel-title">Why do we say this?</span>
        <button
          className="btn evidence-drawer-close"
          onClick={onClose}
          aria-label="Close evidence panel"
        >
          ✕
        </button>
      </div>

      <div className="evidence-panel-body">

        {/* Cited events */}
        {ledger.events.length > 0 && (
          <section className="evidence-section">
            <h3 className="evidence-section-title">Match events cited</h3>
            <ul className="evidence-events-list">
              {ledger.events.map(ev => (
                <li key={ev.event_id}>
                  <button
                    className="evidence-event-btn"
                    onClick={() => onSeek(ev.match_clock_s)}
                    title={`Seek to ${fmtClock(ev.match_clock_s)}`}
                  >
                    <span className="evidence-event-clock">{fmtClock(ev.match_clock_s)}</span>
                    <span className="evidence-event-type">{ev.event_type.replace(/_/g, ' ')}</span>
                    {ev.player_name && <span className="evidence-event-player">{ev.player_name}</span>}
                    {ev.outcome && <span className="evidence-event-outcome">{ev.outcome}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* All scored options */}
        {ledger.candidates.length > 0 && overlay.moment_type === 'ghost_pass' && (
          <section className="evidence-section">
            <h3 className="evidence-section-title">All scored options</h3>
            <div className="evidence-candidates-wrap">
            <table className="evidence-candidates-table" aria-label="All pass options scored">
              <thead>
                <tr>
                  <th>Receiver</th>
                  <th>T</th>
                  <th>P</th>
                  <th>F</th>
                  <th>R</th>
                  <th>Total</th>
                  <th>Def&nbsp;m</th>
                </tr>
              </thead>
              <tbody>
                {ledger.candidates.map((c, i) => (
                  <tr key={i} className={c.is_actual ? 'candidate-actual' : ''}>
                    <td className="candidate-name">{c.player_name ?? c.player_id ?? '—'}{c.is_actual ? ' ✓' : ''}</td>
                    <td>{fmt3(c.T)}</td>
                    <td>{fmt3(c.P)}</td>
                    <td>{fmt3(c.F)}</td>
                    <td>{fmt3(c.R)}</td>
                    <td className="candidate-total">{fmt3(c.S)}</td>
                    <td>{(c.nearest_defender_m).toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </section>
        )}

        {/* Formula */}
        <section className="evidence-section">
          <h3 className="evidence-section-title">Scoring formula</h3>
          <p className="evidence-formula-note">Tactical option score, roughly 0 to 1 (very risky passes can go below 0). Not a probability.</p>
          <dl className="evidence-formula-dl">
            <dt>Version</dt><dd>{ledger.formula.version}</dd>
            <dt>Weights</dt>
            <dd>
              {Object.entries(ledger.formula.weights).map(([k, v]) => (
                <span key={k} className="evidence-weight-chip">{k}: {v}</span>
              ))}
            </dd>
            <dt>Ghost rule</dt><dd><code>{ledger.formula.ghost_rule}</code></dd>
          </dl>
        </section>

        {/* Run story */}
        <section className="evidence-section">
          <h3 className="evidence-section-title">This insight</h3>
          <p className="evidence-run-source">{runSource}</p>
          {errors.length > 0 && (
            <p className="evidence-run-errors">First draft rejected: {errors.join('; ')}. Fixed on retry.</p>
          )}
        </section>

      </div>
    </div>
  )
}
