import type { CatalogEntry, LiveMatch } from '../types.ts'

interface ReplayPickerProps {
  entries: CatalogEntry[]
  liveMatches: LiveMatch[]
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
  onSelectLive: (matchId: string) => void
  kindLabel: (kind: string) => string
}

function formatClock(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

export default function ReplayPicker({ entries, liveMatches, loading, error, onSelect, onSelectLive, kindLabel }: ReplayPickerProps) {
  if (loading) return <p className="picker-status">Loading replays…</p>
  if (error)   return <p className="picker-status picker-error">Failed to load: {error}</p>

  const hasContent = entries.length > 0 || liveMatches.length > 0
  if (!hasContent) return <p className="picker-status">No replays found.</p>

  return (
    <div className="picker-wrap">
      {liveMatches.length > 0 && (
        <>
          <h2 className="picker-heading">Live from Fabric</h2>
          <ul className="picker-grid" role="list">
            {liveMatches.map(m => (
              <li key={m.match_id}>
                <button
                  className="picker-card picker-card-live"
                  onClick={() => onSelectLive(m.match_id)}
                  aria-label={`Watch live match: ${m.match_id}`}
                >
                  <span className="picker-card-kind">
                    <span className="live-pulse-dot" aria-hidden="true" />
                    Live
                  </span>
                  <span className="picker-card-title">{m.match_id}</span>
                  <span className="picker-card-meta">{m.event_count} events · {formatClock(m.last_clock_s)}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {entries.length > 0 && (
        <>
          <h2 className="picker-heading">Replays</h2>
          <ul className="picker-grid" role="list">
            {entries.map(e => (
              <li key={e.replay_id}>
                <button
                  className="picker-card"
                  onClick={() => onSelect(e.replay_id)}
                  aria-label={`Open ${kindLabel(e.kind).toLowerCase()} replay: ${e.title}`}
                >
                  {e.kind && <span className="picker-card-kind">{kindLabel(e.kind)}</span>}
                  <span className="picker-card-title">{e.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
