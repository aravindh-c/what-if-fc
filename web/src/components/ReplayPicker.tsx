import type { CatalogEntry } from '../types.ts'

interface ReplayPickerProps {
  entries: CatalogEntry[]
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
}

export default function ReplayPicker({ entries, loading, error, onSelect }: ReplayPickerProps) {
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
              aria-label={`Open replay: ${e.title}`}
            >
              <span className="picker-card-title">{e.title}</span>
              {e.kind && <span className="picker-card-kind">{e.kind}</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
