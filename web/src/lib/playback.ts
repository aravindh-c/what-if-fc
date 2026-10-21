import type { EventData, FrameData, PlayerPos, ReplayBundle, SnapshotData } from '../types.ts'
import { toDisplay } from './frame.ts'

// ---------------------------------------------------------------------------
// Positions at time t
// ---------------------------------------------------------------------------

function snapshotToDisplay(
  snap: SnapshotData,
  frames: FrameData,
  homeTeam: string,
): Map<string, PlayerPos> {
  const poss = frames.snapshots[snap.snapshot_id] ?? homeTeam
  const result = new Map<string, PlayerPos>()
  for (const p of snap.positions) {
    const [dx, dy] = toDisplay(p.x, p.y, poss, homeTeam)
    result.set(p.player_id, { playerId: p.player_id, teamId: p.team_id, x: dx, y: dy })
  }
  return result
}

/**
 * Player positions at match clock `t`.
 * Takes the last snapshot at/before t and linearly interpolates toward the
 * next snapshot. Both snapshots are converted to display frame first so
 * interpolation is always in a consistent coordinate space.
 */
export function positionsAt(
  t: number,
  bundle: ReplayBundle,
): PlayerPos[] {
  const homeTeam = Object.keys(bundle.meta.teams)[0] ?? ''
  const sorted = bundle.snapshots.slice().sort((a, b) => a.match_clock_s - b.match_clock_s)

  let beforeIdx = -1
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (sorted[i].match_clock_s <= t) { beforeIdx = i; break }
  }
  if (beforeIdx < 0) {
    if (sorted.length === 0) return []
    // Before first snapshot — use first snapshot
    return [...snapshotToDisplay(sorted[0], bundle.frames, homeTeam).values()]
  }

  const before = sorted[beforeIdx]
  const after = sorted[beforeIdx + 1]

  const bMap = snapshotToDisplay(before, bundle.frames, homeTeam)

  if (!after || after.match_clock_s === before.match_clock_s) {
    return [...bMap.values()]
  }

  const alpha = Math.min(1, (t - before.match_clock_s) / (after.match_clock_s - before.match_clock_s))
  const aMap = snapshotToDisplay(after, bundle.frames, homeTeam)

  const result: PlayerPos[] = []
  for (const [pid, bp] of bMap) {
    const ap = aMap.get(pid)
    if (!ap) {
      result.push(bp)
      continue
    }
    result.push({
      playerId: pid,
      teamId: bp.teamId,
      x: bp.x + alpha * (ap.x - bp.x),
      y: bp.y + alpha * (ap.y - bp.y),
    })
  }
  return result
}

// ---------------------------------------------------------------------------
// Ball position at time t
// ---------------------------------------------------------------------------

/**
 * Ball display position at match clock `t`.
 * During a pass, the ball is interpolated linearly along the pass line.
 */
export function ballAt(
  t: number,
  events: EventData[],
  homeTeam: string,
): [number, number] | null {
  const sorted = events.slice().sort((a, b) => a.match_clock_s - b.match_clock_s)
  const idx = findLastIdxBefore(sorted, t)
  if (idx < 0) return null

  const ev = sorted[idx]
  if (!ev.team_id) return null
  const poss = ev.team_id

  if (
    ev.event_type === 'pass' &&
    ev.x != null && ev.y != null &&
    ev.end_x != null && ev.end_y != null
  ) {
    const next = sorted[idx + 1]
    if (next && next.match_clock_s > ev.match_clock_s) {
      const alpha = Math.min(1, (t - ev.match_clock_s) / (next.match_clock_s - ev.match_clock_s))
      const bx = ev.x + alpha * (ev.end_x - ev.x)
      const by = ev.y + alpha * (ev.end_y - ev.y)
      return toDisplay(bx, by, poss, homeTeam)
    }
    return toDisplay(ev.end_x, ev.end_y, poss, homeTeam)
  }

  if (ev.x != null && ev.y != null) {
    return toDisplay(ev.x, ev.y, poss, homeTeam)
  }
  return null
}

// ---------------------------------------------------------------------------
// Score at time t
// ---------------------------------------------------------------------------

export function scoreAt(
  t: number,
  bundle: ReplayBundle,
): Record<string, number> {
  const score: Record<string, number> = {}
  for (const tid of Object.keys(bundle.meta.teams)) score[tid] = 0
  for (const ev of bundle.events) {
    if (ev.match_clock_s > t) break
    if (ev.event_type === 'goal' && ev.team_id) {
      score[ev.team_id] = (score[ev.team_id] ?? 0) + 1
    }
  }
  return score
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findLastIdxBefore(sorted: EventData[], t: number): number {
  let lo = 0, hi = sorted.length - 1, result = -1
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1
    if (sorted[mid].match_clock_s <= t) { result = mid; lo = mid + 1 }
    else hi = mid - 1
  }
  return result
}

/** Maximum match clock in the bundle's events. */
export function maxClockS(bundle: ReplayBundle): number {
  if (bundle.events.length === 0) return 0
  return bundle.events[bundle.events.length - 1].match_clock_s
}
