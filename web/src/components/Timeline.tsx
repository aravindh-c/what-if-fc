import type { OverlayData } from '../types.ts'
import { fmtClock } from '../lib/frame.ts'

interface TimelineProps {
  durationS: number
  clockS: number
  overlays: OverlayData[]
  onSeek: (t: number) => void
}

const MOMENT_COLORS: Record<string, string> = {
  ghost_pass: '#BFE8FF',
  goal:       '#E3A52B',
  turnover:   '#F24040',
}

export default function Timeline({ durationS, clockS, overlays, onSeek }: TimelineProps) {
  if (durationS <= 0) return null

  const pct = (t: number) => `${Math.min(100, (t / durationS) * 100).toFixed(2)}%`

  return (
    <div className="timeline" role="group" aria-label="Match timeline">
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
        {/* Played portion */}
        <div className="timeline-played" style={{ width: pct(clockS) }} />

        {/* Moment markers */}
        {overlays.map(ov => {
          const t = ov.match_clock_s
          const color = MOMENT_COLORS[ov.moment_type] ?? '#fff'
          return (
            <button
              key={ov.overlay_id}
              className="timeline-marker"
              style={{ left: pct(t), background: color }}
              aria-label={`${ov.moment_type} at ${fmtClock(t)}`}
              onClick={e => {
                e.stopPropagation()
                onSeek(Math.max(0, t - 3))
              }}
              tabIndex={0}
            />
          )
        })}

        {/* Playhead */}
        <div className="timeline-head" style={{ left: pct(clockS) }} aria-hidden="true" />
      </div>
    </div>
  )
}
