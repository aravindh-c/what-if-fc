"""Live-match moment watcher for What If FC.

Runs one asyncio background task per watched match that polls Fabric Eventhouse
every 5 seconds via EventsSince, detects ghost-eligible and goal moments, runs
the agent workflow, and accumulates overlays in memory.

Public API (used by api/main.py):
    start_watcher(match_id, kql) -> None
    stop_watcher(match_id) -> None
    get_state(match_id) -> LiveMatchState | None
    get_overlays(match_id, since_clock_s) -> list[dict]
    set_simulate_outage(match_id, value) -> None
    list_watched_match_ids() -> list[str]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL_S = 5.0
_GHOST_COOLDOWN_S = 180  # at most one ghost overlay per 180 s window

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class LiveMatchState:
    match_id: str
    clock_s: int = 0                 # last polled clock
    score: dict[str, int] = field(default_factory=dict)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    ledgers: dict[str, Any] = field(default_factory=dict)
    last_ghost_clock_s: int = -_GHOST_COOLDOWN_S
    simulate_outage: bool = False
    events: list[Any] = field(default_factory=list)   # accumulated MatchEvent objects
    task: asyncio.Task | None = field(default=None, repr=False)


_states: dict[str, LiveMatchState] = {}


# ---------------------------------------------------------------------------
# Overlay ID (matches build_replay._overlay_id)
# ---------------------------------------------------------------------------


def _overlay_id(match_id: str, event_id: str) -> str:
    raw = (match_id + event_id).encode()
    return "ov_" + hashlib.sha256(raw).hexdigest()[:10]


# ---------------------------------------------------------------------------
# NoOp agent stub for outage simulation
# ---------------------------------------------------------------------------


class _NoOpAgent:
    async def run(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated outage")


# ---------------------------------------------------------------------------
# Core watcher loop
# ---------------------------------------------------------------------------


async def _watch(state: LiveMatchState, kql: Any) -> None:
    """Background task: poll EventsSince, detect moments, build overlays."""
    from agents.workflow import run_moment_workflow
    from analytics.evidence import build_evidence_packet
    from analytics.metrics import key_moments, pass_event_for
    from analytics.tactical_twin import score_pass
    from core.schemas import EventType, MatchEvent, Outcome

    # snapshot cache: snapshot_id -> PositionSnapshot
    snap_cache: dict[str, Any] = {}

    def _get_snapshot(snapshot_id: str | None) -> Any:
        if snapshot_id is None:
            return None
        if snapshot_id in snap_cache:
            return snap_cache[snapshot_id]
        row = kql.match_snapshot(state.match_id, snapshot_id)
        if row is None:
            return None
        from core.schemas import PlayerPosition, PositionSnapshot
        positions = [
            PlayerPosition(**p) if isinstance(p, dict) else p
            for p in (row.get("positions") or [])
        ]
        snap = PositionSnapshot(
            snapshot_id=row["snapshot_id"],
            match_id=row["match_id"],
            match_clock_s=row["match_clock_s"],
            positions=positions,
        )
        snap_cache[snapshot_id] = snap
        return snap

    # track which moment_ids have already been processed
    processed_ids: set[str] = set()

    while True:
        try:
            await asyncio.sleep(_POLL_INTERVAL_S)

            new_rows = kql.events_since(state.match_id, state.clock_s)
            if not new_rows:
                continue

            # Convert to MatchEvent objects
            new_events: list[Any] = []
            for r in new_rows:
                try:
                    ev = MatchEvent(
                        event_id=r["event_id"],
                        match_id=r["match_id"],
                        match_clock_s=int(r["match_clock_s"]),
                        event_type=EventType(r["event_type"]),
                        team_id=r.get("team_id"),
                        player_id=r.get("player_id"),
                        outcome=Outcome(r["outcome"]) if r.get("outcome") else None,
                        x=float(r["x"]) if r.get("x") is not None else None,
                        y=float(r["y"]) if r.get("y") is not None else None,
                        to_x=float(r["to_x"]) if r.get("to_x") is not None else None,
                        to_y=float(r["to_y"]) if r.get("to_y") is not None else None,
                    )
                    new_events.append(ev)
                except Exception:
                    logger.debug("Skipping malformed event row: %s", r)

            if not new_events:
                continue

            state.events.extend(new_events)
            state.clock_s = max(e.match_clock_s for e in state.events)

            # Update score from goal events
            for ev in new_events:
                if str(ev.event_type) in {"EventType.GOAL", "goal"} and ev.team_id:
                    state.score[ev.team_id] = state.score.get(ev.team_id, 0) + 1

            # Run key-moment detection on full accumulated event list
            moments = key_moments(state.events)

            for moment in moments:
                if moment.moment_id in processed_ids:
                    continue
                processed_ids.add(moment.moment_id)

                # Ghost-eligible: cooldown check
                is_ghost = moment.ghost_eligible
                is_goal = moment.moment_type == "goal"

                if not is_ghost and not is_goal:
                    continue

                if is_ghost:
                    gap = moment.match_clock_s - state.last_ghost_clock_s
                    if gap < _GHOST_COOLDOWN_S:
                        logger.debug(
                            "Ghost cooldown active for %s (gap=%ds)", state.match_id, gap
                        )
                        continue

                # Build evidence packet + twin
                try:
                    pass_ev = pass_event_for(moment, state.events)
                    if pass_ev is None:
                        continue
                    snapshot = _get_snapshot(pass_ev.snapshot_id)
                    if snapshot is None:
                        continue
                    twin = score_pass(pass_ev, snapshot)
                    if not twin.ghost_shown:
                        continue
                    packet = build_evidence_packet(
                        moment, state.events, snapshot, twin, state.match_id
                    )
                except Exception:
                    logger.exception("Failed to build packet for %s", moment.moment_id)
                    continue

                # Determine roster for narrative (empty list if unavailable)
                roster: list[Any] = []

                # Run workflow
                use_agents = not state.simulate_outage
                try:
                    overlay, log = await run_moment_workflow(
                        packet,
                        twin,
                        roster,
                        kql,
                        None,  # no Azure client in live watcher
                        timeout_s=30.0,
                        _agents=None if use_agents else (_NoOpAgent(), _NoOpAgent()),
                    )
                except Exception:
                    logger.exception("Workflow failed for %s", moment.moment_id)
                    continue

                if not use_agents and log.get("source") == "template":
                    log = {**log, "fallback_reason": "simulated outage"}

                ov_id = _overlay_id(state.match_id, moment.event_id)
                ov_dict = overlay.model_dump(by_alias=True)
                ov_dict["overlay_id"] = ov_id

                # Build ledger
                try:
                    from scripts.build_replay import _build_ledger  # noqa: PLC2701
                    ledger = _build_ledger(packet, twin, roster, state.events, log)
                except Exception:
                    logger.debug("Could not build ledger for %s", ov_id)
                    ledger = {}

                state.overlays.append(ov_dict)
                state.ledgers[ov_id] = ledger

                if is_ghost:
                    state.last_ghost_clock_s = moment.match_clock_s

                logger.info(
                    "Live overlay %s (%s) at clock=%ds source=%s",
                    ov_id, moment.moment_type, moment.match_clock_s, log.get("source"),
                )

                # Flush to disk
                _flush(state)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Watcher error for %s; continuing", state.match_id)


# ---------------------------------------------------------------------------
# Disk flush
# ---------------------------------------------------------------------------


def _flush(state: LiveMatchState) -> None:
    """Write current overlays + ledgers to data/replay/live_<match_id>.json."""
    try:
        out_dir = Path(os.environ.get("REPLAY_DIR", "data/replay"))
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"live_{state.match_id}.json"
        bundle = {
            "meta": {
                "replay_id": f"live_{state.match_id}",
                "kind": "live",
                "match_id": state.match_id,
                "built_at": datetime.now(UTC).isoformat(),
            },
            "overlays": state.overlays,
            "ledgers": state.ledgers,
            "score": state.score,
            "clock_s": state.clock_s,
        }
        path.write_text(json.dumps(bundle, default=str), encoding="utf-8")
    except Exception:
        logger.exception("Failed to flush live bundle for %s", state.match_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_watcher(match_id: str, kql: Any) -> None:
    """Start the background watcher task for *match_id* if not already running."""
    if match_id in _states and _states[match_id].task and not _states[match_id].task.done():
        return
    state = _states.get(match_id) or LiveMatchState(match_id=match_id)
    task = asyncio.create_task(_watch(state, kql), name=f"watcher-{match_id}")
    state.task = task
    _states[match_id] = state
    logger.info("Started watcher for %s", match_id)


def stop_watcher(match_id: str) -> None:
    """Cancel the background watcher task for *match_id*."""
    state = _states.get(match_id)
    if state and state.task and not state.task.done():
        state.task.cancel()
        logger.info("Stopped watcher for %s", match_id)


def get_state(match_id: str) -> LiveMatchState | None:
    return _states.get(match_id)


def get_overlays(match_id: str, since_clock_s: int = 0) -> list[dict[str, Any]]:
    state = _states.get(match_id)
    if state is None:
        return []
    return [
        ov for ov in state.overlays
        if ov.get("match_clock_s", 0) > since_clock_s
    ]


def set_simulate_outage(match_id: str, value: bool) -> None:
    state = _states.get(match_id)
    if state:
        state.simulate_outage = value


def list_watched_match_ids() -> list[str]:
    return [
        mid for mid, s in _states.items()
        if s.task and not s.task.done()
    ]
