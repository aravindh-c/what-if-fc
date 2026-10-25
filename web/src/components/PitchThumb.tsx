import type { OverlayVisualData } from '../types.ts'

interface PitchThumbProps {
  visual: OverlayVisualData | null | undefined
  animKey?: number
  animate?: boolean
}

const L = 105, W = 68

export default function PitchThumb({ visual, animKey = 0, animate = false }: PitchThumbProps) {
  const actual = visual?.actual
  const ghost  = visual?.ghost

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
