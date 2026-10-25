import type { OverlayData } from '../types.ts'
import { fmtClock } from '../lib/frame.ts'

interface TimelineProps {
  durationS: number
  clockS: number
  overlays: OverlayData[]
  onSeek: (t: number) => void
  onPlay: () => void
}

const MOMENT_COLORS: Record<string, string> = {
  ghost_pass: '#BFE8FF',
  goal:       '#E3A52B',
  turnover:   '#F24040',
}

const KEY_ITEMS = [
  { color: '#BFE8FF', label: 'Ghost pass' },
  { color: '#E3A52B', label: 'Goal' },
  { color: '#F24040', label: 'Turnover' },
]

export default function Timeline({ durationS, clockS, overlays, onSeek, onPlay }: TimelineProps) {
  if (durationS <= 0) return null

  const pct = (t: number) => `${Math.min(100, (t / durationS) * 100).toFixed(2)}%`

  return (
    <div className="timeline" role="group" aria-label="Match timeline" data-tour="timeline">
      <div
        className="timeline-track"
        role="slider"
        aria-valuemin={0}
        aria-valuemax={Math.round(durationS)}
        aria-valuenow={Math.round(clockS)}
        aria-valuetext={fmtClock(clockS)}
        tabIndex={0}
        onClick={e => {
          const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
          const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
          onSeek(frac * durationS)
        }}
        onKeyDown={e => {
          if (e.key === 'ArrowLeft')  onSeek(Math.max(0, clockS - 5))
          if (e.key === 'ArrowRight') onSeek(Math.min(durationS, clockS + 5))
          if (e.key === 'Home')  onSeek(0)
          if (e.key === 'End')   onSeek(durationS)
        }}
      >
        <div className="timeline-played" style={{ width: pct(clockS) }} />

        {overlays.map(ov => {
          const t = ov.match_clock_s
          const color = MOMENT_COLORS[ov.moment_type] ?? '#fff'
          return (
            <button
              key={ov.overlay_id}
              className="timeline-marker"
              style={{ left: pct(t), background: color }}
              aria-label={`${ov.moment_type.replace(/_/g, ' ')} at ${fmtClock(t)}`}
              onClick={e => {
                e.stopPropagation()
                onSeek(Math.max(0, t - 3))
                onPlay()
              }}
              tabIndex={0}
            />
          )
        })}

        <div className="timeline-head" style={{ left: pct(clockS) }} aria-hidden="true" />
      </div>
      <div className="timeline-key" aria-label="Timeline key">
        {KEY_ITEMS.map(({ color, label }) => (
          <span key={label} className="timeline-key-item">
            <span className="timeline-key-dot" style={{ background: color }} aria-hidden="true"/>
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
