import { useState, useEffect } from 'react'
import type { CatalogEntry, ReplayBundle, SnapshotData } from '../types.ts'
import { loadReplay } from '../api.ts'
import PitchThumb from './PitchThumb.tsx'

interface HeroProps {
  entries: CatalogEntry[]
  onSelect: (id: string) => void
  loading: boolean
}

export default function Hero({ entries, onSelect, loading }: HeroProps) {
  const [heroBundle, setHeroBundle] = useState<ReplayBundle | null>(null)
  const [heroError, setHeroError] = useState(false)
  const [animKey, setAnimKey] = useState(0)

  const scenarioEntry = entries.find(e => e.replay_id === 'scenario_forced_pass_into_traffic')
    ?? entries.find(e => e.kind === 'scenario')
    ?? null
  const matchEntry = entries.find(e => e.kind === 'match') ?? null
  const scenarioId = scenarioEntry?.replay_id

  useEffect(() => {
    if (!scenarioId) return
    setHeroError(false)
    loadReplay(scenarioId)
      .then(b => setHeroBundle(b))
      .catch(() => setHeroError(true))
  }, [scenarioId])

  useEffect(() => {
    if (!heroBundle) return
    const timer = setInterval(() => setAnimKey(k => k + 1), 4500)
    return () => clearInterval(timer)
  }, [heroBundle])

  const ov0 = heroBundle?.overlays[0]
  const visual = ov0?.visual ?? null
  const heroSnapshot: SnapshotData | null = (() => {
    if (!heroBundle || !ov0) return null
    const evId = ov0.evidence.event_ids[0]
    const ev = evId ? heroBundle.events.find(e => e.event_id === evId) : null
    const sid = ev?.snapshot_id
    return sid ? (heroBundle.snapshots.find(s => s.snapshot_id === sid) ?? null) : null
  })()

  return (
    <section className="hero" aria-labelledby="hero-headline">
      <div className="hero-text">
        <h2 id="hero-headline" className="hero-headline">Every pass has a ghost.</h2>
        <p className="hero-sub">
          See the better option that was on, scored in code and explained.
          Every claim is checked against the evidence.
        </p>
        <div className="hero-ctas">
          <button
            className="btn btn-primary"
            onClick={() => scenarioEntry && onSelect(scenarioEntry.replay_id)}
            disabled={loading || !scenarioEntry}
          >
            See the Ghost Pass
          </button>
          {matchEntry && (
            <button
              className="btn"
              onClick={() => onSelect(matchEntry.replay_id)}
              disabled={loading}
            >
              Watch a full match
            </button>
          )}
        </div>
      </div>
      <div className="hero-pitch" aria-hidden="true">
        <PitchThumb
          visual={visual}
          snapshot={heroSnapshot}
          meta={heroBundle?.meta ?? null}
          animKey={animKey}
          animate={!!visual}
        />
        {heroError && (
          <p className="hero-pitch-msg">Preview unavailable — click to load the scenario.</p>
        )}
      </div>
    </section>
  )
}
