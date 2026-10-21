import type { CatalogEntry, ReplayBundle } from './types.ts'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000'

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return res.json() as Promise<T>
}

export function listReplays(): Promise<CatalogEntry[]> {
  return fetchJson<CatalogEntry[]>('/api/replays')
}

export function loadReplay(id: string): Promise<ReplayBundle> {
  return fetchJson<ReplayBundle>(`/api/replays/${encodeURIComponent(id)}`)
}
