import type { OverlayData, ReplayBundle, LedgerData } from '../types.ts'
import type { DisplayMode } from '../App.tsx'

interface MomentCardProps {
  overlay: OverlayData
  bundle: ReplayBundle
  mode: DisplayMode
  ledger?: LedgerData
  onDrawerToggle: () => void
  /** When true, only render narrative text (no score table, no why button). Used in Compare row. */
  textOnly?: boolean
}

function fmt(n: number) { return n.toFixed(2) }

function FanText({ overlay }: { overlay: OverlayData }) {
  const fanText = Object.values(overlay.text.fan)[0]
  const headline = fanText?.headline ?? overlay.moment_type.replace(/_/g, ' ')
  const body = fanText?.body ?? ''
  return (
    <>
      <p className="moment-headline">{headline}</p>
      {body && <p className="moment-fan">{body}</p>}
    </>
  )
}

function AnalystText({ overlay }: { overlay: OverlayData }) {
  const analystText = Object.values(overlay.text.analyst)[0]
  const headline = analystText?.headline ?? overlay.moment_type.replace(/_/g, ' ')
  const body = analystText?.body ?? ''
  return (
    <>
      <p className="moment-headline">{headline}</p>
      {body && <p className="moment-fan">{body}</p>}
    </>
  )
}

function ScoreTable({ overlay, ledger }: { overlay: OverlayData; ledger?: LedgerData }) {
  const scores = overlay.scores
  if (!scores || overlay.moment_type !== 'ghost_pass') return null
  const actual = ledger?.candidates.find(c => c.is_actual)
  const ghost = ledger?.candidates.find(c => !c.is_actual)
  return (
    <div className="analyst-score-table-wrap">
      <table className="analyst-score-table" aria-label="Component scores">
        <thead>
          <tr>
            <th></th>
            <th>Actual</th>
            <th>Better option</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Threat (T)</td>
            <td>{actual ? fmt(actual.T) : fmt(scores.components_actual['T'] ?? 0)}</td>
            <td>{ghost ? fmt(ghost.T) : fmt(scores.components_ghost['T'] ?? 0)}</td>
          </tr>
          <tr>
            <td>Progress (P)</td>
            <td>{actual ? fmt(actual.P) : fmt(scores.components_actual['P'] ?? 0)}</td>
            <td>{ghost ? fmt(ghost.P) : fmt(scores.components_ghost['P'] ?? 0)}</td>
          </tr>
          <tr>
            <td>Open path (F)</td>
            <td>{actual ? fmt(actual.F) : fmt(scores.components_actual['F'] ?? 0)}</td>
            <td>{ghost ? fmt(ghost.F) : fmt(scores.components_ghost['F'] ?? 0)}</td>
          </tr>
          <tr>
            <td>Risk (R)</td>
            <td>{actual ? fmt(actual.R) : fmt(scores.components_actual['R'] ?? 0)}</td>
            <td>{ghost ? fmt(ghost.R) : fmt(scores.components_ghost['R'] ?? 0)}</td>
          </tr>
          <tr className="score-row-total">
            <td>Total</td>
            <td>{fmt(scores.actual)}</td>
            <td className="ghost-score-cell">{fmt(scores.ghost)}</td>
          </tr>
        </tbody>
      </table>
      {(actual || ghost) && (
        <div className="analyst-defenders">
          {actual && <span>Actual pass — nearest defender: {(actual.nearest_defender_m).toFixed(1)} m</span>}
          {ghost && <span>Better option — nearest defender: {(ghost.nearest_defender_m).toFixed(1)} m</span>}
        </div>
      )}
      <p className="moment-score-explainer">
        Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.
      </p>
    </div>
  )
}

function FanScores({ overlay }: { overlay: OverlayData }) {
  const scores = overlay.scores
  if (!scores || overlay.moment_type !== 'ghost_pass') return null
  return (
    <>
      <div className="moment-scores" aria-label="Pass quality scores">
        <span className="moment-score-label">Actual pass</span>
        <span className="moment-score-value">{fmt(scores.actual)}</span>
        <span className="moment-score-label">Better option</span>
        <span className="moment-score-value ghost">{fmt(scores.ghost)}</span>
      </div>
      <p className="moment-score-explainer">
        Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.
      </p>
    </>
  )
}

function GoalScorer({ overlay, bundle }: { overlay: OverlayData; bundle: ReplayBundle }) {
  const evId = overlay.evidence.event_ids[0]
  const ev = bundle.events.find(e => e.event_id === evId)
  const scorer = ev?.player_id ? bundle.meta.players[ev.player_id] : undefined
  return scorer ? <p className="moment-scorer">Scored by {scorer.name}</p> : null
}

function WhyButton({ onToggle }: { onToggle: () => void }) {
  return (
    <button className="btn btn-why" onClick={onToggle} data-tour="why-btn">
      Why do we say this?
    </button>
  )
}

export default function MomentCard({ overlay, bundle, mode, ledger, onDrawerToggle, textOnly }: MomentCardProps) {
  const hasLedger = !!ledger

  if (textOnly) {
    // Only narrative text — used in Compare full-width row
    return (
      <div className="moment-card">
        {mode === 'analyst' ? <AnalystText overlay={overlay} /> : <FanText overlay={overlay} />}
      </div>
    )
  }

  if (mode === 'compare') {
    // Side panel: show score table only (texts go in the compare row below the pitch)
    return (
      <div className="moment-card" role="complementary" aria-label="Moment insight">
        <ScoreTable overlay={overlay} ledger={ledger} />
        {overlay.moment_type === 'goal' && <GoalScorer overlay={overlay} bundle={bundle} />}
        {hasLedger && <WhyButton onToggle={onDrawerToggle} />}
      </div>
    )
  }

  if (mode === 'analyst') {
    return (
      <div className="moment-card" role="complementary" aria-label="Moment insight">
        <AnalystText overlay={overlay} />
        <ScoreTable overlay={overlay} ledger={ledger} />
        {overlay.moment_type === 'goal' && <GoalScorer overlay={overlay} bundle={bundle} />}
        {hasLedger && <WhyButton onToggle={onDrawerToggle} />}
      </div>
    )
  }

  // Fan (default)
  return (
    <div className="moment-card" role="complementary" aria-label="Moment insight">
      <FanText overlay={overlay} />
      <FanScores overlay={overlay} />
      {overlay.moment_type === 'goal' && <GoalScorer overlay={overlay} bundle={bundle} />}
      {hasLedger && <WhyButton onToggle={onDrawerToggle} />}
    </div>
  )
}
