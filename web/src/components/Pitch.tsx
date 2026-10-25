import type { OverlayData, PlayerPos, ReplayBundle } from '../types.ts'
import { toDisplay } from '../lib/frame.ts'

interface PitchProps {
  positions: PlayerPos[]
  ball: [number, number] | null
  bundle: ReplayBundle
  activeOverlay: OverlayData | null
  homeTeam: string
  animKey?: number
}

const L = 105, W = 68
const PENALTY_DEPTH = 16.5
const PENALTY_WIDTH = 40.32
const PENALTY_Y = (W - PENALTY_WIDTH) / 2   // 13.84
const SIX_DEPTH = 5.5
const SIX_WIDTH = 18.32
const SIX_Y = (W - SIX_WIDTH) / 2           // 24.84
const CENTER_R = 9.15
const PENALTY_SPOT = 11                      // distance from goal line
const GOAL_W = 7.32
const GOAL_Y = (W - GOAL_W) / 2             // 30.34

// Penalty arc: portion of circle r=9.15 centred at penalty spot that lies
// outside the penalty area. Intersection with penalty area edge at x=PENALTY_DEPTH:
//   cos θ = (PENALTY_DEPTH - PENALTY_SPOT) / 9.15 ≈ 0.601, θ ≈ 53.1°
//   intersection y offset = 9.15 * sin(53.1°) ≈ 7.32
const ARC_Y_OFFSET = 7.32
const ARC_LEFT_X = PENALTY_DEPTH              // 16.5
const ARC_LEFT_TOP = W / 2 - ARC_Y_OFFSET    // 26.68
const ARC_LEFT_BOT = W / 2 + ARC_Y_OFFSET    // 41.32
const ARC_RIGHT_X = L - PENALTY_DEPTH         // 88.5

