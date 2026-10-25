import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import Hero from '../components/Hero.tsx'
import type { CatalogEntry } from '../types.ts'

vi.mock('../api.ts', () => ({
  loadReplay: vi.fn(() => new Promise(() => {})),
}))

afterEach(cleanup)

const CATALOG: CatalogEntry[] = [
  { replay_id: 'scenario_forced_pass_into_traffic', kind: 'scenario', title: 'Forced Pass Into Traffic', overlays: 1 },
  { replay_id: 'scenario_high_press_escape', kind: 'scenario', title: 'High Press Escape', overlays: 1 },
  { replay_id: 'match_s7_T01_T02', kind: 'match', title: 'Season 7 · Home vs Away', overlays: 12 },
]

const catalogIds = CATALOG.map(e => e.replay_id)

describe('Landing page IDs', () => {
  it('scenario button opens an id that exists in the catalog', () => {
    const opened: string[] = []
    render(<Hero entries={CATALOG} onSelect={id => opened.push(id)} loading={false} />)
    screen.getByRole('button', { name: /See the Ghost Pass/i }).click()
    expect(opened).toHaveLength(1)
    expect(catalogIds).toContain(opened[0])
  })

  it('prefers scenario_forced_pass_into_traffic when catalog contains it', () => {
    const opened: string[] = []
    render(<Hero entries={CATALOG} onSelect={id => opened.push(id)} loading={false} />)
    screen.getByRole('button', { name: /See the Ghost Pass/i }).click()
    expect(opened[0]).toBe('scenario_forced_pass_into_traffic')
  })

  it('match button opens an id that exists in the catalog', () => {
    const opened: string[] = []
    render(<Hero entries={CATALOG} onSelect={id => opened.push(id)} loading={false} />)
    const btn = screen.queryByRole('button', { name: /Watch a full match/i })
    expect(btn).not.toBeNull()
    btn!.click()
    expect(opened).toHaveLength(1)
    expect(catalogIds).toContain(opened[0])
  })

  it('falls back to first scenario entry when preferred id is absent', () => {
    const catalog: CatalogEntry[] = [
      { replay_id: 'scenario_high_press_escape', kind: 'scenario', title: 'High Press Escape', overlays: 1 },
      { replay_id: 'match_s7_T01_T02', kind: 'match', title: 'Season 7', overlays: 12 },
    ]
    const opened: string[] = []
    render(<Hero entries={catalog} onSelect={id => opened.push(id)} loading={false} />)
    screen.getByRole('button', { name: /See the Ghost Pass/i }).click()
    expect(opened[0]).toBe('scenario_high_press_escape')
    expect(catalog.map(e => e.replay_id)).toContain(opened[0])
  })

  it('renders without throwing when catalog has no entries', () => {
    render(<Hero entries={[]} onSelect={() => {}} loading={false} />)
    expect(screen.getByRole('heading', { name: /Every pass has a ghost/i })).toBeTruthy()
  })
})
