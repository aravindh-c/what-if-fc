"""Tests for the live moment watcher.

No network required — a FakeKql drives the watcher with data built from the
offline simulator (seed 7).

AT-LW-01: poll_once repeated over 5-minute event chunks (snapshots arriving one
           poll late) produces EXACTLY the same ghost and goal overlay ids as
           the offline builder for seed 7.
AT-LW-02: simulate_outage flag causes source=template with reason "simulated
           outage" on every overlay produced while the flag is set.
"""

from __future__ import annotations

import asyncio
import hashlib
import time as _time
from typing import Any

# ---------------------------------------------------------------------------
# Helpers: build seed-7 data offline
# ---------------------------------------------------------------------------


def _seed7_data() -> dict[str, Any]:
    from simulator.run import run_match

    match_id, events, snapshots = run_match(7, "T01", "T02")
    return {"match_id": match_id, "events": events, "snapshots": snapshots}


def _offline_overlay_ids(match_id: str, events: list, snapshots: list) -> list[str]:
    """All overlay IDs (ghost AND goal) that the offline builder would produce."""
    from analytics.evidence import build_evidence_packet
    from analytics.metrics import key_moments, pass_event_for
    from analytics.tactical_twin import score_pass

    snap_map = {s.snapshot_id: s for s in snapshots}
    moments = key_moments(events)

    def _ov_id(event_id: str) -> str:
        return "ov_" + hashlib.sha256((match_id + event_id).encode()).hexdigest()[:10]

    ids: list[str] = []

    for km in moments:
        if km.ghost_eligible:
            pass_ev = pass_event_for(km, events)
            if pass_ev is None:
                continue
            snap = snap_map.get(pass_ev.snapshot_id or "")
            if snap is None:
                continue
            twin = score_pass(pass_ev, snap)
            if twin.ghost_shown:
                build_evidence_packet(km, events, snap, twin, match_id)
                ids.append(_ov_id(km.event_id))
        elif km.moment_type == "goal":
            ev = next((e for e in events if e.event_id == km.event_id), None)
            if ev is not None and ev.player_id is not None:
                ids.append(_ov_id(km.event_id))

    return ids


# ---------------------------------------------------------------------------
# FakeKql: returns rows exactly as Kusto EventsSince would
# ---------------------------------------------------------------------------


def _event_to_row(ev: Any) -> dict:
    """Convert a MatchEvent to a dict that mirrors a Kusto EventsSince row."""
    return {
        "event_id": ev.event_id,
        "match_id": ev.match_id,
        "scenario_id": ev.scenario_id,
        "seed": ev.seed,
        "event_time": ev.event_time,
        "match_clock_s": ev.match_clock_s,
        "period": ev.period,
        "event_type": ev.event_type.value,
        "team_id": ev.team_id,
        "player_id": ev.player_id,
        "possession_id": ev.possession_id,
        "x": ev.x,
        "y": ev.y,
        "end_x": ev.end_x,
        "end_y": ev.end_y,
        "outcome": ev.outcome.value if ev.outcome else None,
        "receiver_id": ev.receiver_id,
        "pressure_level": ev.pressure_level,
        "snapshot_id": ev.snapshot_id,
    }


class FakeKql:
    """Serves events in 5-minute chunks; snapshots arrive one poll late."""

    def __init__(self, events: list, snapshots: list) -> None:
        self._events = events
        self._snapshots = snapshots
        self._snapshot_first_seen: set[str] = set()

    def events_since(self, match_id: str, clock_s: int) -> list[dict]:
        window_end = clock_s + 300  # 5-minute chunk
        evs = [
            e for e in self._events
            if e.match_id == match_id
            and e.match_clock_s > clock_s
            and e.match_clock_s <= window_end
        ]
        return [_event_to_row(e) for e in evs]

    def match_snapshot(self, match_id: str, snapshot_id: str) -> dict | None:
        if snapshot_id not in self._snapshot_first_seen:
            self._snapshot_first_seen.add(snapshot_id)
            return None  # not available on first request
        for s in self._snapshots:
            if s.match_id == match_id and s.snapshot_id == snapshot_id:
                return {
                    "snapshot_id": s.snapshot_id,
                    "match_id": s.match_id,
                    "match_clock_s": s.match_clock_s,
                    "positions": [p.model_dump() for p in s.positions],
                }
        return None

    # pass-through helpers used by run_moment_workflow
    def match_stats(self, match_id: str) -> dict:
        from agents.kql_tools import LocalKql
        return LocalKql(self._events).match_stats(match_id)

    def momentum_at(self, match_id: str, minute: int) -> dict:
        from agents.kql_tools import LocalKql
        return LocalKql(self._events).momentum_at(match_id, minute)

    def pressure_at(self, match_id: str, minute: int) -> dict:
        from agents.kql_tools import LocalKql
        return LocalKql(self._events).pressure_at(match_id, minute)

    def recent_events(self, match_id: str, minute: int, n: int = 5) -> list[dict]:
        from agents.kql_tools import LocalKql
        return LocalKql(self._events).recent_events(match_id, minute, n)


