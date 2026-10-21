import { useState, useEffect, useRef, useCallback } from 'react'
import type { CatalogEntry, OverlayData, ReplayBundle } from './types.ts'
import { listReplays, loadReplay } from './api.ts'
import { positionsAt, ballAt, scoreAt, maxClockS } from './lib/playback.ts'
import Pitch from './components/Pitch.tsx'
import Scoreboard from './components/Scoreboard.tsx'
import PlaybackControls from './components/PlaybackControls.tsx'
import Timeline from './components/Timeline.tsx'
import ReplayPicker from './components/ReplayPicker.tsx'
import MomentCard from './components/MomentCard.tsx'

// ---------------------------------------------------------------------------
// usePlayback hook
// ---------------------------------------------------------------------------

interface PlaybackState {
  clockS: number
  playing: boolean
  speed: number
  activeOverlay: OverlayData | null
}

function usePlayback(bundle: ReplayBundle | null) {
  const [state, setState] = useState<PlaybackState>({
    clockS: 0, playing: false, speed: 30, activeOverlay: null,
  })
  const rafRef = useRef<number | null>(null)
  const lastTsRef = useRef<number | null>(null)
  const pausedForOverlayRef = useRef<string | null>(null)

  const duration = bundle ? maxClockS(bundle) : 0

  // Toggle play/pause
  const toggle = useCallback(() => {
    setState(s => {
      if (s.playing) {
        lastTsRef.current = null
      }
      return { ...s, playing: !s.playing, activeOverlay: s.playing ? s.activeOverlay : null }
    })
  }, [])

  const setSpeed = useCallback((speed: number) => setState(s => ({ ...s, speed })), [])

  const seek = useCallback((t: number) => {
    pausedForOverlayRef.current = null
    setState(s => ({
      ...s,
      clockS: Math.max(0, Math.min(duration, t)),
      activeOverlay: null,
    }))
  }, [duration])

  // RAF loop
  useEffect(() => {
    if (!state.playing || !bundle) return
    const safeBundle = bundle

    function tick(ts: number) {
      if (lastTsRef.current === null) lastTsRef.current = ts
      const elapsed = (ts - lastTsRef.current) / 1000
      lastTsRef.current = ts

      setState(prev => {
        const { clockS, speed, activeOverlay } = prev
        if (activeOverlay) return prev  // paused at overlay

        let next = clockS + elapsed * speed
        if (next >= duration) next = duration

        // Check if we've crossed an overlay clock
        const hit = safeBundle.overlays.find(ov => {
          if (pausedForOverlayRef.current === ov.overlay_id) return false
          return ov.match_clock_s > clockS && ov.match_clock_s <= next
        })

        if (hit) {
          pausedForOverlayRef.current = hit.overlay_id
          lastTsRef.current = null
          return { ...prev, clockS: hit.match_clock_s, playing: false, activeOverlay: hit }
        }

        if (next >= duration) {
          lastTsRef.current = null
          return { ...prev, clockS: duration, playing: false }
        }

        return { ...prev, clockS: next }
      })

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current) }
  }, [state.playing, bundle, duration])

  // Space bar toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code === 'Space' && e.target === document.body) {
        e.preventDefault()
        toggle()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [toggle])

  return { ...state, toggle, setSpeed, seek }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [entries, setEntries] = useState<CatalogEntry[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [bundle, setBundle] = useState<ReplayBundle | null>(null)
  const [bundleLoading, setBundleLoading] = useState(false)

  const { clockS, playing, speed, activeOverlay, toggle, setSpeed, seek } = usePlayback(bundle)

  // Load catalog
  useEffect(() => {
    listReplays()
      .then(setEntries)
      .catch(e => setListError(String(e)))
      .finally(() => setListLoading(false))
  }, [])

  const openReplay = useCallback(async (id: string) => {
    setBundleLoading(true)
    try {
      const b = await loadReplay(id)
      setBundle(b)
      // Scenario replays: open directly at the first (only) overlay moment
      if (b.meta.kind === 'scenario' && b.overlays.length > 0) {
        seek(b.overlays[0].match_clock_s)
      }
    } finally {
      setBundleLoading(false)
    }
  }, [seek])

  if (!bundle) {
    return (
      <div className="app-root">
        <header className="app-header">
          <h1>What-If FC</h1>
        </header>
        <main className="app-main">
          {bundleLoading
            ? <p className="picker-status">Loading replay…</p>
            : <ReplayPicker
                entries={entries}
                loading={listLoading}
                error={listError}
                onSelect={openReplay}
              />
          }
        </main>
      </div>
    )
  }

  const homeTeam = Object.keys(bundle.meta.teams)[0] ?? ''
  const positions = positionsAt(clockS, bundle)
  const ball = ballAt(clockS, bundle.events, homeTeam)
  const score = scoreAt(clockS, bundle)
  const duration = maxClockS(bundle)

  return (
    <div className="app-root">
      <header className="app-header">
        <button
          className="btn back-btn"
          onClick={() => setBundle(null)}
          aria-label="Back to replay list"
        >
          ← Back
        </button>
        <h1>{bundle.meta.title}</h1>
      </header>
      <main className="app-main">
        <Scoreboard bundle={bundle} score={score} clockS={clockS} />
        <div className="pitch-wrap">
          <Pitch
            positions={positions}
            ball={ball}
            bundle={bundle}
            activeOverlay={activeOverlay}
            homeTeam={homeTeam}
          />
          {activeOverlay && (
            <MomentCard overlay={activeOverlay} bundle={bundle} />
          )}
        </div>
        <PlaybackControls
          playing={playing}
          speed={speed}
          onToggle={toggle}
          onSpeed={setSpeed}
        />
        <Timeline
          durationS={duration}
          clockS={clockS}
          overlays={bundle.overlays}
          onSeek={seek}
        />
      </main>
    </div>
  )
}
