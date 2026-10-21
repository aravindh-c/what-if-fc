export interface TeamMeta {
  name: string
  short_name: string
  formation: string
  style: string
}

export interface PlayerMeta {
  name: string
  role: string
  team_id: string
  shirt_number?: number
}

export interface BundleMeta {
  replay_id: string
  kind: 'match' | 'scenario'
  title: string
  scenario_description?: string
  scenario_why?: string
  teams: Record<string, TeamMeta>
  players: Record<string, PlayerMeta>
  built_at: string
  twin_version: string
}

export interface EventData {
  event_id: string
  match_id: string
  scenario_id: string
  seed: number
  event_time: string
  match_clock_s: number
  period: 1 | 2
  event_type: string
  team_id?: string
  player_id?: string
  possession_id: number
  x?: number
  y?: number
  end_x?: number
  end_y?: number
  outcome?: string
  receiver_id?: string
  pressure_level: number
  snapshot_id?: string
}

export interface PlayerPositionData {
  player_id: string
  team_id: string
  role: string
  x: number
  y: number
}

export interface SnapshotData {
  snapshot_id: string
  match_id: string
  match_clock_s: number
  positions: PlayerPositionData[]
}

export interface PassLineData {
  from: [number, number]
  to: [number, number]
  receiver_id: string
}

export interface OverlayVisualData {
  actual?: PassLineData | null
  ghost?: PassLineData | null
  highlight_defenders: string[]
}

export interface TwinScoresData {
  actual: number
  ghost: number
  components_actual: Record<string, number>
  components_ghost: Record<string, number>
}

export interface NarrativeTextData {
  headline: string
  body: string
}

export interface OverlayTextData {
  analyst: Record<string, NarrativeTextData>
  fan: Record<string, NarrativeTextData>
  cue?: string | null
}

export interface EvidenceData {
  event_ids: string[]
  metrics: Record<string, number>
}

export interface OverlayData {
  overlay_id: string
  match_id: string
  match_clock_s: number
  display_duration_s: number
  moment_type: 'ghost_pass' | 'goal' | 'turnover' | 'momentum_swing' | 'pressure_spell'
  calculation_version: string
  validation_status: string
  narrative_source: string
  visual?: OverlayVisualData | null
  scores?: TwinScoresData | null
  evidence: EvidenceData
  text: OverlayTextData
}

export interface FrameData {
  snapshots: Record<string, string>
  overlays: Record<string, string>
}

export interface ReplayBundle {
  meta: BundleMeta
  events: EventData[]
  snapshots: SnapshotData[]
  metrics: {
    match_stats: Record<string, unknown>[]
    momentum: { minute: number; team_id: string; share: number }[]
    pressure: { minute: number; team_id: string; pressure_index: number }[]
  }
  headline_moments: Record<string, unknown>[]
  overlays: OverlayData[]
  frames: FrameData
}

export interface CatalogEntry {
  replay_id: string
  kind: string
  title: string
  overlays: number
}

export interface PlayerPos {
  playerId: string
  teamId: string
  x: number
  y: number
}
