"""Tests for agents.templates – deterministic fallback narratives.

Verifies that build_narrative output always passes analytics.validation.validate_text
on all 4 hand-designed demo scenarios and on every headline moment of seeds 1–5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.templates import build_narrative
from analytics.evidence import EvidencePacket, build_evidence_packet
from analytics.metrics import KeyMoment
from analytics.tactical_twin import score_pass
from analytics.validation import validate_text
from core.schemas import MatchEvent, OverlayText, PositionSnapshot

SCENARIOS_DIR = Path("data/scenarios")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_scenario(name: str) -> dict:
    return json.loads((SCENARIOS_DIR / f"{name}.json").read_text())


def _roster(seed: int = 7):
    from simulator.reference_data import build_players

    return build_players(seed)


def _moment_for_pass(ev: MatchEvent) -> KeyMoment:
    return KeyMoment(
        moment_id=f"km_{ev.event_id}",
        match_id="demo",
        match_clock_s=ev.match_clock_s,
        moment_type="high_pressure_final_third_pass",
        team_id=ev.team_id or "T01",
        event_id=ev.event_id,
        snapshot_id=ev.snapshot_id,
        source_event_id=None,
        value=ev.pressure_level,
        score=0.7,
        ghost_eligible=True,
    )


# ---------------------------------------------------------------------------
# Smoke test on all 4 demo scenarios
# ---------------------------------------------------------------------------

_DEMO_SCENARIO_IDS = [
    "missed_overlap_right",
    "forced_pass_into_traffic",
    "late_counter",
    "high_press_escape",
]


@pytest.mark.parametrize("scenario_id", _DEMO_SCENARIO_IDS)
def test_template_passes_validator_on_demo_scenario(scenario_id: str) -> None:
    """build_narrative output must pass validate_text on every demo scenario."""
    sc = _load_scenario(scenario_id)
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    moment = _moment_for_pass(ev)
    roster = _roster(7)

    packet = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")
    text: OverlayText = build_narrative(packet, roster)

    errors = validate_text(text, packet, roster)
    assert errors == [], f"[{scenario_id}] validator found errors: {errors}"


# ---------------------------------------------------------------------------
# Validate on every headline moment of seeds 1–5
# ---------------------------------------------------------------------------


def _build_packet_for_moment(
    moment: KeyMoment,
    events: list,
    snap_map: dict,
    roster: list,
) -> EvidencePacket | None:
    snap = snap_map.get(moment.snapshot_id) if moment.snapshot_id else None
    trigger_id = moment.source_event_id or moment.event_id
    trigger_ev = next((e for e in events if e.event_id == trigger_id), None)
    if trigger_ev is None:
        return None
    twin = score_pass(trigger_ev, snap) if (
        snap is not None
        and trigger_ev.event_type in ("pass",)
        and trigger_ev.end_x is not None
    ) else _dummy_twin(trigger_ev)
    return build_evidence_packet(moment, events, snap, twin, match_id=moment.match_id)


def _dummy_twin(ev: MatchEvent):
    """Return a minimal TwinResult for non-pass / no-snapshot moments."""
    from analytics.tactical_twin import TwinResult
    from core.schemas import OverlayVisual, TwinScores

    return TwinResult(
        version="twin-v1",
        weights={"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15},
        candidates=[],
        actual_player_id=ev.player_id or "unknown",
        best_alt_player_id=None,
        delta=0.0,
        ghost_shown=False,
        visual=OverlayVisual(),
        scores=TwinScores(
            actual=0.0,
            ghost=0.0,
            components_actual={"T": 0.0, "P": 0.0, "F": 0.0, "R": 0.0},
            components_ghost={"T": 0.0, "P": 0.0, "F": 0.0, "R": 0.0},
        ),
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_template_passes_validator_for_seed_headline_moments(seed: int) -> None:
    """build_narrative must pass validate_text for every headline moment of seeds 1–5."""
    from analytics.metrics import headline_moments
    from simulator.engine import MatchEngine
    from simulator.reference_data import build_players, build_teams

    teams = {t.team_id: t for t in build_teams()}
    players = build_players(seed)
    engine = MatchEngine(
        home_team=teams["T01"],
        away_team=teams["T02"],
        players=players,
        seed=seed,
        match_id=f"match_s{seed}_T01_T02",
        scenario_id="test",
    )
    events, snapshots = engine.run()
    snap_map = {s.snapshot_id: s for s in snapshots}
    roster = players

    moments = headline_moments(events)
    assert moments, f"seed {seed}: no headline moments generated"

    failures: list[str] = []
    for moment in moments:
        packet = _build_packet_for_moment(moment, events, snap_map, roster)
        if packet is None:
            continue
        text = build_narrative(packet, roster)
        errs = validate_text(text, packet, roster)
        if errs:
            failures.append(
                f"[seed={seed}, moment={moment.moment_id}, type={moment.moment_type}]: "
                + "; ".join(errs)
            )

    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Unit tests on build_narrative return type and structure
# ---------------------------------------------------------------------------


def test_build_narrative_returns_overlay_text() -> None:
    sc = _load_scenario("missed_overlap_right")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    moment = _moment_for_pass(ev)
    roster = _roster(7)
    packet = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")

    result = build_narrative(packet, roster)
    assert isinstance(result, OverlayText)
    assert "en" in result.analyst
    assert "en" in result.fan


def test_build_narrative_headline_max_80() -> None:
    sc = _load_scenario("forced_pass_into_traffic")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    moment = _moment_for_pass(ev)
    roster = _roster(7)
    packet = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")

    result = build_narrative(packet, roster)
    assert len(result.analyst["en"].headline) <= 80
    assert len(result.fan["en"].headline) <= 80


def test_build_narrative_body_max_280() -> None:
    sc = _load_scenario("late_counter")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    moment = _moment_for_pass(ev)
    roster = _roster(7)
    packet = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")

    result = build_narrative(packet, roster)
    assert len(result.analyst["en"].body) <= 280
    assert len(result.fan["en"].body) <= 280


def test_build_narrative_no_banned_terms() -> None:
    sc = _load_scenario("high_press_escape")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    moment = _moment_for_pass(ev)
    roster = _roster(7)
    packet = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")

    result = build_narrative(packet, roster)
    all_text = (
        result.analyst["en"].headline
        + " "
        + result.analyst["en"].body
        + " "
        + result.fan["en"].headline
        + " "
        + result.fan["en"].body
    ).lower()
    for banned in ("xg", "xa", "xt", "expected goals", "probability", "% chance"):
        assert banned not in all_text, f"Banned term {banned!r} in template text"
