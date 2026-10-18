"""Acceptance tests for hand-designed demo scenarios.

AT-04: known-answer scenario triggers the expected key moment (covered here via
geometry checks that confirm the Ghost Pass preconditions are met).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.schemas import Outcome
from simulator.scenarios import Scenario, _build_scenarios

SCENARIOS_DIR = Path("data/scenarios")

# Build once per session; these are deterministic and cheap.
@pytest.fixture(scope="module")
def scenarios() -> list[Scenario]:
    return _build_scenarios()


# ---------------------------------------------------------------------------
# Basic validity
# ---------------------------------------------------------------------------


def test_four_scenarios_produced(scenarios: list[Scenario]) -> None:
    assert len(scenarios) == 4
    ids = {s.scenario_id for s in scenarios}
    assert ids == {
        "missed_overlap_right",
        "forced_pass_into_traffic",
        "late_counter",
        "high_press_escape",
    }


def test_all_scenarios_pydantic_valid(scenarios: list[Scenario]) -> None:
    # Re-serialise and re-parse to confirm round-trip validity.
    for s in scenarios:
        Scenario.model_validate_json(s.model_dump_json())


# ---------------------------------------------------------------------------
# Geometry: passer and receiver placement
# ---------------------------------------------------------------------------


def test_passer_at_pass_start(scenarios: list[Scenario]) -> None:
    for s in scenarios:
        pos = {p.player_id: (p.x, p.y) for p in s.snapshot.positions}
        px, py = pos[s.actual_pass.player_id]
        dist = math.hypot(px - s.actual_pass.x, py - s.actual_pass.y)
        assert dist < 0.5, (
            f"{s.scenario_id}: passer {s.actual_pass.player_id} at ({px},{py}) "
            f"but pass starts at ({s.actual_pass.x},{s.actual_pass.y})"
        )


def test_complete_pass_receiver_at_pass_end(scenarios: list[Scenario]) -> None:
    for s in scenarios:
        if s.actual_pass.outcome != Outcome.COMPLETE:
            continue
        pos = {p.player_id: (p.x, p.y) for p in s.snapshot.positions}
        rx, ry = pos[s.actual_pass.receiver_id]
        dist = math.hypot(rx - s.actual_pass.end_x, ry - s.actual_pass.end_y)
        assert dist < 0.5, (
            f"{s.scenario_id}: receiver {s.actual_pass.receiver_id} at ({rx},{ry}) "
            f"but pass ends at ({s.actual_pass.end_x},{s.actual_pass.end_y})"
        )


# ---------------------------------------------------------------------------
# Ghost receiver validity
# ---------------------------------------------------------------------------


def test_ghost_receiver_is_teammate_not_actual_receiver(scenarios: list[Scenario]) -> None:
    for s in scenarios:
        team_of = {p.player_id: p.team_id for p in s.snapshot.positions}
        ghost_id = s.expected_ghost_receiver_id
        assert ghost_id in team_of, f"{s.scenario_id}: ghost receiver not in snapshot"
        assert team_of[ghost_id] == s.in_possession, (
            f"{s.scenario_id}: ghost receiver {ghost_id} on wrong team"
        )
        assert ghost_id != s.actual_pass.receiver_id, (
            f"{s.scenario_id}: ghost receiver is the same as actual receiver"
        )


def test_ghost_receiver_onside(scenarios: list[Scenario]) -> None:
    """Ghost receiver's x must be <= second-last opposing defender's x."""
    for s in scenarios:
        defending = "T02" if s.in_possession == "T01" else "T01"
        def_xs = sorted(
            [p.x for p in s.snapshot.positions if p.team_id == defending], reverse=True
        )
        second_last_x = def_xs[1]  # def_xs[0] is the GK
        ghost_x = next(
            p.x for p in s.snapshot.positions if p.player_id == s.expected_ghost_receiver_id
        )
        assert ghost_x <= second_last_x, (
            f"{s.scenario_id}: ghost receiver x={ghost_x} offside "
            f"(second-last defender x={second_last_x})"
        )


def test_nearest_defender_to_ghost_at_least_8m(scenarios: list[Scenario]) -> None:
    for s in scenarios:
        defending = "T02" if s.in_possession == "T01" else "T01"
        pos = {p.player_id: (p.x, p.y) for p in s.snapshot.positions}
        gx, gy = pos[s.expected_ghost_receiver_id]
        min_dist = min(
            math.hypot(gx - p.x, gy - p.y)
            for p in s.snapshot.positions
            if p.team_id == defending
        )
        assert min_dist >= 8.0, (
            f"{s.scenario_id}: nearest defender to ghost is only {min_dist:.1f} m"
        )


# ---------------------------------------------------------------------------
# Pressure on actual receiver (forced_pass_into_traffic, high_press_escape)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scen_id", ["forced_pass_into_traffic", "high_press_escape"])
def test_nearest_defender_to_actual_receiver_within_4m(
    scen_id: str, scenarios: list[Scenario]
) -> None:
    s = next(sc for sc in scenarios if sc.scenario_id == scen_id)
    defending = "T02" if s.in_possession == "T01" else "T01"
    pos = {p.player_id: (p.x, p.y) for p in s.snapshot.positions}
    rx, ry = pos[s.actual_pass.receiver_id]
    min_dist = min(
        math.hypot(rx - p.x, ry - p.y)
        for p in s.snapshot.positions
        if p.team_id == defending
    )
    assert min_dist <= 4.0, (
        f"{scen_id}: nearest defender to actual receiver is {min_dist:.1f} m, expected ≤ 4 m"
    )


# ---------------------------------------------------------------------------
# JSON file consistency
# ---------------------------------------------------------------------------


def test_committed_json_matches_generated(scenarios: list[Scenario]) -> None:
    for s in scenarios:
        path = SCENARIOS_DIR / f"{s.scenario_id}.json"
        assert path.exists(), f"{path} not found; run: python -m simulator.scenarios"
        committed = json.loads(path.read_text())
        generated = json.loads(s.model_dump_json())
        assert committed == generated, (
            f"{s.scenario_id}: committed JSON differs from generated; "
            "re-run python -m simulator.scenarios --out data/scenarios"
        )
