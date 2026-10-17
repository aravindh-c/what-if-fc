"""Simulator acceptance tests.

AT-01: Deterministic simulator – same seed -> identical events and snapshots.
Plus: schema validity, data-quality rules, snapshot/pass consistency, and
per-seed stats in target ranges.
"""

from __future__ import annotations

import math

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
# Snapshot / pass consistency (seeds 1-5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_passer_in_snapshot_at_ball(seed: int) -> None:
    """Passer's position in snapshot must be within 0.5 m of the pass start coords."""
    events, snapshots = _run(seed)
    snap_by_id = {s.snapshot_id: s for s in snapshots}
    passes = [
        e for e in events
        if e.event_type == EventType.PASS and e.snapshot_id is not None
    ]
    assert passes, f"seed {seed}: no snapshotted passes"
    for ev in passes:
        snap = snap_by_id[ev.snapshot_id]
        passer_pos = next(
            p for p in snap.positions if p.player_id == ev.player_id
        )
        dist = math.hypot(passer_pos.x - ev.x, passer_pos.y - ev.y)
        assert dist < 0.5, (
            f"seed {seed} event {ev.event_id}: passer {dist:.3f} m from pass start"
        )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_receiver_in_snapshot_at_pass_end(seed: int) -> None:
    """For complete passes with a snapshot, receiver must be within 0.5 m of end."""
    events, snapshots = _run(seed)
    snap_by_id = {s.snapshot_id: s for s in snapshots}
    complete_snapped = [
        e for e in events
        if e.event_type == EventType.PASS
        and e.outcome == Outcome.COMPLETE
        and e.snapshot_id is not None
    ]
    assert complete_snapped, f"seed {seed}: no complete snapshotted passes"
    for ev in complete_snapped:
        snap = snap_by_id[ev.snapshot_id]
        rec_pos = next(
            p for p in snap.positions if p.player_id == ev.receiver_id
        )
        dist = math.hypot(rec_pos.x - ev.end_x, rec_pos.y - ev.end_y)
        assert dist < 0.5, (
            f"seed {seed} event {ev.event_id}: receiver {dist:.3f} m from pass end"
        )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_mean_pass_end_y_centred(seed: int) -> None:
    """Mean pass end_y must be within 34 ± 3 (play is not piled on the touchlines)."""
    events, _ = _run(seed)
    end_ys = [e.end_y for e in events if e.event_type == EventType.PASS and e.end_y is not None]
    assert end_ys, f"seed {seed}: no passes"
    mean_y = sum(end_ys) / len(end_ys)
    assert 31.0 <= mean_y <= 37.0, (
        f"seed {seed}: mean pass end_y {mean_y:.2f} outside 34 ± 3"
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_few_passes_near_touchline(seed: int) -> None:
    """Fewer than 15 % of passes should end within 5 m of a touchline."""
    events, _ = _run(seed)
    passes = [e for e in events if e.event_type == EventType.PASS and e.end_y is not None]
    assert passes, f"seed {seed}: no passes"
    near_line = sum(1 for e in passes if e.end_y < 5.0 or e.end_y > 63.0)
    frac = near_line / len(passes)
    assert frac < 0.15, (
        f"seed {seed}: {frac:.1%} of passes end near a touchline (limit 15 %)"
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_goal_followed_by_kickoff_of_other_team(seed: int) -> None:
    """Every GOAL event must be immediately followed by a KICKOFF of the other team."""
    events, _ = _run(seed)
    goals = [(i, e) for i, e in enumerate(events) if e.event_type == EventType.GOAL]
    if not goals:
        pytest.skip(f"seed {seed}: no goals in this match")
    for idx, goal_ev in goals:
        # Find next event after the goal
        rest = [e for e in events[idx + 1:] if e.event_type != EventType.PERIOD_END]
        assert rest, f"seed {seed}: no event after goal {goal_ev.event_id}"
        nxt = rest[0]
        assert nxt.event_type == EventType.KICKOFF, (
            f"seed {seed}: after goal {goal_ev.event_id} expected KICKOFF, got {nxt.event_type}"
        )
        assert nxt.team_id != goal_ev.team_id, (
            f"seed {seed}: kickoff after goal is by the scoring team, expected conceding team"
        )


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
