import { useCallback, useEffect, useRef, useState } from 'react'
import type { DisplayMode } from '../App.tsx'
import { getLiveOverlays, getLiveState, setSimulateOutage } from '../api.ts'
import type { LedgerData, LiveState, OverlayData } from '../types.ts'
import EvidenceDrawer from './EvidenceDrawer.tsx'
import MomentCard from './MomentCard.tsx'
import Pitch from './Pitch.tsx'
import PitchLegend from './PitchLegend.tsx'

const POLL_MS = 2000

interface LiveViewProps {
  matchId: string
  displayMode: DisplayMode
  onBack: () => void
}

function formatClock(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

export default function LiveView({ matchId, displayMode, onBack }: LiveViewProps) {
  const [state, setState] = useState<LiveState | null>(null)
  const [_overlays, setOverlays] = useState<OverlayData[]>([])
  const [activeOverlay, setActiveOverlay] = useState<OverlayData | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sinceRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = useCallback(async () => {
    try {
      const [nextState, newOvs] = await Promise.all([
        getLiveState(matchId),
        getLiveOverlays(matchId, sinceRef.current),
      ])
      setState(nextState)
      if (newOvs.length > 0) {
        sinceRef.current = Math.max(...newOvs.map(o => o.match_clock_s))
        setOverlays(prev => {
          const existing = new Set(prev.map(o => o.overlay_id))
          const fresh = newOvs.filter(o => !existing.has(o.overlay_id))
          const merged = [...prev, ...fresh]
          if (fresh.length > 0) setActiveOverlay(fresh[fresh.length - 1])
          return merged
        })
      }
    } catch (e) {
      setError(String(e))
    }
  }, [matchId])

  useEffect(() => {
    poll()
    timerRef.current = setInterval(poll, POLL_MS)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [poll])

  const toggleOutage = useCallback(async () => {
    if (!state) return
    try {
      await setSimulateOutage(matchId, !state.simulate_outage)
    } catch { /* ignore */ }
  }, [matchId, state])

  const activeLedger: LedgerData | undefined = undefined  // live bundles don't carry ledgers in this view
  const showDrawer = drawerOpen && !!activeOverlay

  const sidePanel = showDrawer ? (
    <EvidenceDrawer
      ledger={activeLedger!}
      overlay={activeOverlay!}
      onClose={() => setDrawerOpen(false)}
      onSeek={() => setDrawerOpen(false)}
    />
  ) : (
    <div className="moment-panel">
      {activeOverlay
        ? (
          <MomentCard
            overlay={activeOverlay}
            bundle={null as never}
            mode={displayMode}
            ledger={activeLedger}
            onDrawerToggle={() => setDrawerOpen(true)}
          />
        )
        : (
          <div className="live-waiting">
            <span className="live-pulse-dot" aria-hidden="true" />
            <p className="live-waiting-text">Waiting for the next moment…</p>
          </div>
        )
      }
    </div>
  )

  return (
    <div className="app-root">
      <header className="app-header">
        <button className="btn back-btn" onClick={onBack} aria-label="Back to replay list">← Back</button>
        <div className="app-header-title">
          <span className="app-header-name">Live: {matchId}</span>
          {state && (
            <span className="app-header-sub live-clock-badge">
              <span className="live-pulse-dot" aria-hidden="true" />
              {formatClock(state.clock_s)}
            </span>
          )}
        </div>
        {displayMode === 'analyst' && (
          <button
            className={`btn mode-btn${state?.simulate_outage ? ' active' : ''}`}
            onClick={toggleOutage}
            title="Simulate model outage — next overlay uses template fallback"
          >
            Sim outage
          </button>
        )}
      </header>
      <main className="app-main">
        {error && <p className="picker-status picker-error">{error}</p>}
        {state && (
          <div className="live-scoreline">
            {Object.entries(state.score).map(([tid, g]) => (
              <span key={tid} className="live-score-chip">{tid}: {g}</span>
            ))}
          </div>
        )}
        <div className="replay-body">
          <div className="pitch-col">
            <div className="pitch-wrap">
              <Pitch
                positions={[]}
                ball={null}
                bundle={null as never}
                activeOverlay={activeOverlay}
                homeTeam=""
                animKey={0}
              />
            </div>
            {activeOverlay && <PitchLegend />}
          </div>
          {sidePanel}
        </div>
      </main>
    </div>
  )
}