export default function Pitch({ positions, ball, bundle, activeOverlay, homeTeam, animKey = 0 }: PitchProps) {
  const overlayTeamId = activeOverlay
    ? bundle.frames.overlays[activeOverlay.overlay_id]
    : null

  const visual = activeOverlay?.visual
  const actualPass = visual?.actual
  const ghostPass = visual?.ghost

  function ovToDisplay(pt: [number, number]): [number, number] {
    if (!overlayTeamId) return pt
    return toDisplay(pt[0], pt[1], overlayTeamId, homeTeam)
  }

  const dispActualFrom = actualPass ? ovToDisplay(actualPass.from) : null
  const dispActualTo   = actualPass ? ovToDisplay(actualPass.to)   : null
  const dispGhostFrom  = ghostPass  ? ovToDisplay(ghostPass.from)  : null
  const dispGhostTo    = ghostPass  ? ovToDisplay(ghostPass.to)    : null

  const defenderIds = new Set(visual?.highlight_defenders ?? [])

  // Name tags: passer (from evidence event), receiver, ghost receiver
  const tagIds = new Set<string>()
  if (actualPass) tagIds.add(actualPass.receiver_id)
  if (ghostPass)  tagIds.add(ghostPass.receiver_id)
  const evId = activeOverlay?.evidence.event_ids[0]
  const passerId = evId ? bundle.events.find(e => e.event_id === evId)?.player_id : undefined
  if (passerId) tagIds.add(passerId)

  const playerMap = bundle.meta.players

  const teamIds = Object.keys(bundle.meta.teams)
  const teamColors: Record<string, string> = {}
  if (teamIds[0]) teamColors[teamIds[0]] = '#E3A52B'
  if (teamIds[1]) teamColors[teamIds[1]] = '#3E5C9A'

  // Collect tag data for second-pass rendering (so tags sit above all counters)
  const tagData: Array<{ x: number; y: number; name: string }> = []
  for (const p of positions) {
    if (!tagIds.has(p.playerId)) continue
    const meta = playerMap[p.playerId]
    if (!meta) continue
    const name = meta.name.split(' ').pop() ?? ''
    tagData.push({ x: p.x, y: p.y, name })
  }

  return (
    <svg
      viewBox={`0 0 ${L} ${W}`}
      className="pitch-svg"
      role="img"
      aria-label="Football pitch with player positions"
    >
      <defs>
        <filter id="ghost-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="0.8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        {dispGhostFrom && dispGhostTo && (
          <mask id={`ghost-mask-${animKey}`} maskUnits="userSpaceOnUse" x="0" y="0" width="105" height="68">
            <line
              key={`ghost-mask-line-${animKey}`}
              x1={dispGhostFrom[0]} y1={dispGhostFrom[1]}
              x2={dispGhostTo[0]}   y2={dispGhostTo[1]}
              stroke="white" strokeWidth="4"
              pathLength="1"
              className="ghost-mask-draw"
            />
          </mask>
        )}
      </defs>

      {/* Mown stripes — no borders, pure fill */}
      {Array.from({ length: 21 }, (_, i) => (
        <rect key={i} x={i * 5} y={0} width={5} height={W}
          fill={i % 2 === 0 ? '#2F6B3A' : '#2A6034'} />
      ))}

      {/* Chalk markings */}
      <g stroke="#F2F5EE" strokeWidth="0.25" fill="none">
        <rect x={0} y={0} width={L} height={W} />
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        <circle cx={L / 2} cy={W / 2} r={CENTER_R} />
        <circle cx={L / 2} cy={W / 2} r={0.4} fill="#F2F5EE" />

        {/* Penalty areas */}
        <rect x={0} y={PENALTY_Y} width={PENALTY_DEPTH} height={PENALTY_WIDTH} />
        <rect x={L - PENALTY_DEPTH} y={PENALTY_Y} width={PENALTY_DEPTH} height={PENALTY_WIDTH} />

        {/* 6-yard boxes */}
        <rect x={0} y={SIX_Y} width={SIX_DEPTH} height={SIX_WIDTH} />
        <rect x={L - SIX_DEPTH} y={SIX_Y} width={SIX_DEPTH} height={SIX_WIDTH} />

        {/* Penalty spots */}
        <circle cx={PENALTY_SPOT} cy={W / 2} r={0.4} fill="#F2F5EE" />
        <circle cx={L - PENALTY_SPOT} cy={W / 2} r={0.4} fill="#F2F5EE" />

        {/* Penalty arcs — portion outside penalty area, sweep clockwise on left, CCW on right */}
        <path d={`M ${ARC_LEFT_X} ${ARC_LEFT_TOP} A ${CENTER_R} ${CENTER_R} 0 0 1 ${ARC_LEFT_X} ${ARC_LEFT_BOT}`} />
        <path d={`M ${ARC_RIGHT_X} ${ARC_LEFT_TOP} A ${CENTER_R} ${CENTER_R} 0 0 0 ${ARC_RIGHT_X} ${ARC_LEFT_BOT}`} />

        {/* Goal lines */}
        <line x1={0} y1={GOAL_Y} x2={0} y2={GOAL_Y + GOAL_W} strokeWidth={1} />
        <line x1={L} y1={GOAL_Y} x2={L} y2={GOAL_Y + GOAL_W} strokeWidth={1} />

        {/* Corner arcs (r = 1 m) */}
        <path d="M 1 0 A 1 1 0 0 1 0 1" />
        <path d="M 104 0 A 1 1 0 0 0 105 1" />
        <path d="M 0 67 A 1 1 0 0 1 1 68" />
        <path d="M 104 68 A 1 1 0 0 0 105 67" />
      </g>

      {/* Actual pass line — draws over 0.6 s */}
      {dispActualFrom && dispActualTo && (
        <line
          key={`actual-line-${animKey}`}
          x1={dispActualFrom[0]} y1={dispActualFrom[1]}
          x2={dispActualTo[0]}   y2={dispActualTo[1]}
          stroke="#F2F5EE" strokeWidth="0.5" strokeLinecap="round"
          pathLength="1"
          className="pass-draw-actual"
        />
      )}

      {/* Ghost pass line — revealed by mask over 1.2 s starting at 0.6 s */}
      {dispGhostFrom && dispGhostTo && (
        <line
          key={`ghost-line-${animKey}`}
          x1={dispGhostFrom[0]} y1={dispGhostFrom[1]}
          x2={dispGhostTo[0]}   y2={dispGhostTo[1]}
          stroke="#BFE8FF" strokeWidth="0.6"
          strokeDasharray="2 1.5" strokeLinecap="round"
          filter="url(#ghost-glow)" className="glow-pass"
          mask={`url(#ghost-mask-${animKey})`}
        />
      )}

      {/* Players — first pass: all counters (defender rings + filled circles + number labels) */}
      {positions.map(p => {
        const color = teamColors[p.teamId] ?? '#888'
        const isDef = defenderIds.has(p.playerId)
        const isGhostTarget = ghostPass?.receiver_id === p.playerId
        const meta = playerMap[p.playerId]
        const label = meta?.shirt_number != null
          ? String(meta.shirt_number)
          : (meta ? meta.name.split(' ').map((w: string) => w[0]).join('').slice(0, 2) : '?')

        return (
          <g key={p.playerId}>
            {isDef && (
              <circle cx={p.x} cy={p.y} r={2.6}
                fill="none" stroke="#F2F5EE" strokeWidth="0.4" opacity="0.7" />
            )}
            <circle
              key={isGhostTarget ? `${p.playerId}-pulse-${animKey}` : p.playerId}
              cx={p.x} cy={p.y} r={2}
              fill={color} stroke="#0f1923" strokeWidth="0.3"
              className={isGhostTarget ? 'ghost-receiver-pulse' : ''}
            />
            <text x={p.x} y={p.y + 0.65}
              fontSize="1.5" textAnchor="middle"
              fill="#0f1923" fontWeight="700"
              style={{ pointerEvents: 'none' }}
            >
              {label}
            </text>
          </g>
        )
      })}

      {/* Players — second pass: name tag pills drawn on top of all counters */}
      {tagData.map(({ x, y, name }) => {
        const charW = 1.55
        const pillW = Math.max(name.length * charW + 2.0, 6)
        const pillH = 2.6
        const pillX = x - pillW / 2
        const pillY = y - 5.0
        return (
          <g key={`tag-${x}-${y}`} style={{ pointerEvents: 'none' }}>
            <rect
              x={pillX} y={pillY}
              width={pillW} height={pillH}
              rx={1.2} ry={1.2}
              fill="rgba(20,40,25,0.82)"
            />
            <text x={x} y={pillY + pillH - 0.55}
              fontSize="1.8" textAnchor="middle"
              fill="#F2F5EE" fontFamily="var(--font-display)" fontWeight="600"
            >
              {name}
            </text>
          </g>
        )
      })}

      {/* Ball */}
      {ball && (
        <circle cx={ball[0]} cy={ball[1]} r={1.2}
          fill="#ffffff" stroke="#333" strokeWidth="0.2" />
      )}
    </svg>
  )
}
