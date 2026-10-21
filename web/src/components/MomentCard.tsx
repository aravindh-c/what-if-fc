import type { OverlayData, ReplayBundle } from '../types.ts'

interface MomentCardProps {
  overlay: OverlayData
  bundle: ReplayBundle
}

export default function MomentCard({ overlay, bundle }: MomentCardProps) {
  const scores = overlay.scores
  const fanText = Object.values(overlay.text.fan)[0]
  const headline = fanText?.headline ?? overlay.moment_type.replace(/_/g, ' ')
  const body = fanText?.body ?? ''

  return (
    <div className="moment-card-overlay" role="complementary" aria-label="Moment insight">
      <div className="moment-card">
        <p className="moment-headline">{headline}</p>
        {body && <p className="moment-fan">{body}</p>}
        {scores && overlay.moment_type === 'ghost_pass' && (
          <div className="moment-scores" aria-label="Pass quality scores">
            <span className="moment-score-label">Actual pass</span>
            <span className="moment-score-value">{scores.actual.toFixed(2)}</span>
            <span className="moment-score-label">Better option</span>
            <span className="moment-score-value ghost">{scores.ghost.toFixed(2)}</span>
          </div>
        )}
        {overlay.moment_type === 'goal' && (() => {
          const evId = overlay.evidence.event_ids[0]
          const ev = bundle.events.find(e => e.event_id === evId)
          const scorer = ev?.player_id ? bundle.meta.players[ev.player_id] : undefined
          return scorer ? (
            <p className="moment-scorer">Scored by {scorer.name}</p>
          ) : null
        })()}
      </div>
    </div>
  )
}
