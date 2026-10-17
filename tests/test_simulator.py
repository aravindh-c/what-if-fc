"""Simulator acceptance tests.

AT-01: Deterministic simulator – same seed -> identical events and snapshots.
Plus: schema validity, data-quality rules, and per-seed stats in target ranges.
"""

from __future__ import annotations

import pytest

from core.schemas import EventType, MatchEvent, Outcome, PositionSnapshot
from simulator.engine import MatchEngine
from simulator.reference_data import build_players, build_teams

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _run(
    seed: int, home_id: str = "T01", away_id: str = "T02"
) -> tuple[list[MatchEvent], list[PositionSnapshot]]:
    teams   = {t.team_id: t for t in build_teams()}
    players = build_players(seed)
    engine  = MatchEngine(
        home_team=teams[home_id],
        away_team=teams[away_id],
        players=players,
        seed=seed,
        match_id=f"test_{seed}",
        scenario_id="test",
    )
    return engine.run()


@pytest.fixture(scope="module")
def match_seed7() -> tuple[list[MatchEvent], list[PositionSnapshot]]:
    return _run(7)


# ---------------------------------------------------------------------------
# AT-01: Deterministic simulator
# ---------------------------------------------------------------------------

def test_at01_same_seed_same_events() -> None:
    """AT-01: Same seed produces identical events."""
    e1, s1 = _run(42)
    e2, s2 = _run(42)
    assert [e.model_dump() for e in e1] == [e.model_dump() for e in e2]
    assert [s.model_dump() for s in s1] == [s.model_dump() for s in s2]


def test_at01_different_seed_different_events() -> None:
    """AT-01: Different seeds produce different events."""
    e1, _ = _run(1)
    e2, _ = _run(2)
    assert e1 != e2


# ---------------------------------------------------------------------------
# Schema and data-quality rules
# ---------------------------------------------------------------------------

def test_all_events_are_match_events(match_seed7: tuple) -> None:
    events, _ = match_seed7
    for ev in events:
        assert isinstance(ev, MatchEvent)


def test_all_snapshots_are_position_snapshots(match_seed7: tuple) -> None:
    _, snapshots = match_seed7
    for sn in snapshots:
        assert isinstance(sn, PositionSnapshot)


def test_event_ids_unique(match_seed7: tuple) -> None:
    events, _ = match_seed7
    ids = [e.event_id for e in events]
    assert len(set(ids)) == len(ids)


def test_snapshot_ids_unique(match_seed7: tuple) -> None:
    _, snapshots = match_seed7
    ids = [s.snapshot_id for s in snapshots]
    assert len(set(ids)) == len(ids)


def test_clock_non_decreasing(match_seed7: tuple) -> None:
    events, _ = match_seed7
    clocks = [e.match_clock_s for e in events]
    assert clocks == sorted(clocks), "match_clock_s must never decrease"


def test_all_snapshot_ids_on_events_resolve(match_seed7: tuple) -> None:
    events, snapshots = match_seed7
    snap_ids = {s.snapshot_id for s in snapshots}
    missing  = [
        e.snapshot_id for e in events
        if e.snapshot_id is not None and e.snapshot_id not in snap_ids
    ]
    assert not missing, f"unresolved snapshot_ids on events: {missing}"


def test_snapshots_only_on_pass_events(match_seed7: tuple) -> None:
    events, _ = match_seed7
    for ev in events:
        if ev.snapshot_id is not None:
            assert ev.event_type == EventType.PASS, (
                f"snapshot_id set on non-pass event {ev.event_id} ({ev.event_type})"
            )


def test_periods_are_1_and_2(match_seed7: tuple) -> None:
    events, _ = match_seed7
    periods = {e.period for e in events}
    assert periods == {1, 2}


def test_two_period_end_events(match_seed7: tuple) -> None:
    events, _ = match_seed7
    period_ends = [e for e in events if e.event_type == EventType.PERIOD_END]
    assert len(period_ends) == 2


def test_snapshots_have_22_players(match_seed7: tuple) -> None:
    _, snapshots = match_seed7
    for sn in snapshots:
        assert len(sn.positions) == 22


# ---------------------------------------------------------------------------
# Stats within target ranges across seeds 1–5
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_stats_in_range(seed: int) -> None:
    """Stats must fall within design targets for each seed."""
    events, snapshots = _run(seed)

    passes   = [e for e in events if e.event_type == EventType.PASS]
    complete = [p for p in passes if p.outcome == Outcome.COMPLETE]
    shots    = [e for e in events if e.event_type == EventType.SHOT]
    goals    = [e for e in events if e.event_type == EventType.GOAL]

    assert passes, "no passes generated"

    comp_pct = len(complete) / len(passes)
    assert 0.78 <= comp_pct <= 0.88, (
        f"seed {seed}: pass completion {comp_pct:.2%} outside 78–88 %"
    )
    assert 8 <= len(shots) <= 20, (
        f"seed {seed}: shots {len(shots)} outside 8–20"
    )
    assert 0 <= len(goals) <= 5, (
        f"seed {seed}: goals {len(goals)} outside 0–5"
    )
    assert 1200 <= len(events) <= 2500, (
        f"seed {seed}: events {len(events)} outside 1 200–2 500"
    )
    assert len(snapshots) > 0, f"seed {seed}: no snapshots generated"
