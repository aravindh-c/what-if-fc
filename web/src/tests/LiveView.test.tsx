import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import LiveView from '../components/LiveView.tsx'
import * as api from '../api.ts'
import type { BundleMeta, LiveOverlay, LiveState } from '../types.ts'

vi.mock('../api.ts', () => ({
  getLiveMeta: vi.fn(),
  getLiveState: vi.fn(),
  getLiveOverlays: vi.fn(),
  setSimulateOutage: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function buildMeta(): BundleMeta {
  const players: BundleMeta['players'] = {}
  for (let i = 1; i <= 11; i++) {
    players[`T01-P${String(i).padStart(2, '0')}`] = {
      name: `Home Player ${i}`, role: 'midfielder', team_id: 'T01', shirt_number: i,
    }
    players[`T02-P${String(i).padStart(2, '0')}`] = {
      name: `Away Player ${i}`, role: 'midfielder', team_id: 'T02', shirt_number: i + 11,
    }
  }
  return {
    replay_id: 'match_s7_T01_T02',
    kind: 'match',
    title: 'Home FC vs Away FC',
    teams: {
      T01: { name: 'Home FC', short_name: 'HOM', formation: '4-3-3', style: 'possession' },
      T02: { name: 'Away FC', short_name: 'AWY', formation: '4-4-2', style: 'counter' },
    },
    players,
    built_at: '2026-01-01T00:00:00Z',
    twin_version: 'twin-v1',
  }
}

function buildState(): LiveState {
  const positions = []
  for (let i = 1; i <= 11; i++) {
    positions.push({ player_id: `T01-P${String(i).padStart(2, '0')}`, team_id: 'T01', role: 'midfielder', x: i * 5, y: 20 })
    positions.push({ player_id: `T02-P${String(i).padStart(2, '0')}`, team_id: 'T02', role: 'midfielder', x: i * 5, y: 48 })
  }
  return {
    match_id: 'match_s7_T01_T02',
    clock_s: 600,
    score: { T01: 0, T02: 0 },
    latest_snapshot: {
      snapshot_id: 'sn_001',
      match_id: 'match_s7_T01_T02',
      match_clock_s: 600,
      positions,
    },
    possession_team_id: 'T01',
    events: [],
    skipped_rows: 0,
    simulate_outage: false,
    overlay_count: 0,
  }
}

function buildOverlays(): LiveOverlay[] {
  return [{
    overlay_id: 'ov_test001',
    match_id: 'match_s7_T01_T02',
    match_clock_s: 600,
    display_duration_s: 10,
    moment_type: 'ghost_pass',
    calculation_version: 'v1',
    validation_status: 'ok',
    narrative_source: 'template',
    visual: null,
    scores: null,
    evidence: { event_ids: [], metrics: {} },
    text: {
      fan: { default: { headline: 'What a ghost pass!', body: 'The ghost route was better.' } },
      analyst: { default: { headline: 'xT delta: +0.15', body: 'Analysis here.' } },
    },
    ledger: null,
    frame_team_id: 'T01',
  }]
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LiveView', () => {
  beforeEach(() => {
    vi.mocked(api.getLiveMeta).mockResolvedValue(buildMeta())
    vi.mocked(api.getLiveState).mockResolvedValue(buildState())
    vi.mocked(api.getLiveOverlays).mockResolvedValue(buildOverlays())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders 22 player counters, team names in scoreboard, and moment card headline', async () => {
    const { container } = render(
      <LiveView
        matchId="match_s7_T01_T02"
        displayMode="fan"
        onChangeMode={() => {}}
        onBack={() => {}}
      />
    )

    // Wait for "Connecting to Fabric…" to resolve and Pitch to appear
    await waitFor(() => {
      expect(container.querySelectorAll('circle[r="2"]').length).toBe(22)
    }, { timeout: 3000 })

    // Team short_names in Scoreboard
    expect(screen.getByText('HOM')).toBeTruthy()
    expect(screen.getByText('AWY')).toBeTruthy()

    // Moment card headline from the overlay
    expect(screen.getByText('What a ghost pass!')).toBeTruthy()
  })
})
