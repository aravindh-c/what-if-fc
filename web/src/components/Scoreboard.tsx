import { fmtClock } from '../lib/frame.ts'
import type { ReplayBundle } from '../types.ts'

interface ScoreboardProps {
  bundle: ReplayBundle
  score: Record<string, number>
  clockS: number
}

export default function Scoreboard({ bundle, score, clockS }: ScoreboardProps) {
  const teamIds = Object.keys(bundle.meta.teams)
  const homeId = teamIds[0] ?? ''
  const awayId = teamIds[1] ?? ''
  const home = bundle.meta.teams[homeId]
  const away = bundle.meta.teams[awayId]

  return (
    <div className="scoreboard" aria-label="Scoreboard">
      <span className="scoreboard-team home">{home?.short_name ?? homeId}</span>
      <span className="scoreboard-score" aria-live="polite">
        {score[homeId] ?? 0}–{score[awayId] ?? 0}
      </span>
      <span className="scoreboard-team away">{away?.short_name ?? awayId}</span>
      <span className="scoreboard-clock" aria-label={`Match clock ${fmtClock(clockS)}`}>
        {fmtClock(clockS)}
      </span>
    </div>
  )
}
