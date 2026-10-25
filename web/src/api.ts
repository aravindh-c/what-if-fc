import type { BundleMeta, CatalogEntry, LiveMatch, LiveOverlay, LiveState, ReplayBundle, Season } from './types.ts'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return res.json() as Promise<T>
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return res.json() as Promise<T>
}

export function listReplays(): Promise<CatalogEntry[]> {
  return fetchJson<CatalogEntry[]>('/api/replays')
}

export function loadReplay(id: string): Promise<ReplayBundle> {
  return fetchJson<ReplayBundle>(`/api/replays/${encodeURIComponent(id)}`)
}

export function listLiveMatches(): Promise<LiveMatch[]> {
  return fetchJson<LiveMatch[]>('/api/live/matches')
}

export function watchMatch(matchId: string): Promise<{ status: string; match_id: string }> {
  return postJson(`/api/live/${encodeURIComponent(matchId)}/watch`)
}

export function getLiveState(matchId: string, sinceClockS = 0): Promise<LiveState> {
  return fetchJson<LiveState>(`/api/live/${encodeURIComponent(matchId)}/state?since_clock_s=${sinceClockS}`)
}

export function getLiveMeta(matchId: string): Promise<BundleMeta> {
  return fetchJson<BundleMeta>(`/api/live/${encodeURIComponent(matchId)}/meta`)
}

export function getLiveOverlays(matchId: string, sinceClockS = 0): Promise<LiveOverlay[]> {
  return fetchJson<LiveOverlay[]>(`/api/live/${encodeURIComponent(matchId)}/overlays?since_clock_s=${sinceClockS}`)
}

export function setSimulateOutage(matchId: string, enabled: boolean): Promise<{ match_id: string; simulate_outage: boolean }> {
  return postJson(`/api/live/${encodeURIComponent(matchId)}/simulate-outage?enabled=${enabled}`)
}

export async function getSeason(): Promise<Season | null> {
  const res = await fetch(`${BASE}/api/season`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — /api/season`)
  return res.json() as Promise<Season>
}
