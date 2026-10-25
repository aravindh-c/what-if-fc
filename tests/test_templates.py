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


# ---------------------------------------------------------------------------
# Turnover player naming: ball_won_by must appear in text, not ball_lost_by
# ---------------------------------------------------------------------------


def test_turnover_text_names_ball_winner() -> None:
    """Seed 11's 69' turnover: Noel Rutherglen wins the ball, Wren Falkner loses it."""
    from analytics.metrics import key_moments, pass_event_for
    from analytics.tactical_twin import score_pass as _score_pass
    from simulator.reference_data import build_players
    from simulator.run import run_match

    match_id, events, snapshots = run_match(11, "T01", "T02")
    snap_map = {s.snapshot_id: s for s in snapshots}
    roster = build_players(11)
    roster_map = {p.player_id: p.name for p in roster}

    # Find the 69-minute final_third_turnover
    km_69 = next(
        (
            km for km in key_moments(events)
            if km.moment_type == "final_third_turnover"
            and km.match_clock_s // 60 == 69
        ),
        None,
    )
    assert km_69 is not None, "Seed 11 must have a final_third_turnover at 69'"

    pass_ev = pass_event_for(km_69, events)
    assert pass_ev is not None, "69' turnover must have a source pass event"

    snap = snap_map.get(pass_ev.snapshot_id or "")
    assert snap is not None, "69' turnover source pass must have a snapshot"

    twin = _score_pass(pass_ev, snap)
    packet = build_evidence_packet(km_69, events, snap, twin, match_id)

    assert packet.ball_won_by is not None, "ball_won_by must be set for FTT moments"
    assert packet.ball_lost_by is not None, "ball_lost_by must be set for FTT moments"

    winner_name = roster_map.get(packet.ball_won_by, "")
    loser_name = roster_map.get(packet.ball_lost_by, "")

    assert winner_name == "Noel Rutherglen", (
        f"Expected ball_won_by=Noel Rutherglen, got {winner_name!r}"
    )
    assert loser_name == "Wren Falkner", (
        f"Expected ball_lost_by=Wren Falkner, got {loser_name!r}"
    )

    result = build_narrative(packet, roster)
    full_text = " ".join([
        result.analyst["en"].headline, result.analyst["en"].body,
        result.fan["en"].headline, result.fan["en"].body,
    ])

    assert "Noel Rutherglen" in full_text, (
        f"Ball winner 'Noel Rutherglen' not found in turnover text:\n{full_text}"
    )
    assert "Wren Falkner wins" not in full_text, (
        f"Ball loser 'Wren Falkner wins' must not appear in turnover text:\n{full_text}"
    )


# ---------------------------------------------------------------------------
# Space-language: template must respect ghost_nearest_defender_m gate
# ---------------------------------------------------------------------------


def _build_ghost_pass_packet(ghost_nearest_def: float, actual_nearest_def: float):
    """Minimal EvidencePacket for a ghost_pass moment with custom defender distances."""
    from analytics.evidence import EvidencePacket, LiveMetrics

    live = LiveMetrics(
        minute=42,
        momentum_share={"T01": 0.55, "T02": 0.45},
        pressure_index={"T01": 1.2, "T02": 0.8},
        scoreline={"T01": 0, "T02": 0},
    )
    return EvidencePacket(
        match_id="match_test",
        moment_type="ghost_pass",
        moment_minute=42,
        moment_score=0.7,
        event_ids=["ev_tpl001"],
        live_metrics=live,
        twin_version="twin-v1",
        twin_weights={"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15},
        twin_delta=0.22,
        twin_actual_score=0.41,
        twin_ghost_score=0.63,
        twin_ghost_player_id="T01-P08",
        twin_components_actual={"T": 0.4, "P": 0.3, "F": 0.7, "R": 0.2},
        twin_components_ghost={"T": 0.7, "P": 0.6, "F": 0.9, "R": 0.1},
        pass_difficulty=28.5,
        ghost_shown=True,
        formula_version="twin-v1",
        label=(
            "Tactical option score, roughly 0 to 1 "
            "(very risky passes can go below 0): "
            "how threatening, forward, open and safe a pass was. "
            "Higher is better. Not a probability."
        ),
        passer_id="T01-P12",
        actual_receiver_id="T01-P10",
        highlight_defenders=["T02-P03"],
        actual_pass_length_m=18.5,
        ghost_pass_length_m=31.2,
        actual_nearest_defender_m=actual_nearest_def,
        ghost_nearest_defender_m=ghost_nearest_def,
    )


def test_ghost_pass_text_uses_free_when_condition_met() -> None:
    """Fan headline must mention 'free' when ghost_def >= 10 AND > actual_def."""
    packet = _build_ghost_pass_packet(ghost_nearest_def=12.0, actual_nearest_def=3.1)
    roster = _roster(7)
    result = build_narrative(packet, roster)
    fan_text = result.fan["en"].headline + " " + result.fan["en"].body
    assert "free" in fan_text.lower(), (
        f"Expected 'free' in fan text when condition met; got:\n{fan_text}"
    )
    errors = validate_text(result, packet, roster)
    assert errors == [], f"Template output failed validation: {errors}"


def test_ghost_pass_text_uses_component_reason_when_not_free() -> None:
    """Fan text must NOT use 'free' when ghost_def < 10; must use a component reason."""
    import re

    packet = _build_ghost_pass_packet(ghost_nearest_def=8.3, actual_nearest_def=3.1)
    roster = _roster(7)
    result = build_narrative(packet, roster)
    fan_text = result.fan["en"].headline + " " + result.fan["en"].body
    assert not re.search(r"\b(free|unmarked|wide\s+open)\b", fan_text, re.IGNORECASE), (
        f"Space word must not appear when condition not met; got:\n{fan_text}"
    )
    component_phrases = [
        "a clearer passing lane",
        "far less risk of losing it",
        "more forward progress",
        "a more threatening position",
    ]
    assert any(phrase in fan_text for phrase in component_phrases), (
        f"Expected a component-reason phrase; got:\n{fan_text}"
    )
    errors = validate_text(result, packet, roster)
    assert errors == [], f"Template output failed validation: {errors}"
