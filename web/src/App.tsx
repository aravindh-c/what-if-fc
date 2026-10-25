import { useState, useEffect, useRef, useCallback } from 'react'
import type { CatalogEntry, OverlayData, ReplayBundle } from './types.ts'

export type DisplayMode = 'fan' | 'analyst' | 'compare'

function getStoredMode(): DisplayMode {
  try {
    const v = localStorage.getItem('whatiffc_mode')
    if (v === 'fan' || v === 'analyst' || v === 'compare') return v
  } catch { /* ignore */ }
  return 'fan'
}
import { listReplays, loadReplay } from './api.ts'
import { positionsAt, ballAt, scoreAt, maxClockS, tickStep } from './lib/playback.ts'
import Pitch from './components/Pitch.tsx'
import Scoreboard from './components/Scoreboard.tsx'
import PlaybackControls from './components/PlaybackControls.tsx'
import Timeline from './components/Timeline.tsx'
import ReplayPicker from './components/ReplayPicker.tsx'
import MomentCard from './components/MomentCard.tsx'
import PitchLegend from './components/PitchLegend.tsx'
import EvidenceDrawer from './components/EvidenceDrawer.tsx'

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
  // Refs always in sync with state — safe to read from RAF closure without stale values
  const clockRef = useRef(0)
  const speedRef = useRef(30)

  const duration = bundle ? maxClockS(bundle) : 0

  const toggle = useCallback(() => {
    setState(s => {
      if (s.playing) lastTsRef.current = null
      return { ...s, playing: !s.playing }
    })
  }, [])

  const play = useCallback(() => {
    lastTsRef.current = null
    setState(s => ({ ...s, playing: true }))
  }, [])

  const setSpeed = useCallback((speed: number) => {
    speedRef.current = speed
    setState(s => ({ ...s, speed }))
  }, [])

  const seek = useCallback((t: number) => {
    const clamped = Math.max(0, Math.min(duration, t))
    pausedForOverlayRef.current = null
    clockRef.current = clamped
    lastTsRef.current = null
    setState(s => ({ ...s, clockS: clamped, activeOverlay: null }))
  }, [duration])

  const showMoment = useCallback((overlay: OverlayData) => {
    pausedForOverlayRef.current = overlay.overlay_id
    clockRef.current = overlay.match_clock_s
    lastTsRef.current = null
    setState(s => ({ ...s, clockS: overlay.match_clock_s, activeOverlay: overlay, playing: false }))
  }, [])

  // RAF loop — all hit detection outside setState so updaters stay pure (StrictMode safe)
  useEffect(() => {
    if (!state.playing || !bundle) return
    const safeBundle = bundle

    function tick(ts: number) {
      if (lastTsRef.current === null) lastTsRef.current = ts
      const elapsed = (ts - lastTsRef.current) / 1000
      lastTsRef.current = ts

      const { nextClock, hitId, done } = tickStep(
        clockRef.current,
        elapsed,
        speedRef.current,
        duration,
        safeBundle.overlays,
        pausedForOverlayRef.current,
      )
      clockRef.current = nextClock

      if (hitId) {
        const hitOverlay = safeBundle.overlays.find(ov => ov.overlay_id === hitId)!
        pausedForOverlayRef.current = hitId
        lastTsRef.current = null
        setState(prev => ({ ...prev, clockS: nextClock, playing: false, activeOverlay: hitOverlay }))
        return
      }

      if (done) {
        lastTsRef.current = null
        setState(prev => ({ ...prev, clockS: nextClock, playing: false }))
        return
      }

      setState(prev => ({ ...prev, clockS: nextClock }))
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current) }
  }, [state.playing, bundle, duration])

  // Space bar — toggle anywhere except text inputs
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      const el = e.target as HTMLElement | null
      if (!el) return
      const tag = el.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable) return
      e.preventDefault()
      toggle()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [toggle])

  return { ...state, toggle, play, setSpeed, seek, showMoment }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function kindLabel(kind: string) {
  if (kind === 'match') return 'Full match'
  if (kind === 'scenario') return 'Scenario'
  return kind.charAt(0).toUpperCase() + kind.slice(1)
}

function replayTitle(bundle: ReplayBundle) {
  const ids = Object.keys(bundle.meta.teams)
  const home = bundle.meta.teams[ids[0]]?.name
  const away = bundle.meta.teams[ids[1]]?.name
  if (home && away) return `${home} vs ${away}`
  return bundle.meta.title
}

