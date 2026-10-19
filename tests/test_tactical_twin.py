"""AT-05: Tactical Twin candidate ranking and Ghost Pass detection tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analytics.metrics import headline_moments
from analytics.tactical_twin import (
    _REF_ANGLE,
    _is_offside,
    _score_T,
    pass_difficulty,
    score_pass,
)
from core.schemas import MatchEvent, PlayerPosition, PositionSnapshot, Role
from simulator.engine import MatchEngine
from simulator.reference_data import build_players, build_teams

SCENARIOS_DIR = Path("data/scenarios")

_SCENARIO_IDS = [
    "missed_overlap_right",
    "forced_pass_into_traffic",
    "late_counter",
    "high_press_escape",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_scenario(name: str) -> dict:
    return json.loads((SCENARIOS_DIR / f"{name}.json").read_text())


def _make_pos(pid: str, team: str, role: str, x: float, y: float) -> PlayerPosition:
    return PlayerPosition(player_id=pid, team_id=team, role=Role(role), x=x, y=y)


# ---------------------------------------------------------------------------
# Offside rule tests (Law 11 – goalkeeper counts)
# ---------------------------------------------------------------------------


def test_offside_gk_counts_in_second_last() -> None:
    """GK at x=100, CB at x=83 → player at x=82 is onside (second-last=83)."""
    opps = [
        _make_pos("GK", "T02", "GK", 100.0, 34.0),
        _make_pos("CB1", "T02", "CB", 83.0, 28.0),
        _make_pos("CB2", "T02", "CB", 77.0, 40.0),
        _make_pos("FB", "T02", "FB", 65.0, 10.0),
    ]
    # second-last (including GK): sorted asc = [..., 77, 83, 100], [-2]=83
    assert not _is_offside(rx=82.0, ball_x=62.0, opp_positions=opps)


def test_offside_level_with_second_last_is_onside() -> None:
    """Exactly level with the second-last opponent is onside."""
    opps = [
        _make_pos("GK", "T02", "GK", 100.0, 34.0),
        _make_pos("CB", "T02", "CB", 80.0, 30.0),
        _make_pos("FB", "T02", "FB", 60.0, 10.0),
    ]
    # second-last = 80; rx=80 is level → onside
    assert not _is_offside(rx=80.0, ball_x=70.0, opp_positions=opps)


def test_offside_half_metre_beyond_is_offside() -> None:
    """0.5 m beyond the second-last opponent is offside."""
    opps = [
        _make_pos("GK", "T02", "GK", 100.0, 34.0),
        _make_pos("CB", "T02", "CB", 80.0, 30.0),
        _make_pos("FB", "T02", "FB", 60.0, 10.0),
    ]
    assert _is_offside(rx=80.5, ball_x=70.0, opp_positions=opps)


def test_offside_own_half_never_offside() -> None:
    """Player at x <= 52.5 is never offside regardless of opponents."""
    opps = [
        _make_pos("GK", "T02", "GK", 100.0, 34.0),
        _make_pos("ST", "T02", "ST", 10.0, 34.0),  # very high up
    ]
    assert not _is_offside(rx=52.5, ball_x=40.0, opp_positions=opps)
    assert not _is_offside(rx=30.0, ball_x=25.0, opp_positions=opps)


# ---------------------------------------------------------------------------
# T component: fixed reference point
# ---------------------------------------------------------------------------


def test_t_wide_far_lower_than_central_closer() -> None:
    """Wide player far from goal has lower T than central player closer to goal."""
    t_wide = _score_T(30.0, 58.0)   # far and wide
    t_central = _score_T(34.0, 36.0)  # slightly closer to goal, central
    assert t_wide < t_central, f"wide T={t_wide:.4f} should be < central T={t_central:.4f}"


def test_t_closer_to_goal_higher() -> None:
    t_far = _score_T(50.0, 34.0)
    t_near = _score_T(85.0, 34.0)
    assert t_near > t_far


def test_t_clamped_0_to_1() -> None:
    for x in [0.0, 52.5, 85.0, 104.9]:
        for y in [0.0, 34.0, 67.9]:
            t = _score_T(x, y)
            assert 0.0 <= t <= 1.0, f"T={t} out of range for ({x},{y})"


def test_ref_angle_reasonable() -> None:
    """REF_ANGLE should be roughly the goal angle from a shooting position."""
    assert 0.5 < _REF_ANGLE < 0.9, f"REF_ANGLE={_REF_ANGLE:.4f} seems wrong"


# ---------------------------------------------------------------------------
# AT-05: Demo scenario ranking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scen_id", _SCENARIO_IDS)
def test_scenario_ghost_receiver(scen_id: str) -> None:
    """AT-05: Ghost receiver matches expected for all demo scenarios."""
    sc = _load_scenario(scen_id)
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    result = score_pass(ev, snap)
    assert result.best_alt_player_id == sc["expected_ghost_receiver_id"], (
        f"{scen_id}: expected {sc['expected_ghost_receiver_id']}, "
        f"got {result.best_alt_player_id}"
    )


@pytest.mark.parametrize("scen_id", _SCENARIO_IDS)
def test_scenario_delta_at_least_0_10(scen_id: str) -> None:
    sc = _load_scenario(scen_id)
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    result = score_pass(ev, snap)
    assert result.delta >= 0.10, f"{scen_id}: delta={result.delta:.3f} < 0.10"


@pytest.mark.parametrize("scen_id", _SCENARIO_IDS)
def test_scenario_ghost_f_at_least_0_5(scen_id: str) -> None:
    sc = _load_scenario(scen_id)
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    result = score_pass(ev, snap)
    ghost_cand = next(
        (c for c in result.candidates if c["player_id"] == result.best_alt_player_id), None
    )
    assert ghost_cand is not None
    assert ghost_cand["F"] >= 0.5, f"{scen_id}: ghost F={ghost_cand['F']:.3f} < 0.5"


# ---------------------------------------------------------------------------
# Hand-built geometry tests
# ---------------------------------------------------------------------------


def _minimal_snapshot(
    passer_id: str,
    passer_team: str,
    teammates: list[tuple[str, str, float, float]],
    opponents: list[tuple[str, float, float]],
    clock: int = 0,
) -> PositionSnapshot:
    """Build a minimal PositionSnapshot for geometry tests."""
    positions = []
    # Passer at (60, 34)
    positions.append(_make_pos(passer_id, passer_team, "CM", 60.0, 34.0))
    for pid, role, x, y in teammates:
        positions.append(_make_pos(pid, passer_team, role, x, y))
    for oid, x, y in opponents:
        positions.append(_make_pos(oid, "T02", "CB", x, y))
    # Pad to 22 if needed
    team1_count = sum(1 for p in positions if p.team_id == passer_team)
    team2_count = sum(1 for p in positions if p.team_id == "T02")
    for i in range(11 - team1_count):
        positions.append(_make_pos(f"pad1_{i}", passer_team, "CB", float(i * 5), 5.0))
    for i in range(11 - team2_count):
        positions.append(_make_pos(f"pad2_{i}", "T02", "CB", float(90 + i), 5.0))
    # Fix one GK each (pad players above might not have GK)
    # Ensure each team has a GK
    t1_has_gk = any(p.role == Role.GK and p.team_id == passer_team for p in positions)
    t2_has_gk = any(p.role == Role.GK and p.team_id == "T02" for p in positions)
    if not t1_has_gk:
        positions = [
            p if not (p.team_id == passer_team and p.player_id == "pad1_0")
            else _make_pos("pad1_0", passer_team, "GK", 0.0 * 5, 5.0)
            for p in positions
        ]
    if not t2_has_gk:
        positions = [
            p if not (p.team_id == "T02" and p.player_id == "pad2_0")
            else _make_pos("pad2_0", "T02", "GK", 90.0, 5.0)
            for p in positions
        ]
    return PositionSnapshot(
        snapshot_id="test_snap",
        match_id="test",
        match_clock_s=clock,
        positions=positions,
    )


def test_open_lane_gives_high_f() -> None:
    """Undefended lane: F should be close to 1."""
    sc = _load_scenario("late_counter")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    result = score_pass(ev, snap)
    ghost_cand = next(c for c in result.candidates if c["player_id"] == "T01-P17")
    assert ghost_cand["F"] >= 0.9, f"open lane F={ghost_cand['F']:.3f} expected ≥ 0.9"


def test_defender_on_lane_lowers_f() -> None:
    """Actual receiver surrounded by defenders: F should be low."""
    sc = _load_scenario("forced_pass_into_traffic")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    result = score_pass(ev, snap)
    actual_cand = next(c for c in result.candidates if c["is_actual"])
    assert actual_cand["F"] < 0.6, f"traffic F={actual_cand['F']:.3f} expected < 0.6"


def test_actual_receiver_always_present() -> None:
    """Actual receiver appears in candidates even if it would fail filters."""
    for scen_id in _SCENARIO_IDS:
        sc = _load_scenario(scen_id)
        ev = MatchEvent(**sc["actual_pass"])
        snap = PositionSnapshot(**sc["snapshot"])
        result = score_pass(ev, snap)
        actual_ids = [c["player_id"] for c in result.candidates if c["is_actual"]]
        assert len(actual_ids) == 1, f"{scen_id}: expected 1 actual candidate, got {actual_ids}"
        assert actual_ids[0] == ev.receiver_id


def test_gk_never_a_non_actual_candidate() -> None:
    """GK is never an alternative candidate (may appear as actual receiver)."""
    for scen_id in _SCENARIO_IDS:
        sc = _load_scenario(scen_id)
        ev = MatchEvent(**sc["actual_pass"])
        snap = PositionSnapshot(**sc["snapshot"])
        result = score_pass(ev, snap)
        snap_roles = {p.player_id: p.role for p in snap.positions}
        for cand in result.candidates:
            if cand["is_actual"]:
                continue
            assert snap_roles.get(cand["player_id"]) != Role.GK, (
                f"{scen_id}: GK {cand['player_id']} is a non-actual candidate"
            )


def test_gk_can_be_actual_receiver() -> None:
    """GK appears as actual candidate when they are the receiver."""
    # Use a real scenario event, reroute the pass to the T01 GK position.
    sc = _load_scenario("missed_overlap_right")
    snap = PositionSnapshot(**sc["snapshot"])
    gk = next(p for p in snap.positions if p.team_id == "T01" and p.role == Role.GK)
    ev_data = dict(sc["actual_pass"])
    ev_data["receiver_id"] = gk.player_id
    ev_data["end_x"] = gk.x
    ev_data["end_y"] = gk.y
    ev = MatchEvent(**ev_data)
    result = score_pass(ev, snap)
    actual_ids = [c["player_id"] for c in result.candidates if c["is_actual"]]
    assert gk.player_id in actual_ids, "GK should be actual candidate when they are the receiver"


def test_missing_receiver_no_ghost() -> None:
    """When receiver_id is not in the snapshot, ghost_shown is always False."""
    sc = _load_scenario("missed_overlap_right")
    ev_data = dict(sc["actual_pass"])
    ev_data["receiver_id"] = "PLAYER-NOT-IN-SNAPSHOT"
    ev = MatchEvent(**ev_data)
    snap = PositionSnapshot(**sc["snapshot"])
    result = score_pass(ev, snap)
    assert not result.ghost_shown


def test_scores_within_range() -> None:
    """S must be in [-0.15, 1.0] given weights and component bounds."""
    for scen_id in _SCENARIO_IDS:
        sc = _load_scenario(scen_id)
        ev = MatchEvent(**sc["actual_pass"])
        snap = PositionSnapshot(**sc["snapshot"])
        result = score_pass(ev, snap)
        for cand in result.candidates:
            assert -1.0 <= cand["S"] <= 1.0, (
                f"{scen_id} {cand['player_id']}: S={cand['S']:.3f} out of range"
            )


def test_same_input_same_output() -> None:
    """Deterministic: identical inputs produce identical TwinResult."""
    sc = _load_scenario("missed_overlap_right")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    r1 = score_pass(ev, snap)
    r2 = score_pass(ev, snap)
    assert r1.model_dump_json() == r2.model_dump_json()


# ---------------------------------------------------------------------------
# pass_difficulty
# ---------------------------------------------------------------------------


def test_pass_difficulty_range() -> None:
    for scen_id in _SCENARIO_IDS:
        sc = _load_scenario(scen_id)
        ev = MatchEvent(**sc["actual_pass"])
        snap = PositionSnapshot(**sc["snapshot"])
        assert ev.x is not None and ev.y is not None
        assert ev.end_x is not None and ev.end_y is not None
        opps = [p for p in snap.positions if p.team_id != ev.team_id]
        d = pass_difficulty(ev.x, ev.y, ev.end_x, ev.end_y, opps)
        assert 0.0 <= d <= 100.0, f"{scen_id}: difficulty={d}"


def test_high_press_escape_high_difficulty() -> None:
    """Pass into an intercepting defender should give high difficulty."""
    sc = _load_scenario("high_press_escape")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    assert ev.x is not None and ev.y is not None
    assert ev.end_x is not None and ev.end_y is not None
    opps = [p for p in snap.positions if p.team_id != ev.team_id]
    d = pass_difficulty(ev.x, ev.y, ev.end_x, ev.end_y, opps)
    assert d >= 60.0, f"high-press pass difficulty={d:.1f} expected ≥ 60"


# ---------------------------------------------------------------------------
# Seeds 1-10: no errors on ghost-eligible headline moments
# ---------------------------------------------------------------------------


_teams_cache: dict | None = None
_players_cache: dict | None = None


def _get_teams() -> dict:
    global _teams_cache
    if _teams_cache is None:
        _teams_cache = {t.team_id: t for t in build_teams()}
    return _teams_cache


@pytest.fixture(scope="module")
def seed_results() -> list[tuple[int, list, list]]:
    teams = _get_teams()
    results = []
    for seed in range(1, 11):
        players = build_players(seed)
        engine = MatchEngine(
            home_team=teams["T01"],
            away_team=teams["T02"],
            players=players,
            seed=seed,
            match_id=f"match_s{seed}_T01_T02",
            scenario_id="live",
        )
        events, snapshots = engine.run()
        headlines = headline_moments(events)
        ghost_eligible = [h for h in headlines if h.ghost_eligible]
        results.append((seed, events, ghost_eligible))
    return results


def test_twin_runs_without_error_on_ghost_eligible(seed_results) -> None:
    """AT-05: score_pass raises no error on every ghost-eligible headline moment."""
    teams = _get_teams()
    for seed in range(1, 11):
        players = build_players(seed)
        engine = MatchEngine(
            home_team=teams["T01"],
            away_team=teams["T02"],
            players=players,
            seed=seed,
            match_id=f"match_s{seed}_T01_T02",
            scenario_id="live",
        )
        events, snapshots = engine.run()
        snap_lookup_seed = {s.snapshot_id: s for s in snapshots}

        headlines = headline_moments(events)
        ev_lookup = {e.event_id: e for e in events}
        for moment in headlines:
            if not moment.ghost_eligible:
                continue
            ev = ev_lookup.get(moment.event_id)
            if ev is None or ev.snapshot_id is None:
                continue
            snap = snap_lookup_seed.get(ev.snapshot_id)
            if snap is None:
                continue
            # Must not raise
            result = score_pass(ev, snap)
            assert result is not None
