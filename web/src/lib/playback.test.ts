import { describe, it, expect } from 'vitest'
import { positionsAt, ballAt, scoreAt, maxClockS } from './playback.ts'
import type { ReplayBundle, EventData, SnapshotData } from '../types.ts'

// ---------------------------------------------------------------------------
// Helpers to build minimal bundle fixtures
// ---------------------------------------------------------------------------

function makeEvent(overrides: Partial<EventData> & { event_id: string; match_clock_s: number }): EventData {
  return {
    match_id: 'm1', scenario_id: 'live', seed: 1,
    event_time: '2026-01-01T00:00:00Z',
    period: 1, event_type: 'pass', possession_id: 1,
    pressure_level: 0,
    team_id: 'T01', player_id: 'T01-P01',
    x: 20, y: 34, end_x: 50, end_y: 34, outcome: 'complete',
    receiver_id: 'T01-P02',
    ...overrides,
  }
}

function makeGoalEvent(overrides: Partial<EventData> & { event_id: string; match_clock_s: number; team_id: string }): EventData {
  return {
    match_id: 'm1', scenario_id: 'live', seed: 1,
    event_time: '2026-01-01T00:00:00Z',
    period: 1, event_type: 'goal', possession_id: 2,
    pressure_level: 0,
    player_id: 'T01-P09', x: 103, y: 34,
    ...overrides,
  }
}

function makeSnap(
  snapshot_id: string,
  match_clock_s: number,
  _teamPoss: string,
): SnapshotData {
  // 22 players: 11 each side, simplified positions
  const positions = [
    ...Array.from({ length: 11 }, (_, i) => ({
      player_id: `T01-P${String(i + 1).padStart(2, '0')}`,
      team_id: 'T01', role: i === 0 ? 'GK' : 'DF',
      x: 10 + i * 5, y: 20 + i * 2,
    })),
    ...Array.from({ length: 11 }, (_, i) => ({
      player_id: `T02-P${String(i + 1).padStart(2, '0')}`,
      team_id: 'T02', role: i === 0 ? 'GK' : 'DF',
      x: 60 + i * 3, y: 30 + i * 2,
    })),
  ]
  return { snapshot_id, match_id: 'm1', match_clock_s, positions }
}

function makeBundle(overrides: {
  events?: EventData[]
  snapshots?: SnapshotData[]
  frames?: Partial<{ snapshots: Record<string, string>; overlays: Record<string, string> }>
}): ReplayBundle {
  const events = overrides.events ?? []
  const snapshots = overrides.snapshots ?? []
  const frames = {
    snapshots: overrides.frames?.snapshots ?? {},
    overlays: overrides.frames?.overlays ?? {},
  }
  return {
    meta: {
      replay_id: 'm1', kind: 'match', title: 'Test', built_at: '', twin_version: 'twin-v1',
      teams: { T01: { name: 'Home', short_name: 'HOM', formation: '4-3-3', style: 'possession' },
               T02: { name: 'Away', short_name: 'AWY', formation: '4-3-3', style: 'direct' } },
      players: {},
    },
    events, snapshots, frames,
    metrics: { match_stats: [], momentum: [], pressure: [] },
    headline_moments: [],
    overlays: [],
  }
}

// ---------------------------------------------------------------------------
// positionsAt
// ---------------------------------------------------------------------------

describe('positionsAt', () => {
  it('returns empty array when no snapshots', () => {
    const bundle = makeBundle({})
    expect(positionsAt(100, bundle)).toEqual([])
  })

  it('returns first snapshot before its time', () => {
    const snap = makeSnap('s1', 60, 'T01')
    const bundle = makeBundle({
      snapshots: [snap],
      frames: { snapshots: { s1: 'T01' } },
    })
    const pos = positionsAt(30, bundle)
    expect(pos).toHaveLength(22)
    // T01 in possession (home) — no flip
    const p1 = pos.find(p => p.playerId === 'T01-P01')!
    expect(p1.x).toBeCloseTo(snap.positions[0].x)
    expect(p1.y).toBeCloseTo(snap.positions[0].y)
  })

  it('interpolates between two snapshots', () => {
    const s1 = makeSnap('s1', 0, 'T01')
    const s2 = makeSnap('s2', 100, 'T01')
    // Move T01-P01 in s2
    s2.positions[0] = { ...s2.positions[0], x: 50, y: 34 }

    const bundle = makeBundle({
      snapshots: [s1, s2],
      frames: { snapshots: { s1: 'T01', s2: 'T01' } },
    })
    // At t=50, alpha=0.5 → position midway between s1.x=10 and s2.x=50
    const pos = positionsAt(50, bundle)
    const p1 = pos.find(p => p.playerId === 'T01-P01')!
    expect(p1.x).toBeCloseTo(30) // (10 + 50) / 2
  })

  it('converts away-possession snapshot to display frame', () => {
    const snap = makeSnap('s1', 60, 'T02')
    const bundle = makeBundle({
      snapshots: [snap],
      frames: { snapshots: { s1: 'T02' } },
    })
    const pos = positionsAt(60, bundle)
    // T02 is away → flip: display_x = 105 - x
    const raw = snap.positions[0]
    const p = pos.find(p => p.playerId === raw.player_id)!
    expect(p.x).toBeCloseTo(105 - raw.x)
    expect(p.y).toBeCloseTo(68 - raw.y)
  })
})

