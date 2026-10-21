import type { OverlayData, PlayerPos, ReplayBundle } from '../types.ts'
import { toDisplay } from '../lib/frame.ts'

interface PitchProps {
  positions: PlayerPos[]
  ball: [number, number] | null
  bundle: ReplayBundle
  activeOverlay: OverlayData | null
  homeTeam: string
}

// Pitch dimensions
const L = 105, W = 68

// Standard pitch markings (metres)
const PENALTY_DEPTH = 16.5
const PENALTY_WIDTH = 40.32
const PENALTY_Y = (W - PENALTY_WIDTH) / 2         // 13.84
const SIX_DEPTH = 5.5
const SIX_WIDTH = 18.32
const SIX_Y = (W - SIX_WIDTH) / 2                  // 24.84
const CENTER_R = 9.15
const PENALTY_SPOT = 11
const GOAL_W = 7.32
const GOAL_Y = (W - GOAL_W) / 2                    // 30.34

export default function Pitch({ positions, ball, bundle, activeOverlay, homeTeam }: PitchProps) {
  const overlayTeamId = activeOverlay
    ? bundle.frames.overlays[activeOverlay.overlay_id]
    : null

  // Convert overlay visual coords to display frame
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

  // Player-id lookup for name tags (passer, receiver, ghost receiver)
  const tagIds = new Set<string>()
  if (actualPass) { tagIds.add(actualPass.receiver_id) }
  if (ghostPass)  { tagIds.add(ghostPass.receiver_id) }
  // Passer is the player at actualPass.from position — we'll identify by position proximity
  // For simplicity, mark passer from the event's player_id via evidence
  const evId = activeOverlay?.evidence.event_ids[0]
  const evPlayerIdFromBundle = evId
    ? bundle.events.find(e => e.event_id === evId)?.player_id
    : undefined
  if (evPlayerIdFromBundle) tagIds.add(evPlayerIdFromBundle)

  const playerMap = bundle.meta.players

  // Color lookup
  const teamColors: Record<string, string> = {}
  const teamIds = Object.keys(bundle.meta.teams)
  if (teamIds[0]) teamColors[teamIds[0]] = '#E3A52B'
  if (teamIds[1]) teamColors[teamIds[1]] = '#3E5C9A'

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
      </defs>

      {/* Mown stripes */}
      {Array.from({ length: 21 }, (_, i) => (
        <rect
          key={i}
          x={i * 5} y={0} width={5} height={W}
          fill={i % 2 === 0 ? '#2F6B3A' : '#2A6034'}
        />
      ))}

      {/* Chalk lines */}
      <g stroke="#F2F5EE" strokeWidth="0.25" fill="none">
        {/* Pitch outline */}
        <rect x={0} y={0} width={L} height={W} />
        {/* Center line */}
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        {/* Center circle */}
        <circle cx={L / 2} cy={W / 2} r={CENTER_R} />
        {/* Center spot */}
        <circle cx={L / 2} cy={W / 2} r={0.4} fill="#F2F5EE" />
        {/* Left penalty area */}
        <rect x={0} y={PENALTY_Y} width={PENALTY_DEPTH} height={PENALTY_WIDTH} />
        {/* Right penalty area */}
        <rect x={L - PENALTY_DEPTH} y={PENALTY_Y} width={PENALTY_DEPTH} height={PENALTY_WIDTH} />
        {/* Left 6-yard box */}
        <rect x={0} y={SIX_Y} width={SIX_DEPTH} height={SIX_WIDTH} />
        {/* Right 6-yard box */}
        <rect x={L - SIX_DEPTH} y={SIX_Y} width={SIX_DEPTH} height={SIX_WIDTH} />
        {/* Left penalty spot */}
        <circle cx={PENALTY_SPOT} cy={W / 2} r={0.4} fill="#F2F5EE" />
        {/* Right penalty spot */}
        <circle cx={L - PENALTY_SPOT} cy={W / 2} r={0.4} fill="#F2F5EE" />
        {/* Goals (thick bar) */}
        <line x1={0} y1={GOAL_Y} x2={0} y2={GOAL_Y + GOAL_W} strokeWidth={1} />
        <line x1={L} y1={GOAL_Y} x2={L} y2={GOAL_Y + GOAL_W} strokeWidth={1} />
      </g>

      {/* Ghost pass line (dashed, behind actual) */}
      {dispGhostFrom && dispGhostTo && (
        <line
          x1={dispGhostFrom[0]} y1={dispGhostFrom[1]}
          x2={dispGhostTo[0]}   y2={dispGhostTo[1]}
          stroke="#BFE8FF"
          strokeWidth="0.6"
          strokeDasharray="2 1.5"
          strokeLinecap="round"
          filter="url(#ghost-glow)"
          className="glow-pass"
        />
      )}

      {/* Actual pass line (solid chalk) */}
      {dispActualFrom && dispActualTo && (
        <line
          x1={dispActualFrom[0]} y1={dispActualFrom[1]}
          x2={dispActualTo[0]}   y2={dispActualTo[1]}
          stroke="#F2F5EE"
          strokeWidth="0.5"
          strokeLinecap="round"
        />
      )}

      {/* Players */}
      {positions.map(p => {
        const color = teamColors[p.teamId] ?? '#888'
        const isDef = defenderIds.has(p.playerId)
        const isTag = tagIds.has(p.playerId)
        const isGhostTarget = ghostPass?.receiver_id === p.playerId
        const meta = playerMap[p.playerId]
        const initials = meta ? meta.name.split(' ').map((w: string) => w[0]).join('').slice(0, 2) : '?'

        return (
          <g key={p.playerId}>
            {isDef && (
              <circle cx={p.x} cy={p.y} r={2.6} fill="none" stroke="#F2F5EE" strokeWidth="0.4" opacity="0.7" />
            )}
            <circle
              cx={p.x} cy={p.y} r={2}
              fill={color}
              stroke="#0f1923"
              strokeWidth="0.3"
              className={isGhostTarget ? 'ghost-receiver-pulse' : ''}
            />
            {isTag && meta && (
              <text
                x={p.x} y={p.y - 2.8}
                fontSize="1.8"
                textAnchor="middle"
                fill="#F2F5EE"
                fontFamily="var(--font-display)"
                fontWeight="600"
                style={{ pointerEvents: 'none' }}
              >
                {meta.name.split(' ').pop()}
              </text>
            )}
            <text
              x={p.x} y={p.y + 0.65}
              fontSize="1.5"
              textAnchor="middle"
              fill="#0f1923"
              fontWeight="700"
              style={{ pointerEvents: 'none' }}
            >
              {initials}
            </text>
          </g>
        )
      })}

      {/* Ball */}
      {ball && (
        <circle cx={ball[0]} cy={ball[1]} r={1.2} fill="#ffffff" stroke="#333" strokeWidth="0.2" />
      )}
    </svg>
  )
}
