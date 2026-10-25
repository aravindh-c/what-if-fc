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
    poll_once(state, kql, client) -> None   (exported for tests)
    row_to_event(row) -> MatchEvent | None  (exported for tests)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 5.0
_MAX_SNAPSHOT_RETRIES = 6
_SEED_RE = re.compile(r"_s(\d+)_")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class LiveMatchState:
    match_id: str
    clock_s: int = 0
    score: dict[str, int] = field(default_factory=dict)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    ledgers: dict[str, Any] = field(default_factory=dict)
    simulate_outage: bool = False
    events: list[Any] = field(default_factory=list)
    skipped_rows: int = 0
    processed_ids: set[str] = field(default_factory=set)
    pending_moments: dict[str, int] = field(default_factory=dict)
    snap_cache: dict[str, Any] = field(default_factory=dict)
    task: asyncio.Task | None = field(default=None, repr=False)


_states: dict[str, LiveMatchState] = {}


# ---------------------------------------------------------------------------
# Row conversion
# ---------------------------------------------------------------------------


def _seed_from_match_id(match_id: str) -> int | None:
    m = _SEED_RE.search(match_id)
    return int(m.group(1)) if m else None


def row_to_event(row: dict) -> Any:
    """Convert a KQL EventsSince row dict to a MatchEvent, or None if invalid."""
    from core.schemas import EventType, MatchEvent, Outcome

    try:
        et_raw = row.get("event_time")
        if isinstance(et_raw, datetime):
            event_time = et_raw if et_raw.tzinfo else et_raw.replace(tzinfo=UTC)
        elif isinstance(et_raw, str) and et_raw:
            event_time = datetime.fromisoformat(et_raw.replace("Z", "+00:00"))
        else:
            event_time = datetime.now(UTC)

        match_id = str(row["match_id"])
        seed_val = row.get("seed")
        seed = int(seed_val) if seed_val is not None else (_seed_from_match_id(match_id) or 0)

        clock_s = int(row["match_clock_s"])
        period_val = row.get("period")
        period: int
        if period_val in (1, 2):
            period = period_val
        else:
            period = 1 if clock_s <= 2700 else 2

        def _f(key: str) -> float | None:
            v = row.get(key)
            return float(v) if v is not None else None

        outcome_raw = row.get("outcome")
        outcome = None
        if outcome_raw:
            try:
                outcome = Outcome(str(outcome_raw))
            except ValueError:
                pass

        return MatchEvent(
            event_id=str(row["event_id"]),
            match_id=match_id,
            scenario_id=str(row.get("scenario_id") or "live"),
            seed=seed,
            event_time=event_time,
            match_clock_s=clock_s,
            period=period,
            event_type=EventType(str(row["event_type"])),
            team_id=row.get("team_id") or None,
            player_id=row.get("player_id") or None,
            possession_id=int(row.get("possession_id") or 0),
            x=_f("x"),
            y=_f("y"),
            end_x=_f("end_x"),
            end_y=_f("end_y"),
            outcome=outcome,
            receiver_id=row.get("receiver_id") or None,
            pressure_level=float(row.get("pressure_level") or 0.0),
            snapshot_id=row.get("snapshot_id") or None,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Roster helper
# ---------------------------------------------------------------------------


def _build_roster(match_id: str) -> list:
    seed = _seed_from_match_id(match_id)
    if seed is None:
        return []
    try:
        from simulator.reference_data import build_players
        return build_players(seed)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------


def _get_snapshot(state: LiveMatchState, kql: Any, snapshot_id: str | None) -> Any:
    if snapshot_id is None:
        return None
    if snapshot_id in state.snap_cache:
        return state.snap_cache[snapshot_id]
    row = kql.match_snapshot(state.match_id, snapshot_id)
    if row is None:
        return None
    from core.schemas import PlayerPosition, PositionSnapshot
    raw_pos = row.get("positions") or []
    positions = [PlayerPosition(**p) if isinstance(p, dict) else p for p in raw_pos]
    snap = PositionSnapshot(
        snapshot_id=row["snapshot_id"],
        match_id=row["match_id"],
        match_clock_s=row["match_clock_s"],
        positions=positions,
    )
    state.snap_cache[snapshot_id] = snap
    return snap


# ---------------------------------------------------------------------------
# poll_once — single watcher iteration (exported for tests)
# ---------------------------------------------------------------------------


async def poll_once(state: LiveMatchState, kql: Any, client: Any) -> None:
    """Execute one poll: fetch new events, detect moments, run overlay workflows."""
    from agents.moments import NoOpAgent, build_ledger, make_goal_twin, overlay_id
    from agents.workflow import run_moment_workflow
    from analytics.evidence import build_evidence_packet
    from analytics.metrics import key_moments, pass_event_for
    from analytics.tactical_twin import score_pass
    from core.schemas import EventType

    # Fetch new rows
    rows = kql.events_since(state.match_id, state.clock_s)

    # Convert rows to MatchEvent objects
    new_events: list[Any] = []
    for row in rows:
        ev = row_to_event(row)
        if ev is None:
            state.skipped_rows += 1
            logger.warning("Skipped malformed event row: %s", row)
        else:
            new_events.append(ev)

    # Accumulate events, advance clock, update score
    state.events.extend(new_events)
    if state.events:
        state.clock_s = max(e.match_clock_s for e in state.events)
    for ev in new_events:
        if ev.event_type == EventType.GOAL and ev.team_id:
            state.score[ev.team_id] = state.score.get(ev.team_id, 0) + 1

    # Detect key moments on full accumulated event list
    moments = key_moments(state.events)

    # Roster for narrative (may be empty if seed not extractable)
    roster = _build_roster(state.match_id)

    for moment in moments:
        if moment.moment_id in state.processed_ids:
            continue

        is_ghost = moment.ghost_eligible
        is_goal = moment.moment_type == "goal"

        if not is_ghost and not is_goal:
            state.processed_ids.add(moment.moment_id)
            continue

        # Ghost: need pass event and snapshot
        if is_ghost:
            pass_ev = pass_event_for(moment, state.events)
            if pass_ev is None:
                state.processed_ids.add(moment.moment_id)
                continue
            snapshot = _get_snapshot(state, kql, pass_ev.snapshot_id)
            if snapshot is None:
                retry_count = state.pending_moments.get(moment.moment_id, 0)
                if retry_count >= _MAX_SNAPSHOT_RETRIES:
                    logger.warning(
                        "Giving up on snapshot for %s after %d retries",
                        moment.moment_id, _MAX_SNAPSHOT_RETRIES,
                    )
                    state.processed_ids.add(moment.moment_id)
                    state.pending_moments.pop(moment.moment_id, None)
                else:
                    state.pending_moments[moment.moment_id] = retry_count + 1
                continue
        else:
            pass_ev = None
            snapshot = None

        # Mark processed; clear pending retry
        state.processed_ids.add(moment.moment_id)
        state.pending_moments.pop(moment.moment_id, None)

        # Build twin and evidence packet
        try:
            if is_ghost:
                twin = score_pass(pass_ev, snapshot)
                if not twin.ghost_shown:
                    continue
                packet = build_evidence_packet(
                    moment, state.events, snapshot, twin, state.match_id
                )
            else:
                goal_ev = next(
                    (e for e in state.events if e.event_id == moment.event_id), None
                )
                if goal_ev is None or goal_ev.player_id is None:
                    continue
                twin = make_goal_twin(goal_ev.player_id)
                packet = build_evidence_packet(
                    moment, state.events, None, twin, state.match_id
                )
        except Exception:
            logger.exception("Failed to build packet for %s", moment.moment_id)
            continue

        # Agent strategy
        if state.simulate_outage:
            _agents_pair: tuple | None = (NoOpAgent(), NoOpAgent())
            fallback_reason: str | None = "simulated outage"
        elif client is None:
            _agents_pair = (NoOpAgent(), NoOpAgent())
            fallback_reason = "agents not configured"
        else:
            _agents_pair = None
            fallback_reason = None

        # Run workflow
        try:
            overlay, log = await run_moment_workflow(
                packet,
                twin,
                roster,
                kql,
                client,
                timeout_s=30.0,
                _agents=_agents_pair,
            )
        except Exception:
            logger.exception("Workflow failed for %s", moment.moment_id)
            continue

        if _agents_pair is not None and log.get("source") == "template":
            log = {**log, "fallback_reason": fallback_reason}

        ov_id = overlay_id(state.match_id, moment.event_id)
        ov_dict = overlay.model_dump(by_alias=True)
        ov_dict["overlay_id"] = ov_id

        try:
            ledger = build_ledger(packet, twin, roster, state.events, log)
        except Exception:
            logger.debug("Could not build ledger for %s", ov_id)
            ledger = {}

        state.overlays.append(ov_dict)
        state.ledgers[ov_id] = ledger

        logger.info(
            "Live overlay %s (%s) at clock=%ds source=%s",
            ov_id, moment.moment_type, moment.match_clock_s, log.get("source"),
        )

        _flush(state)


# ---------------------------------------------------------------------------
# Background watcher loop
# ---------------------------------------------------------------------------


async def _watch(state: LiveMatchState, kql: Any, client: Any) -> None:
    while True:
        try:
            await asyncio.sleep(_POLL_INTERVAL_S)
            await poll_once(state, kql, client)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Watcher error for %s; continuing", state.match_id)


# ---------------------------------------------------------------------------
# Agent client factory
# ---------------------------------------------------------------------------


def _make_agent_client() -> Any:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    model = os.environ.get("FOUNDRY_MODEL", "").strip()
    if not endpoint or not model:
        logger.info("Agents not configured (FOUNDRY_PROJECT_ENDPOINT/FOUNDRY_MODEL not set)")
        return None
    try:
        from agent_framework_foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        return FoundryChatClient(
            project_endpoint=endpoint,
            model=model,
            credential=DefaultAzureCredential(),
        )
    except Exception:
        logger.warning("Failed to create FoundryChatClient; using templates", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Disk flush
# ---------------------------------------------------------------------------


def _flush(state: LiveMatchState) -> None:
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
    client = _make_agent_client()
    task = asyncio.create_task(_watch(state, kql, client), name=f"watcher-{match_id}")
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
    return [ov for ov in state.overlays if ov.get("match_clock_s", 0) > since_clock_s]


def set_simulate_outage(match_id: str, value: bool) -> None:
    state = _states.get(match_id)
    if state:
        state.simulate_outage = value


def list_watched_match_ids() -> list[str]:
    return [mid for mid, s in _states.items() if s.task and not s.task.done()]
