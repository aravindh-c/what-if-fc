import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import SeasonSection from '../components/SeasonSection.tsx'
import type { Season, CatalogEntry } from '../types.ts'

// ---------------------------------------------------------------------------
// Mock api
// ---------------------------------------------------------------------------

vi.mock('../api.ts', () => ({
  getSeason: vi.fn(),
}))

import { getSeason } from '../api.ts'
const mockGetSeason = getSeason as ReturnType<typeof vi.fn>

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function makeSeason(overrides: Partial<Season> = {}): Season {
  return {
    version: 1,
    generated_at: '2026-10-25T20:00:00Z',
    run_id: 'test-run-id',
    source: {
      bronze_rows: 2847,
      rejected_rows: 14,
      duplicate_rows: 5,
      silver_rows: 2828,
      matches: 3,
    },
    standings: [
      {
        team_id: 'T01', team_name: 'Kestrel Vale FC', team_color: '#1F6F5B',
        played: 3, won: 2, drawn: 1, lost: 0, goals_for: 5, goals_against: 2,
        goal_diff: 3, points: 7,
      },
      {
        team_id: 'T03', team_name: 'Saltmere Mariners', team_color: '#1D3557',
        played: 3, won: 2, drawn: 0, lost: 1, goals_for: 4, goals_against: 2,
        goal_diff: 2, points: 6,
      },
      {
        team_id: 'T04', team_name: 'Copperhill Athletic', team_color: '#B5651D',
        played: 3, won: 1, drawn: 0, lost: 2, goals_for: 3, goals_against: 5,
        goal_diff: -2, points: 3,
      },
      {
        team_id: 'T02', team_name: 'Thornfield Rovers', team_color: '#8C1C13',
        played: 3, won: 0, drawn: 1, lost: 2, goals_for: 2, goals_against: 5,
        goal_diff: -3, points: 1,
      },
    ],
    matches: [
      {
        match_id: 'match_s7_T01_T02',
        seed: 7,
        home_team_id: 'T01',
        away_team_id: 'T02',
        home_goals: 2,
        away_goals: 0,
        result: 'home_win',
        total_events: 957,
        duration_min: 90,
        is_complete: true,
        first_event_ts: '2026-10-23T18:00:00Z',
        last_event_ts: '2026-10-23T19:33:00Z',
        teams: {
          T01: {
            team_name: 'Kestrel Vale FC', team_color: '#1F6F5B',
            passes: 312, completed_passes: 278, completion_pct: 89.1,
            shots: 8, shots_on_target: 5, goals: 2, possession_proxy_pct: 52.9,
            tackles_won: 12, interceptions: 7, avg_pressure_on_passes: 0.234,
          },
          T02: {
            team_name: 'Thornfield Rovers', team_color: '#8C1C13',
            passes: 278, completed_passes: 238, completion_pct: 85.6,
            shots: 5, shots_on_target: 2, goals: 0, possession_proxy_pct: 47.1,
            tackles_won: 9, interceptions: 5, avg_pressure_on_passes: 0.289,
          },
        },
        top_players: [],
      },
      {
        match_id: 'match_s11_T01_T02',
        seed: 11,
        home_team_id: 'T01',
        away_team_id: 'T02',
        home_goals: 1,
        away_goals: 1,
        result: 'draw',
        total_events: 961,
        duration_min: 90,
        is_complete: true,
        first_event_ts: '2026-10-24T18:00:00Z',
        last_event_ts: '2026-10-24T19:34:00Z',
        teams: {
          T01: {
            team_name: 'Kestrel Vale FC', team_color: '#1F6F5B',
            passes: 312, completed_passes: 278, completion_pct: 89.1,
            shots: 8, shots_on_target: 5, goals: 1, possession_proxy_pct: 52.9,
            tackles_won: 12, interceptions: 7, avg_pressure_on_passes: 0.234,
          },
          T02: {
            team_name: 'Thornfield Rovers', team_color: '#8C1C13',
            passes: 278, completed_passes: 238, completion_pct: 85.6,
            shots: 5, shots_on_target: 2, goals: 1, possession_proxy_pct: 47.1,
            tackles_won: 9, interceptions: 5, avg_pressure_on_passes: 0.289,
          },
        },
        top_players: [
          {
            player_id: 'T01-P09',
            team_id: 'T01',
            name: 'Kian Oyelaran',
            shirt_number: 9,
            goals: 1,
            shots: 3,
            passes: 28,
            completion_pct: 82.1,
            tackles_won: 0,
            interceptions: 0,
          },
        ],
      },
    ],
    team_totals: [
      {
        team_id: 'T01', team_name: 'Kestrel Vale FC', team_color: '#1F6F5B',
        matches: 3, avg_possession_pct: 52.9, avg_completion_pct: 89.1,
        shots_per_match: 8.0, shots_on_target_per_match: 5.0,
        goals_per_match: 1.7, tackles_won_per_match: 12.0,
      },
    ],
    ...overrides,
  }
}