# ---------------------------------------------------------------------------
# AT-LW-01: exact match with offline builder
# ---------------------------------------------------------------------------


def test_live_watcher_matches_offline_builder(tmp_path: Any, monkeypatch: Any) -> None:
    """AT-LW-01: poll_once produces exactly the same overlay ids as the offline builder."""
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))
    from api.live import LiveMatchState, poll_once

    data = _seed7_data()
    match_id = data["match_id"]
    events = data["events"]
    snapshots = data["snapshots"]

    expected_ids = _offline_overlay_ids(match_id, events, snapshots)
    assert expected_ids, (
        "seed 7 must produce at least one overlay (ghost or goal) — check run_match(7)"
    )

    kql = FakeKql(events, snapshots)
    state = LiveMatchState(match_id=match_id)

    # Enough polls to deliver all events in 5-minute chunks + retry passes for snapshots
    max_clock = max(e.match_clock_s for e in events)
    n_event_polls = (max_clock // 300) + 2
    n_retry_polls = 3  # snapshots arrive one poll late; extra margin
    total_polls = n_event_polls + n_retry_polls

    for _ in range(total_polls):
        asyncio.run(poll_once(state, kql, None))

    actual_ids = [ov["overlay_id"] for ov in state.overlays]

    assert set(actual_ids) == set(expected_ids), (
        f"Watcher overlay ids differ from offline builder.\n"
        f"  actual  : {sorted(actual_ids)}\n"
        f"  expected: {sorted(expected_ids)}"
    )


# ---------------------------------------------------------------------------
# AT-LW-02: outage flag → source=template + reason
# ---------------------------------------------------------------------------


def test_live_watcher_outage_gives_template(tmp_path: Any, monkeypatch: Any) -> None:
    """AT-LW-02: simulate_outage forces source=template with reason 'simulated outage'."""
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))
    from api.live import LiveMatchState, poll_once

    data = _seed7_data()
    match_id = data["match_id"]
    events = data["events"]
    snapshots = data["snapshots"]

    expected_ids = _offline_overlay_ids(match_id, events, snapshots)
    if not expected_ids:
        return

    kql = FakeKql(events, snapshots)
    state = LiveMatchState(match_id=match_id)
    state.simulate_outage = True

    max_clock = max(e.match_clock_s for e in events)
    n_event_polls = (max_clock // 300) + 2
    for _ in range(n_event_polls + 3):
        asyncio.run(poll_once(state, kql, None))

    assert state.overlays, "No overlays produced with outage flag set"

    for ov in state.overlays:
        ov_id = ov["overlay_id"]
        run_info = state.ledgers.get(ov_id, {}).get("run", {})
        source = run_info.get("source", "")
        reason = run_info.get("fallback_reason", "")
        assert source == "template", (
            f"Overlay {ov_id}: expected source=template, got {source!r}"
        )
        assert reason == "simulated outage", (
            f"Overlay {ov_id}: expected fallback_reason='simulated outage', got {reason!r}"
        )


# ---------------------------------------------------------------------------
# AT-LW-03: events_since runs in a thread (non-blocking)
# ---------------------------------------------------------------------------


def test_slow_kql_does_not_block_state(tmp_path: Any, monkeypatch: Any) -> None:
    """AT-LW-03: a slow KQL call must not block concurrent event loop work."""
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))

    SLEEP = 0.3  # simulate slow Fabric; keep test fast

    class SlowKql:
        def events_since(self, match_id: str, clock_s: int) -> list:
            _time.sleep(SLEEP)
            return []

        def match_snapshot(self, *a) -> None:
            return None

        def match_stats(self, *a) -> dict:
            return {}

        def momentum_at(self, *a) -> dict:
            return {}

        def pressure_at(self, *a) -> dict:
            return {}

        def recent_events(self, *a, **kw) -> list:
            return []

        def live_matches(self) -> list:
            return []

    async def run() -> tuple[float, list[float]]:
        from api.live import LiveMatchState, poll_once

        state = LiveMatchState(match_id="match_s7_T01_T02")
        loop = asyncio.get_event_loop()
        concurrent_done: list[float] = []

        async def concurrent() -> None:
            concurrent_done.append(loop.time())

        t0 = loop.time()
        await asyncio.gather(poll_once(state, SlowKql(), None), concurrent())
        return t0, concurrent_done

    t0, done = asyncio.run(run())
    assert done, "concurrent coroutine never ran"
    assert done[0] - t0 < SLEEP * 0.5, (
        f"Event loop was blocked: concurrent ran {done[0] - t0:.3f}s after start "
        f"(KQL sleep was {SLEEP}s)"
    )