// ---------------------------------------------------------------------------
// ballAt
// ---------------------------------------------------------------------------

describe('ballAt', () => {
  it('returns null when no events', () => {
    expect(ballAt(50, [], 'T01')).toBeNull()
  })

  it('returns event position for non-pass', () => {
    const ev = makeEvent({ event_id: 'e1', match_clock_s: 10, event_type: 'carry' })
    expect(ballAt(10, [ev], 'T01')).toEqual([20, 34])
  })

  it('interpolates ball along pass line', () => {
    const pass = makeEvent({ event_id: 'e1', match_clock_s: 0, x: 0, y: 34, end_x: 50, end_y: 34 })
    const next = makeEvent({ event_id: 'e2', match_clock_s: 10, event_type: 'reception', x: 50, y: 34 })
    const ball = ballAt(5, [pass, next], 'T01')!
    expect(ball[0]).toBeCloseTo(25) // midway between 0 and 50
    expect(ball[1]).toBeCloseTo(34)
  })

  it('flips ball coordinates for away possession', () => {
    const ev = makeEvent({ event_id: 'e1', match_clock_s: 0, team_id: 'T02', event_type: 'carry', x: 80, y: 40 })
    const ball = ballAt(0, [ev], 'T01')!
    expect(ball[0]).toBeCloseTo(105 - 80)
    expect(ball[1]).toBeCloseTo(68 - 40)
  })
})

// ---------------------------------------------------------------------------
// scoreAt
// ---------------------------------------------------------------------------

describe('scoreAt', () => {
  it('starts at 0-0', () => {
    const bundle = makeBundle({})
    const s = scoreAt(0, bundle)
    expect(s['T01']).toBe(0)
    expect(s['T02']).toBe(0)
  })

  it('counts goals before t', () => {
    const events: EventData[] = [
      makeGoalEvent({ event_id: 'g1', match_clock_s: 100, team_id: 'T01' }),
      makeGoalEvent({ event_id: 'g2', match_clock_s: 200, team_id: 'T02' }),
      makeGoalEvent({ event_id: 'g3', match_clock_s: 300, team_id: 'T01' }),
    ]
    const bundle = makeBundle({ events })
    expect(scoreAt(150, bundle)).toMatchObject({ T01: 1, T02: 0 })
    expect(scoreAt(250, bundle)).toMatchObject({ T01: 1, T02: 1 })
    expect(scoreAt(300, bundle)).toMatchObject({ T01: 2, T02: 1 })
  })

  it('excludes goals strictly after t', () => {
    const events: EventData[] = [
      makeGoalEvent({ event_id: 'g1', match_clock_s: 100, team_id: 'T01' }),
    ]
    expect(scoreAt(99, makeBundle({ events }))).toMatchObject({ T01: 0 })
  })
})

// ---------------------------------------------------------------------------
// maxClockS
// ---------------------------------------------------------------------------

describe('maxClockS', () => {
  it('returns 0 for empty bundle', () => {
    expect(maxClockS(makeBundle({}))).toBe(0)
  })

  it('returns last event clock', () => {
    const events = [
      makeEvent({ event_id: 'e1', match_clock_s: 100 }),
      makeEvent({ event_id: 'e2', match_clock_s: 200 }),
    ]
    expect(maxClockS(makeBundle({ events }))).toBe(200)
  })
})
