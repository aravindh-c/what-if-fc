import { useState, useEffect } from 'react'
import type { CatalogEntry, LiveMatch, OverlayVisualData } from '../types.ts'
import { loadReplay } from '../api.ts'
import PitchThumb from './PitchThumb.tsx'

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

const _thumbCache = new Map<string, OverlayVisualData | null>()

function useThumbnail(replayId: string): OverlayVisualData | null | undefined {
  const [visual, setVisual] = useState<OverlayVisualData | null | undefined>(undefined)

  useEffect(() => {
    if (_thumbCache.has(replayId)) {
      setVisual(_thumbCache.get(replayId) ?? null)
      return
    }
    loadReplay(replayId)
      .then(bundle => {
        const v = bundle.overlays[0]?.visual ?? null
        _thumbCache.set(replayId, v)
        setVisual(v)
      })
      .catch(() => {
        _thumbCache.set(replayId, null)
        setVisual(null)
      })
  }, [replayId])

  return visual
}

function ReplayCard({ entry, onSelect, kindLabel }: {
  entry: CatalogEntry
  onSelect: (id: string) => void
  kindLabel: (kind: string) => string
}) {
  const visual = useThumbnail(entry.replay_id)
  const cleanTitle = entry.title.replace(/\s*\(seed\s+\d+\)\s*/i, '').trim()

  return (
    <button
      className="picker-card"
      onClick={() => onSelect(entry.replay_id)}
      aria-label={`Open ${kindLabel(entry.kind).toLowerCase()}: ${cleanTitle}`}
    >
      <div className="picker-card-thumb" aria-hidden="true">
        <PitchThumb visual={visual ?? null} />
      </div>
      {entry.kind && <span className="picker-card-kind">{kindLabel(entry.kind)}</span>}
      <span className="picker-card-title">{cleanTitle}</span>
      {entry.description && (
        <span className="picker-card-desc">{entry.description}</span>
      )}
      <span className="picker-card-meta">
        {entry.overlays} key {entry.overlays === 1 ? 'moment' : 'moments'}
      </span>
    </button>
  )
}

export default function ReplayPicker({
  entries, liveMatches, loading, error, onSelect, onSelectLive, kindLabel,
}: ReplayPickerProps) {
  if (loading) return <p className="picker-status">Loading replays…</p>
  if (error)   return <p className="picker-status picker-error">Failed to load: {error}</p>

  return (
    <div className="picker-wrap">
      <section aria-label="Live matches">
        <h2 className="picker-heading">Live from Fabric</h2>
        {liveMatches.length > 0 ? (
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
        ) : (
          <p className="picker-live-empty">
            No match is streaming right now. Live mode appears here when the Fabric capacity is running.
          </p>
        )}
      </section>
      {entries.length > 0 && (
        <section aria-label="Replay library">
          <h2 className="picker-heading">Replays</h2>
          <ul className="picker-grid" role="list">
            {entries.map(e => (
              <li key={e.replay_id}>
                <ReplayCard entry={e} onSelect={onSelect} kindLabel={kindLabel} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
