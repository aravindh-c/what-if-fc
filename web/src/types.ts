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

export interface LiveOverlay extends OverlayData {
  ledger: LedgerData | null
  frame_team_id: string | null
}

export interface FrameData {
  snapshots: Record<string, string>
  overlays: Record<string, string>
}

export interface LedgerCandidate {
  player_id: string | null
  player_name: string | null
  T: number
  P: number
  F: number
  R: number
  S: number
  nearest_defender_m: number
  is_actual: boolean
}

export interface LedgerFormula {
  version: string
  weights: Record<string, number>
  ghost_rule: string
}

export interface LedgerRun {
  source: string
  attempts: number
  fallback_reason?: string | null
  errors_attempt1?: string[]
  durations_s?: number[]
}

export interface LedgerEvent {
  event_id: string
  match_clock_s: number
  event_type: string
  player_name: string | null
  team_id: string
  outcome: string | null
}

export interface LedgerData {
  packet: Record<string, unknown>
  events: LedgerEvent[]
  candidates: LedgerCandidate[]
  formula: LedgerFormula
  run: LedgerRun
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
  ledgers?: Record<string, LedgerData>
}

export interface CatalogEntry {
  replay_id: string
  kind: string
  title: string
  overlays: number
  description?: string
}

export interface PlayerPos {
  playerId: string
  teamId: string
  x: number
  y: number
}

export interface LiveMatch {
  match_id: string
  event_count: number
  last_clock_s: number
  last_ingested: string
}

export interface LiveStateEvent {
  event_id: string
  match_clock_s: number
  event_type: string
  team_id?: string
  player_id?: string
}

export interface LiveState {
  match_id: string
  clock_s: number
  score: Record<string, number>
  latest_snapshot: SnapshotData | null
  possession_team_id: string | null
  events: LiveStateEvent[]
  skipped_rows: number
  simulate_outage: boolean
  overlay_count: number
}

// ---------------------------------------------------------------------------
// Season (gold layer)
// ---------------------------------------------------------------------------

export interface SeasonSource {
  bronze_rows: number
  rejected_rows: number
  duplicate_rows: number
  silver_rows: number
  matches: number
}

export interface SeasonStandingRow {
  team_id: string
  team_name?: string
  team_color?: string
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_diff: number
  points: number
}

export interface SeasonMatchTeamStats {
  team_name?: string
  team_color?: string
  passes: number
  completed_passes: number
  completion_pct: number
  shots: number
  shots_on_target: number
  goals: number
  possession_proxy_pct: number
  tackles_won: number
  interceptions: number
  avg_pressure_on_passes: number
}

export interface SeasonTopPlayer {
  player_id: string
  team_id: string
  name?: string
  shirt_number?: number
  goals: number
  shots: number
  passes: number
  completion_pct: number
  tackles_won: number
  interceptions: number
}

export interface SeasonMatch {
  match_id: string
  seed: number
  home_team_id: string
  away_team_id: string
  home_goals: number
  away_goals: number
  result: 'home_win' | 'draw' | 'away_win'
  total_events: number
  duration_min: number
  is_complete: boolean
  first_event_ts: string
  last_event_ts: string
  teams: Record<string, SeasonMatchTeamStats>
  top_players: SeasonTopPlayer[]
}

export interface SeasonTeamTotal {
  team_id: string
  team_name?: string
  team_color?: string
  matches: number
  avg_possession_pct: number
  avg_completion_pct: number
  shots_per_match: number
  shots_on_target_per_match: number
  goals_per_match: number
  tackles_won_per_match: number
}

export interface Season {
  version: number
  generated_at: string
  run_id: string
  source: SeasonSource
  standings: SeasonStandingRow[]
  matches: SeasonMatch[]
  team_totals: SeasonTeamTotal[]
}