const ENTRIES_WITH_REPLAY: CatalogEntry[] = [
  { replay_id: 'match_s7_T01_T02', kind: 'match', title: 'KVF vs THR Seed 7', overlays: 3 },
]

const ENTRIES_WITHOUT_REPLAY: CatalogEntry[] = [
  { replay_id: 'scenario_forced_pass', kind: 'scenario', title: 'Forced pass', overlays: 1 },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SeasonSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders nothing when getSeason returns null', async () => {
    mockGetSeason.mockResolvedValue(null)
    const { container } = render(
      <SeasonSection entries={[]} onSelect={vi.fn()} />
    )
    await waitFor(() => expect(mockGetSeason).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })

  it('renders standings rows in points-descending order', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={ENTRIES_WITH_REPLAY} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    const rows = screen.getAllByRole('row').filter(r => r.querySelector('td'))
    const pointCells = rows.map(r => {
      const cells = r.querySelectorAll('td')
      return Number(cells[cells.length - 1].textContent)
    })
    expect(pointCells).toEqual([...pointCells].sort((a, b) => b - a))
  })

  it('shows Watch replay button when catalog has match_id', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={ENTRIES_WITH_REPLAY} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    const btns = screen.getAllByRole('button', { name: /watch replay/i })
    expect(btns.length).toBeGreaterThanOrEqual(1)
  })

  it('hides Watch replay button when catalog lacks match_id', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={ENTRIES_WITHOUT_REPLAY} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    expect(screen.queryByRole('button', { name: /watch replay/i })).toBeNull()
  })

  it('calls onSelect with match_id when Watch replay is clicked', async () => {
    const onSelect = vi.fn()
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={ENTRIES_WITH_REPLAY} onSelect={onSelect} />)
    await waitFor(() => screen.getByText('Standings'))

    fireEvent.click(screen.getByRole('button', { name: /watch replay.*kestrel/i }))
    expect(onSelect).toHaveBeenCalledWith('match_s7_T01_T02')
  })

  it('shows data-quality bronze row count', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={[]} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    expect(screen.getByText(/2,847/)).toBeTruthy()
  })

  it('renders top performer line for match with top_players', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={[]} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    expect(screen.getByText(/Top performer: Kian Oyelaran \(#9\)/)).toBeTruthy()
  })

  it('renders standings legend line', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={[]} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    expect(screen.getByText(/3 for a win, 1 for a draw/)).toBeTruthy()
  })

  it('renders results newest-first (highest seed first)', async () => {
    mockGetSeason.mockResolvedValue(makeSeason())
    render(<SeasonSection entries={[]} onSelect={vi.fn()} />)
    await waitFor(() => screen.getByText('Standings'))

    const scoreEls = screen.getAllByText(/^[0-9]+–[0-9]+$/)
    const scores = scoreEls.map(el => el.textContent ?? '')
    const idx11 = scores.findIndex(s => s === '1–1')
    const idx7 = scores.findIndex(s => s === '2–0')
    expect(idx11).toBeLessThan(idx7)
  })
})
