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
      <span className="scoreboard-team home">
        <span className="team-name-row">
          <span className="team-dot home-dot" aria-hidden="true" />
          {home?.short_name ?? homeId}
        </span>
        <span className="team-dir">attacks right →</span>
      </span>
      <span className="scoreboard-score" aria-live="polite">
        {score[homeId] ?? 0}–{score[awayId] ?? 0}
      </span>
      <span className="scoreboard-team away">
        <span className="team-name-row">
          <span className="team-dot away-dot" aria-hidden="true" />
          {away?.short_name ?? awayId}
        </span>
        <span className="team-dir">← attacks left</span>
      </span>
      <span className="scoreboard-clock" aria-label={`Match clock ${fmtClock(clockS)}`}>
        {fmtClock(clockS)}
      </span>
    </div>
  )
}