function seedSubtitle(replayId: string): string | null {
  const m = replayId.match(/_s(\d+)_/)
  return m ? `Seed ${m[1]} replay` : null
}

export default function App() {
  const [entries, setEntries] = useState<CatalogEntry[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [bundle, setBundle] = useState<ReplayBundle | null>(null)
  const [bundleLoading, setBundleLoading] = useState(false)
  const [bundleError, setBundleError] = useState<string | null>(null)
  const [animKey, setAnimKey] = useState(0)
  const [displayMode, setDisplayMode] = useState<DisplayMode>(getStoredMode)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const changeMode = useCallback((m: DisplayMode) => {
    try { localStorage.setItem('whatiffc_mode', m) } catch { /* ignore */ }
    setDisplayMode(m)
  }, [])

  const { clockS, playing, speed, activeOverlay, toggle, play, setSpeed, seek, showMoment } = usePlayback(bundle)

  useEffect(() => {
    listReplays()
      .then(data => setEntries(data))
      .catch(e => setListError(String(e)))
      .finally(() => setListLoading(false))
  }, [])

  const openReplay = useCallback(async (id: string) => {
    setBundleLoading(true)
    setBundleError(null)
    try {
      const b = await loadReplay(id)
      if (!b.frames) {
        setBundleError('This replay was built with an older version. Rebuild it with scripts/build_replay.py.')
        return
      }
      setBundle(b)
      if (b.meta.kind === 'scenario' && b.overlays.length > 0) {
        showMoment(b.overlays[0])
      }
    } catch (e) {
      setBundleError(`Failed to load replay: ${String(e)}`)
    } finally {
      setBundleLoading(false)
    }
  }, [showMoment])

  const closeBundle = useCallback(() => {
    setBundle(null)
    setBundleError(null)
  }, [])

  // Derived navigation state — computed before early returns so hooks below are unconditional
  const currentIdx = activeOverlay && bundle
    ? bundle.overlays.findIndex(o => o.overlay_id === activeOverlay.overlay_id)
    : -1

  // All useCallback hooks must be declared before any early return (Rules of Hooks)
  const goToPrev = useCallback(() => {
    if (!bundle || currentIdx <= 0) return
    showMoment(bundle.overlays[currentIdx - 1])
  }, [bundle, currentIdx, showMoment])

  const goToNext = useCallback(() => {
    if (!bundle || currentIdx < 0 || currentIdx >= bundle.overlays.length - 1) return
    showMoment(bundle.overlays[currentIdx + 1])
  }, [bundle, currentIdx, showMoment])

  const restartReplay = useCallback(() => {
    if (!bundle || bundle.overlays.length === 0) return
    showMoment(bundle.overlays[0])
  }, [bundle, showMoment])

  // Picker view
  if (!bundle && !bundleError) {
    return (
      <div className="app-root">
        <header className="app-header">
          <h1 className="app-title">What If FC</h1>
        </header>
        <main className="app-main">
          {bundleLoading
            ? <p className="picker-status">Loading replay…</p>
            : <ReplayPicker
                entries={entries}
                loading={listLoading}
                error={listError}
                onSelect={openReplay}
                kindLabel={kindLabel}
              />
          }
        </main>
      </div>
    )
  }

  // Error view
  if (bundleError) {
    return (
      <div className="app-root">
        <header className="app-header">
          <button className="btn back-btn" onClick={closeBundle} aria-label="Back to replay list">← Back</button>
          <h1 className="app-title">What If FC</h1>
        </header>
        <main className="app-main">
          <div className="bundle-error">
            <p className="bundle-error-msg">{bundleError}</p>
            <button className="btn btn-primary" onClick={closeBundle}>Back to replays</button>
          </div>
        </main>
      </div>
    )
  }

  const b = bundle!
  const isScenario = b.meta.kind === 'scenario'
  const homeTeam = Object.keys(b.meta.teams)[0] ?? ''
  const positions = positionsAt(clockS, b)
  const ball = ballAt(clockS, b.events, homeTeam)
  const score = scoreAt(clockS, b)
  const dur = maxClockS(b)

  const headerTitle = isScenario ? b.meta.title : replayTitle(b)
  const headerSub   = isScenario ? (b.meta.scenario_description ?? null) : seedSubtitle(b.meta.replay_id)

  const activeLedger = activeOverlay && b.ledgers ? b.ledgers[activeOverlay.overlay_id] : undefined
  const showDrawer = drawerOpen && !!activeOverlay && !!activeLedger

  // In Compare mode the side panel shows scores; a separate full-width row shows texts
  const isCompare = displayMode === 'compare'

  const sidePanel = showDrawer ? (
    <EvidenceDrawer
      ledger={activeLedger!}
      overlay={activeOverlay!}
      onClose={() => setDrawerOpen(false)}
      onSeek={t => { seek(t); setDrawerOpen(false) }}
    />
  ) : (
    <div className="moment-panel">
      {b.overlays.length > 1 && (
        <div className="moment-nav" aria-label="Moment navigation">
          <button
            className="btn moment-nav-btn"
            onClick={restartReplay}
            aria-label="Restart from first moment"
            title="Restart"
          >⟨⟨</button>
          <button
            className="btn moment-nav-btn"
            onClick={goToPrev}
            disabled={currentIdx <= 0}
            aria-label="Previous moment"
          >‹ Prev</button>
          <span className="moment-nav-count" aria-live="polite">
            {currentIdx >= 0 ? `${currentIdx + 1} / ${b.overlays.length}` : `— / ${b.overlays.length}`}
          </span>
          <button
            className="btn moment-nav-btn"
            onClick={goToNext}
            disabled={currentIdx < 0 || currentIdx >= b.overlays.length - 1}
            aria-label="Next moment"
          >Next ›</button>
        </div>
      )}
      {activeOverlay
        ? <MomentCard
            overlay={activeOverlay}
            bundle={b}
            mode={displayMode}
            ledger={activeLedger}
            onDrawerToggle={() => setDrawerOpen(true)}
          />
        : <p className="moment-panel-empty">Play the match to see key moments</p>
      }
      {isScenario && (
        <button
          className="btn btn-ghost-replay"
          onClick={() => setAnimKey(k => k + 1)}
          aria-label="Replay the Ghost Pass animation"
        >
          Replay the Ghost Pass
        </button>
      )}
    </div>
  )

  return (
    <div className="app-root">
      <header className="app-header">
        <button className="btn back-btn" onClick={closeBundle} aria-label="Back to replay list">← Back</button>
        <div className="app-header-title">
          <span className="app-header-name">{headerTitle}</span>
          {headerSub && <span className="app-header-sub">{headerSub}</span>}
        </div>
        <div className="mode-switch" role="group" aria-label="Display mode">
          {(['fan', 'analyst', 'compare'] as DisplayMode[]).map(m => (
            <button
              key={m}
              className={`mode-btn${displayMode === m ? ' active' : ''}`}
              onClick={() => changeMode(m)}
              aria-pressed={displayMode === m}
            >
              {m === 'fan' ? 'Fan' : m === 'analyst' ? 'Analyst' : 'Compare'}
            </button>
          ))}
        </div>
      </header>
      <main className="app-main">
        {!isScenario && <Scoreboard bundle={b} score={score} clockS={clockS} />}
        <div className="replay-body">
          <div className="pitch-col">
            <div className="pitch-wrap">
              <Pitch
                positions={positions}
                ball={ball}
                bundle={b}
                activeOverlay={activeOverlay}
                homeTeam={homeTeam}
                animKey={animKey}
              />
            </div>
            {activeOverlay && <PitchLegend />}
          </div>
          {sidePanel}
        </div>
        {isCompare && activeOverlay && (
          <div className="compare-row">
            <div className="compare-col">
              <p className="compare-col-label">Fan</p>
              <MomentCard
                overlay={activeOverlay}
                bundle={b}
                mode="fan"
                ledger={activeLedger}
                onDrawerToggle={() => setDrawerOpen(true)}
                textOnly
              />
            </div>
            <div className="compare-divider" aria-hidden="true" />
            <div className="compare-col">
              <p className="compare-col-label">Analyst</p>
              <MomentCard
                overlay={activeOverlay}
                bundle={b}
                mode="analyst"
                ledger={activeLedger}
                onDrawerToggle={() => setDrawerOpen(true)}
                textOnly
              />
            </div>
          </div>
        )}
        {!isScenario && (
          <PlaybackControls
            playing={playing}
            speed={speed}
            onToggle={toggle}
            onSpeed={setSpeed}
          />
        )}
        {!isScenario && (
          <Timeline
            durationS={dur}
            clockS={clockS}
            overlays={b.overlays}
            onSeek={seek}
            onPlay={play}
          />
        )}
      </main>
    </div>
  )
}
