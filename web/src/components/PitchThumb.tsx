import type { OverlayVisualData, SnapshotData, BundleMeta } from '../types.ts'

interface PitchThumbProps {
  visual: OverlayVisualData | null | undefined
  snapshot?: SnapshotData | null
  meta?: BundleMeta | null
  animKey?: number
  animate?: boolean
}

const L = 105, W = 68

export default function PitchThumb({ visual, snapshot, meta, animKey = 0, animate = false }: PitchThumbProps) {
  const actual = visual?.actual
  const ghost  = visual?.ghost

  const teamIds = meta ? Object.keys(meta.teams) : []
  const teamColor = (tid: string) => tid === teamIds[0] ? '#E3A52B' : '#3E5C9A'

  return (
    <svg viewBox={`0 0 ${L} ${W}`} className="pitch-thumb-svg" aria-hidden="true">
      {Array.from({ length: 21 }, (_, i) => (
        <rect key={i} x={i * 5} y={0} width={5} height={W}
              fill={i % 2 === 0 ? '#2F6B3A' : '#2A6034'}/>
      ))}
      <g stroke="#F2F5EE" strokeWidth="0.3" fill="none">
        <rect x={0} y={0} width={L} height={W}/>
        <line x1={L / 2} y1={0} x2={L / 2} y2={W}/>
        <circle cx={L / 2} cy={W / 2} r={9.15}/>
        <rect x={0} y={13.84} width={16.5} height={40.32}/>
        <rect x={L - 16.5} y={13.84} width={16.5} height={40.32}/>
      </g>
      {snapshot && meta && snapshot.positions.map(p => {
        const shirt = meta.players[p.player_id]?.shirt_number
        return (
          <g key={p.player_id}>
            <circle cx={p.x} cy={p.y} r={2}
              fill={teamColor(p.team_id)} stroke="#0f1923" strokeWidth="0.25" />
            {shirt != null && (
              <text x={p.x} y={p.y + 0.65}
                fontSize="1.5" textAnchor="middle"
                fill="#0f1923" fontWeight="700"
                style={{ pointerEvents: 'none' }}>
                {shirt}
              </text>
            )}
          </g>
        )
      })}
      {actual && (
        <line
          key={`a${animKey}`}
          x1={actual.from[0]} y1={actual.from[1]}
          x2={actual.to[0]}   y2={actual.to[1]}
          stroke="#F2F5EE" strokeWidth="0.7" strokeLinecap="round"
          pathLength="1"
          className={animate ? 'pass-draw-actual' : ''}
        />
      )}
      {ghost && (
        <line
          key={`g${animKey}`}
          x1={ghost.from[0]} y1={ghost.from[1]}
          x2={ghost.to[0]}   y2={ghost.to[1]}
          stroke="#BFE8FF" strokeWidth="0.9" strokeDasharray="2.5 2"
          strokeLinecap="round"
          className={animate ? 'pitch-thumb-ghost-in' : ''}
        />
      )}
    </svg>
  )
}
