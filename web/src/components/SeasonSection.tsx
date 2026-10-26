import { useState, useEffect } from 'react'
import type { CatalogEntry, Season, SeasonMatch, SeasonStandingRow, SeasonTeamTotal } from '../types.ts'
import { getSeason } from '../api.ts'

interface SeasonSectionProps {
  entries: CatalogEntry[]
  onSelect: (id: string) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  return new Date(isoStr).toLocaleDateString()
}

// ---------------------------------------------------------------------------
// Standings table
// ---------------------------------------------------------------------------

function StandingsTable({ standings }: { standings: SeasonStandingRow[] }) {
  return (
    <div className="season-standings-wrap">
      <h3 className="season-subhead">Standings</h3>
      <table className="season-standings" aria-label="Season standings">
        <thead>
          <tr>
            <th className="col-team">Team</th>
            <th title="Played"><abbr title="Played">P</abbr></th>
            <th title="Won"><abbr title="Won">W</abbr></th>
            <th title="Drawn"><abbr title="Drawn">D</abbr></th>
            <th title="Lost"><abbr title="Lost">L</abbr></th>
            <th className="col-gf" title="Goals for"><abbr title="Goals for">GF</abbr></th>
            <th className="col-ga" title="Goals against"><abbr title="Goals against">GA</abbr></th>
            <th title="Goal difference"><abbr title="Goal difference">GD</abbr></th>
            <th title="Points"><abbr title="Points">Pts</abbr></th>
          </tr>
        </thead>
        <tbody>
          {standings.map((row, i) => (
            <tr key={row.team_id} className={i === 0 ? 'row-top' : ''}>
              <td className="col-team">
                {row.team_color && (
                  <span
                    className="team-swatch"
                    style={{ background: row.team_color }}
                    aria-hidden="true"
                  />
                )}
                {row.team_name ?? row.team_id}
              </td>
              <td>{row.played}</td>
              <td>{row.won}</td>
              <td>{row.drawn}</td>
              <td>{row.lost}</td>
              <td className="col-gf">{row.goals_for}</td>
              <td className="col-ga">{row.goals_against}</td>
              <td className={row.goal_diff > 0 ? 'pos' : row.goal_diff < 0 ? 'neg' : ''}>
                {row.goal_diff > 0 ? `+${row.goal_diff}` : row.goal_diff}
              </td>
              <td className="col-pts">{row.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="standings-legend">
        <abbr title="Played">P</abbr> played ·{' '}
        <abbr title="Won">W</abbr> won ·{' '}
        <abbr title="Drawn">D</abbr> drawn ·{' '}
        <abbr title="Lost">L</abbr> lost ·{' '}
        <abbr title="Goals for">GF</abbr> goals for ·{' '}
        <abbr title="Goals against">GA</abbr> goals against ·{' '}
        <abbr title="Goal difference">GD</abbr> goal difference ·{' '}
        <abbr title="Points">Pts</abbr> points (3 for a win, 1 for a draw)
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Comparison bar (splits a metric home vs away)
// ---------------------------------------------------------------------------

interface CompBarProps {
  label: string
  homeVal: number
  awayVal: number
  homeColor: string
  awayColor: string
  fmt?: (n: number) => string
}

function CompBar({ label, homeVal, awayVal, homeColor, awayColor, fmt }: CompBarProps) {
  const total = homeVal + awayVal
  const homePct = total > 0 ? (homeVal / total) * 100 : 50
  const awayPct = 100 - homePct
  const f = fmt ?? ((n: number) => n.toFixed(1))
  return (
    <div className="comp-bar-row">
      <span className="comp-bar-val home">{f(homeVal)}</span>
      <div className="comp-bar-track" aria-label={`${label}: ${f(homeVal)} vs ${f(awayVal)}`}>
        <div className="comp-bar-home" style={{ width: `${homePct}%`, background: homeColor }} />
        <div className="comp-bar-away" style={{ width: `${awayPct}%`, background: awayColor }} />
      </div>
      <span className="comp-bar-val away">{f(awayVal)}</span>
      <span className="comp-bar-label">{label}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Match result card
// ---------------------------------------------------------------------------

function MatchResultCard({
  match,
  entries,
  onSelect,
}: {
  match: SeasonMatch
  entries: CatalogEntry[]
  onSelect: (id: string) => void
}) {
  const homeStats = match.teams[match.home_team_id]
  const awayStats = match.teams[match.away_team_id]
  const homeName = homeStats?.team_name ?? match.home_team_id
  const awayName = awayStats?.team_name ?? match.away_team_id
  const homeColor = homeStats?.team_color ?? '#E3A52B'
  const awayColor = awayStats?.team_color ?? '#3E5C9A'
  const hasReplay = entries.some(e => e.replay_id === match.match_id)
  const topPlayer = match.top_players[0]

  return (
    <div className="season-result-card">
      <div className="result-score-row">
        <span className="result-team home-team" style={{ color: homeColor }}>{homeName}</span>
        <span className="result-score">
          {match.home_goals}–{match.away_goals}
        </span>
        <span className="result-team away-team" style={{ color: awayColor }}>{awayName}</span>
      </div>
      {homeStats && awayStats && (
        <div className="comp-bars">
          <CompBar
            label="Possession (event share)"
            homeVal={homeStats.possession_proxy_pct}
            awayVal={awayStats.possession_proxy_pct}
            homeColor={homeColor}
            awayColor={awayColor}
            fmt={n => `${n.toFixed(1)}%`}
          />
          <CompBar
            label="Pass completion"
            homeVal={homeStats.completion_pct}
            awayVal={awayStats.completion_pct}
            homeColor={homeColor}
            awayColor={awayColor}
            fmt={n => `${n.toFixed(1)}%`}
          />
          <CompBar
            label="Shots"
            homeVal={homeStats.shots}
            awayVal={awayStats.shots}
            homeColor={homeColor}
            awayColor={awayColor}
            fmt={n => String(Math.round(n))}
          />
        </div>
      )}
      {topPlayer?.name != null && (
        <p className="result-top-performer">
          Top performer: {topPlayer.name}
          {topPlayer.shirt_number != null ? ` (#${topPlayer.shirt_number})` : ''},
          {' '}{topPlayer.goals} {topPlayer.goals === 1 ? 'goal' : 'goals'},{' '}
          {topPlayer.shots} {topPlayer.shots === 1 ? 'shot' : 'shots'}
        </p>
      )}
      {hasReplay && (
        <button
          className="btn btn-watch-replay"
          onClick={() => onSelect(match.match_id)}
          aria-label={`Watch replay for ${homeName} vs ${awayName}`}
        >
          Watch replay
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Team comparison tiles
// ---------------------------------------------------------------------------

function TeamCompTiles({ teamTotals }: { teamTotals: SeasonTeamTotal[] }) {
  return (
    <div className="season-team-tiles">
      <h3 className="season-subhead">Team averages</h3>
      <div className="team-tiles-grid">
        {teamTotals.map(t => (
          <div key={t.team_id} className="team-tile">
            <div
              className="team-tile-band"
              style={{ background: t.team_color ?? '#444' }}
              aria-hidden="true"
            />
            <p className="team-tile-name">{t.team_name ?? t.team_id}</p>
            <dl className="team-tile-stats">
              <div>
                <dt>Possession (event share)</dt>
                <dd>{t.avg_possession_pct.toFixed(1)}%</dd>
              </div>
              <div>
                <dt>Pass completion</dt>
                <dd>{t.avg_completion_pct.toFixed(1)}%</dd>
              </div>
              <div>
                <dt>Shots per match</dt>
                <dd>{t.shots_per_match.toFixed(1)}</dd>
              </div>
              <div>
                <dt>Goals per match</dt>
                <dd>{t.goals_per_match.toFixed(1)}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Data quality strip
// ---------------------------------------------------------------------------

function DataQualityStrip({ season }: { season: Season }) {
  const s = season.source
  const [tipVisible, setTipVisible] = useState(false)

  return (
    <div className="dq-strip">
      <span className="dq-label">
        <strong>{s.bronze_rows.toLocaleString()}</strong> rows streamed →{' '}
        <strong>{s.duplicate_rows.toLocaleString()}</strong> duplicates removed,{' '}
        <strong>{s.rejected_rows.toLocaleString()}</strong> rejected →{' '}
        <strong>{s.silver_rows.toLocaleString()}</strong> clean events from{' '}
        <strong>{s.matches}</strong> {s.matches === 1 ? 'match' : 'matches'}.
      </span>
      <button
        className="dq-info-btn"
        aria-label="Data quality details"
        onClick={() => setTipVisible(v => !v)}
        aria-expanded={tipVisible}
      >
        ⓘ
      </button>
      {tipVisible && (
        <div className="dq-tooltip" role="tooltip">
          <p>Gold run ID: <code>{season.run_id}</code></p>
          <p>Generated: {new Date(season.generated_at).toLocaleString()}</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SeasonSection
// ---------------------------------------------------------------------------

export default function SeasonSection({ entries, onSelect }: SeasonSectionProps) {
  const [season, setSeason] = useState<Season | null>(null)

  useEffect(() => {
    getSeason()
      .then(s => setSeason(s))
      .catch(() => { /* season is optional — silently skip on error */ })
  }, [])

  if (season === null) return null

  const matchesNewestFirst = [...season.matches].sort((a, b) => b.seed - a.seed)

  return (
    <section className="season-section" aria-label="Season">
      <div className="season-header-wrap">
        <h2 className="season-heading">Season so far</h2>
        <p className="season-header-sub">
          Built by the Fabric pipeline from the gold tables · updated {relativeTime(season.generated_at)}
        </p>
      </div>
      <StandingsTable standings={season.standings} />
      <div className="season-results">
        <h3 className="season-subhead">Results</h3>
        <div className="season-results-grid">
          {matchesNewestFirst.map(m => (
            <MatchResultCard key={m.match_id} match={m} entries={entries} onSelect={onSelect} />
          ))}
        </div>
      </div>
      {season.team_totals.length > 0 && (
        <TeamCompTiles teamTotals={season.team_totals} />
      )}
      <DataQualityStrip season={season} />
    </section>
  )
}
