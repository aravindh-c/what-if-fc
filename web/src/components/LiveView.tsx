import { useCallback, useEffect, useRef, useState } from 'react'
import type { DisplayMode } from '../App.tsx'
import { getLiveMeta, getLiveOverlays, getLiveState, setSimulateOutage } from '../api.ts'
import type { EventData, LedgerData, LiveOverlay, ReplayBundle } from '../types.ts'
import { positionsAt } from '../lib/playback.ts'
import EvidenceDrawer from './EvidenceDrawer.tsx'
import MomentCard from './MomentCard.tsx'
import Pitch from './Pitch.tsx'
import PitchLegend from './PitchLegend.tsx'
import Scoreboard from './Scoreboard.tsx'

const POLL_MS = 2000

interface LiveViewProps {
  matchId: string
  displayMode: DisplayMode
  onChangeMode: (m: DisplayMode) => void
  onBack: () => void
}

function fmtClock(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}

export default function LiveView({ matchId, displayMode, onChangeMode, onBack }: LiveViewProps) {
  const [liveBundle, setLiveBundle] = useState<ReplayBundle | null>(null)
  const [liveClock, setLiveClock] = useState(0)
  const [score, setScore] = useState<Record<string, number>>({})
  const [simulateOutage, setSimulateOutageLocal] = useState(false)
  const [activeOverlay, setActiveOverlay] = useState<LiveOverlay | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [animKey, setAnimKey] = useState(0)
  const [connecting, setConnecting] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isReplaying, setIsReplaying] = useState(false)
  const [replayClockS, setReplayClockS] = useState(0)

  const sinceClockRef = useRef(0)
  const metaLoadedRef = useRef(false)
  const hasSnapshotRef = useRef(false)
  const replayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const poll = useCallback(async () => {
    try {
      const [nextState, newOvs] = await Promise.all([
        getLiveState(matchId),
        getLiveOverlays(matchId, sinceClockRef.current),
      ])

      setLiveClock(nextState.clock_s)
      setScore(nextState.score)
      setSimulateOutageLocal(nextState.simulate_outage)

      setLiveBundle(prev => {
        if (!prev) return prev

        let snapshots = prev.snapshots
        let frameSnaps = prev.frames.snapshots
        if (nextState.latest_snapshot) {
          const snap = nextState.latest_snapshot
          if (!snapshots.find(s => s.snapshot_id === snap.snapshot_id)) {
            snapshots = [...snapshots, snap]
            frameSnaps = {
              ...frameSnaps,
              [snap.snapshot_id]: nextState.possession_team_id ?? Object.keys(prev.meta.teams)[0] ?? '',
            }
            hasSnapshotRef.current = true
          }
        }

        const existingIds = new Set(prev.events.map(e => e.event_id))
        const newEvts = (nextState.events as unknown as EventData[]).filter(e => !existingIds.has(e.event_id))

        return {
          ...prev,
          snapshots,
          events: newEvts.length ? [...prev.events, ...newEvts] : prev.events,
          frames: { ...prev.frames, snapshots: frameSnaps },
        }
      })

      if (newOvs.length > 0) {
        sinceClockRef.current = Math.max(sinceClockRef.current, ...newOvs.map(o => o.match_clock_s))

        setLiveBundle(prev => {
          if (!prev) return prev
          const existingIds = new Set(prev.overlays.map(o => o.overlay_id))
          const fresh = newOvs.filter(o => !existingIds.has(o.overlay_id))
          if (!fresh.length) return prev

          const frameOvs = { ...prev.frames.overlays }
          const ledgers = { ...(prev.ledgers ?? {}) }
          for (const ov of fresh) {
            if (ov.frame_team_id) frameOvs[ov.overlay_id] = ov.frame_team_id
            if (ov.ledger) ledgers[ov.overlay_id] = ov.ledger
          }

          return {
            ...prev,
            overlays: [...prev.overlays, ...fresh],
            frames: { ...prev.frames, overlays: frameOvs },
            ledgers,
          }
        })

        setActiveOverlay(newOvs[newOvs.length - 1])
        setAnimKey(k => k + 1)

        // Instant replay: freeze pitch on this moment's snapshot for 12 s
        const replayClock = newOvs[newOvs.length - 1].match_clock_s
        setReplayClockS(replayClock)
        setIsReplaying(true)
        if (replayTimerRef.current) clearTimeout(replayTimerRef.current)
        replayTimerRef.current = setTimeout(() => setIsReplaying(false), 12000)
      }

      if (metaLoadedRef.current && hasSnapshotRef.current) {
        setConnecting(false)
      }
    } catch (e) {
      setError(String(e))
    }
  }, [matchId])

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null
    let active = true

    getLiveMeta(matchId)
      .then(meta => {
        if (!active) return
        metaLoadedRef.current = true
        setLiveBundle({
          meta,
          events: [],
          snapshots: [],
          metrics: { match_stats: [], momentum: [], pressure: [] },
          headline_moments: [],
          overlays: [],
          frames: { snapshots: {}, overlays: {} },
          ledgers: {},
        })
        void poll()
        interval = setInterval(() => { void poll() }, POLL_MS)
      })
      .catch(e => { if (active) setError(String(e)) })

    return () => {
      active = false
      if (interval) clearInterval(interval)
      if (replayTimerRef.current) clearTimeout(replayTimerRef.current)
    }
  }, [matchId, poll])

  const toggleOutage = useCallback(async () => {
    try {
      await setSimulateOutage(matchId, !simulateOutage)
    } catch { /* ignore */ }
  }, [matchId, simulateOutage])

  const homeTeam = liveBundle ? (Object.keys(liveBundle.meta.teams)[0] ?? '') : ''
  const livePositions = liveBundle ? positionsAt(liveClock, liveBundle) : []
  // During replay, show the frozen snapshot positions so lines/rings align correctly
  const pitchPositions = (isReplaying && liveBundle)
    ? positionsAt(replayClockS, liveBundle)
    : livePositions
  // Lines and rings only make sense against the replay snapshot — suppress on live positions
  const pitchOverlay = isReplaying ? activeOverlay : null
  const activeLedger: LedgerData | undefined = activeOverlay && liveBundle?.ledgers
    ? liveBundle.ledgers[activeOverlay.overlay_id]
    : undefined
  const showDrawer = drawerOpen && !!activeOverlay && !!activeLedger

  if (connecting || !liveBundle) {
    return (
      <div className="app-root">
        <header className="app-header">
          <button className="btn back-btn" onClick={onBack} aria-label="Back to replay list">← Back</button>
        </header>
        <main className="app-main">
          {error
            ? <p className="picker-status picker-error">{error}</p>
            : <p className="picker-status">Connecting to Fabric…</p>
          }
        </main>
      </div>
    )
  }

  const b = liveBundle

  const sidePanel = showDrawer ? (
    <EvidenceDrawer
      ledger={activeLedger!}
      overlay={activeOverlay!}
      onClose={() => setDrawerOpen(false)}
      onSeek={() => setDrawerOpen(false)}
    />
  ) : (
    <div className="moment-panel">
      {activeOverlay ? (
        <MomentCard
          overlay={activeOverlay}
          bundle={b}
          mode={displayMode}
          ledger={activeLedger}
          onDrawerToggle={() => setDrawerOpen(true)}
        />
      ) : (
        <div className="live-waiting">
          <span className="live-pulse-dot" aria-hidden="true" />
          <p className="live-waiting-text">Waiting for the next moment…</p>
        </div>
      )}
    </div>
  )

  return (
    <div className="app-root">
      <header className="app-header">
        <button className="btn back-btn" onClick={onBack} aria-label="Back to replay list">← Back</button>
        <div className="app-header-title">
          <span className="app-header-name">{b.meta.title}</span>
          <span className="app-header-sub live-clock-badge">
            {isReplaying ? (
              `Replay · ${fmtClock(replayClockS)}`
            ) : (
              <>
                <span className="live-pulse-dot" aria-hidden="true" />
                {`Live from Fabric · ${fmtClock(liveClock)}`}
              </>
            )}
          </span>
        </div>
        <div className="mode-switch" role="group" aria-label="Display mode">
          {(['fan', 'analyst', 'compare'] as DisplayMode[]).map(m => (
            <button
              key={m}
              className={`mode-btn${displayMode === m ? ' active' : ''}`}
              onClick={() => onChangeMode(m)}
              aria-pressed={displayMode === m}
            >
              {m === 'fan' ? 'Fan' : m === 'analyst' ? 'Analyst' : 'Compare'}
            </button>
          ))}
        </div>
        {displayMode === 'analyst' && (
          <button
            className={`btn mode-btn${simulateOutage ? ' active' : ''}`}
            onClick={() => { void toggleOutage() }}
            title="Simulate model outage — next overlay uses template fallback"
          >
            Sim outage
          </button>
        )}
        {error && <span className="live-error-badge" title={error}>⚠ poll error</span>}
      </header>
      <main className="app-main">
        <Scoreboard bundle={b} score={score} clockS={isReplaying ? replayClockS : liveClock} />
        <div className="replay-body">
          <div className="pitch-col">
            <div className="pitch-wrap">
              <Pitch
                positions={pitchPositions}
                ball={null}
                bundle={b}
                activeOverlay={pitchOverlay}
                homeTeam={homeTeam}
                animKey={animKey}
              />
            </div>
            {activeOverlay?.moment_type === 'ghost_pass' && <PitchLegend />}
          </div>
          {sidePanel}
        </div>
        {displayMode === 'compare' && activeOverlay && (
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
      </main>
    </div>
  )
}
