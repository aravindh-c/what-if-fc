import { useState, useEffect } from 'react'
import type { CatalogEntry, ReplayBundle } from '../types.ts'
import { loadReplay } from '../api.ts'
import PitchThumb from './PitchThumb.tsx'

interface HeroProps {
  entries: CatalogEntry[]
  onSelect: (id: string) => void
  loading: boolean
}

export default function Hero({ entries, onSelect, loading }: HeroProps) {
  const [heroBundle, setHeroBundle] = useState<ReplayBundle | null>(null)
  const [animKey, setAnimKey] = useState(0)

  useEffect(() => {
    loadReplay('forced_pass_into_traffic').then(b => setHeroBundle(b)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!heroBundle) return
    const timer = setInterval(() => setAnimKey(k => k + 1), 4500)
    return () => clearInterval(timer)
  }, [heroBundle])

  const visual = heroBundle?.overlays[0]?.visual ?? null
  const matchEntry = entries.find(e => e.kind === 'match')

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
            onClick={() => onSelect('forced_pass_into_traffic')}
            disabled={loading}
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
        <PitchThumb visual={visual} animKey={animKey} animate />
      </div>
    </section>
  )
}
