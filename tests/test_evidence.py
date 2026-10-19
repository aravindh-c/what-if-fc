"""AT-05: Evidence packet tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analytics.evidence import _LABEL, EvidencePacket, build_evidence_packet
from analytics.tactical_twin import score_pass
from core.schemas import MatchEvent, PositionSnapshot

SCENARIOS_DIR = Path("data/scenarios")


def _load_scenario(name: str) -> dict:
    return json.loads((SCENARIOS_DIR / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def missed_overlap_packet() -> EvidencePacket:
    sc = _load_scenario("missed_overlap_right")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    # Create a minimal KeyMoment-like object for the evidence builder
    from analytics.metrics import KeyMoment
    moment = KeyMoment(
        moment_id="km_test",
        match_id="demo",
        match_clock_s=ev.match_clock_s,
        moment_type="high_pressure_final_third_pass",
        team_id=ev.team_id,
        event_id=ev.event_id,
        snapshot_id=ev.snapshot_id,
        source_event_id=None,
        value=ev.pressure_level,
        score=0.7,
        ghost_eligible=True,
    )
    return build_evidence_packet(moment, [ev], snap, twin, match_id="demo")


def test_evidence_packet_is_json_serialisable(missed_overlap_packet: EvidencePacket) -> None:
    raw = missed_overlap_packet.model_dump_json()
    parsed = json.loads(raw)
    assert parsed["match_id"] == "demo"


def test_evidence_packet_deterministic() -> None:
    sc = _load_scenario("high_press_escape")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    from analytics.metrics import KeyMoment
    moment = KeyMoment(
        moment_id="km_test2",
        match_id="demo",
        match_clock_s=ev.match_clock_s,
        moment_type="high_pressure_final_third_pass",
        team_id=ev.team_id,
        event_id=ev.event_id,
        snapshot_id=ev.snapshot_id,
        source_event_id=None,
        value=ev.pressure_level,
        score=0.8,
        ghost_eligible=True,
    )
    p1 = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")
    p2 = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")
    assert p1.model_dump_json() == p2.model_dump_json()


def test_evidence_packet_has_label(missed_overlap_packet: EvidencePacket) -> None:
    assert missed_overlap_packet.label == _LABEL


def test_evidence_packet_trigger_event_in_ids(missed_overlap_packet: EvidencePacket) -> None:
    sc = _load_scenario("missed_overlap_right")
    assert sc["actual_pass"]["event_id"] in missed_overlap_packet.event_ids


def test_evidence_packet_ghost_shown(missed_overlap_packet: EvidencePacket) -> None:
    assert missed_overlap_packet.ghost_shown is True
    assert missed_overlap_packet.twin_delta >= 0.10


def test_evidence_packet_formula_version(missed_overlap_packet: EvidencePacket) -> None:
    assert missed_overlap_packet.formula_version == "twin-v1"


def test_evidence_packet_pass_difficulty_range(missed_overlap_packet: EvidencePacket) -> None:
    assert 0.0 <= missed_overlap_packet.pass_difficulty <= 100.0


def test_evidence_packet_scores_match_twin() -> None:
    sc = _load_scenario("forced_pass_into_traffic")
    ev = MatchEvent(**sc["actual_pass"])
    snap = PositionSnapshot(**sc["snapshot"])
    twin = score_pass(ev, snap)
    from analytics.metrics import KeyMoment
    moment = KeyMoment(
        moment_id="km_test3",
        match_id="demo",
        match_clock_s=ev.match_clock_s,
        moment_type="high_pressure_final_third_pass",
        team_id=ev.team_id,
        event_id=ev.event_id,
        snapshot_id=ev.snapshot_id,
        source_event_id=None,
        value=ev.pressure_level,
        score=0.6,
        ghost_eligible=True,
    )
    pkt = build_evidence_packet(moment, [ev], snap, twin, match_id="demo")
    assert pkt.twin_actual_score == twin.scores.actual
    assert pkt.twin_ghost_score == twin.scores.ghost
    assert pkt.twin_ghost_player_id == twin.best_alt_player_id
