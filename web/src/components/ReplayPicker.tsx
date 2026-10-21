import type { CatalogEntry } from '../types.ts'

interface ReplayPickerProps {
  entries: CatalogEntry[]
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
  kindLabel: (kind: string) => string
}

export default function ReplayPicker({ entries, loading, error, onSelect, kindLabel }: ReplayPickerProps) {
  if (loading) return <p className="picker-status">Loading replays…</p>
  if (error)   return <p className="picker-status picker-error">Failed to load: {error}</p>
  if (entries.length === 0) return <p className="picker-status">No replays found.</p>

  return (
    <div className="picker-wrap">
      <h2 className="picker-heading">Choose a replay</h2>
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
    </div>
  )
}
