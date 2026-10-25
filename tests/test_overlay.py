"""Tests for agents.overlay – build_overlay and player_name_map.

AT-06: overlay event_ids all come from packet.event_ids
AT-07: evidence metrics values match packet values after rounding
AT-09: validate_text passes on the overlay text (fan ⊆ analyst numbers)
"""

from __future__ import annotations

import pytest

from agents.overlay import build_overlay, player_name_map
from agents.templates import build_narrative
from analytics.evidence import EvidencePacket, LiveMetrics
from analytics.tactical_twin import TwinResult
from analytics.validation import validate_text
from core.schemas import (
    MomentType,
    NarrativeSource,
    NarrativeText,
    Overlay,
    OverlayText,
    OverlayVisual,
    PassLine,
    TwinScores,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _build_packet(
    moment_type: str = "high_pressure_final_third_pass",
    ghost_shown: bool = True,
    event_ids: list[str] | None = None,
    passer_id: str = "T01-P07",
    actual_receiver_id: str = "T01-P10",
    ghost_player_id: str = "T01-P08",
    actual_score: float = 0.41,
    ghost_score: float = 0.63,
    delta: float = 0.22,
) -> EvidencePacket:
    eids = event_ids or ["ev_abc001", "ev_abc002"]
    live = LiveMetrics(
        minute=34,
        momentum_share={"T01": 0.55, "T02": 0.45},
        pressure_index={"T01": 1.2, "T02": 0.8},
        scoreline={"T01": 0, "T02": 0},
    )
    return EvidencePacket(
        match_id="match_overlay_test",
        moment_type=moment_type,
        moment_minute=34,
        moment_score=0.7,
        event_ids=eids,
        live_metrics=live,
        twin_version="twin-v1",
        twin_weights={"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15},
        twin_delta=delta,
        twin_actual_score=actual_score,
        twin_ghost_score=ghost_score,
        twin_ghost_player_id=ghost_player_id,
        twin_components_actual={"T": 0.4, "P": 0.3, "F": 0.7, "R": 0.2},
        twin_components_ghost={"T": 0.7, "P": 0.6, "F": 0.9, "R": 0.1},
        pass_difficulty=28.5,
        ghost_shown=ghost_shown,
        formula_version="twin-v1",
        label="Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.",
        passer_id=passer_id,
        actual_receiver_id=actual_receiver_id,
        highlight_defenders=["T02-P03"],
        actual_pass_length_m=18.5,
        ghost_pass_length_m=31.2,
        actual_nearest_defender_m=3.1,
        ghost_nearest_defender_m=8.3,
    )


def _build_twin(ghost_shown: bool = True) -> TwinResult:
    if ghost_shown:
        visual = OverlayVisual(
            actual=PassLine(
                **{"from": (60.0, 25.0), "to": (75.0, 30.0)},
                receiver_id="T01-P10",
            ),
            ghost=PassLine(
                **{"from": (60.0, 25.0), "to": (80.0, 40.0)},
                receiver_id="T01-P08",
            ),
        )
    else:
        visual = OverlayVisual()

    return TwinResult(
        version="twin-v1",
        weights={"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15},
        candidates=[],
        actual_player_id="T01-P10",
        best_alt_player_id="T01-P08" if ghost_shown else None,
        delta=0.22 if ghost_shown else 0.0,
        ghost_shown=ghost_shown,
        visual=visual,
        scores=TwinScores(
            actual=0.41,
            ghost=0.63,
            components_actual={"T": 0.4, "P": 0.3, "F": 0.7, "R": 0.2},
            components_ghost={"T": 0.7, "P": 0.6, "F": 0.9, "R": 0.1},
        ),
    )


def _build_text(packet: EvidencePacket) -> OverlayText:
    return OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}, "
                    f"ghost score {packet.twin_ghost_score:.2f}."
                ),
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}, "
                    f"ghost score {packet.twin_ghost_score:.2f}."
                ),
            )
        },
    )


def _roster():
    from simulator.reference_data import build_players

    return build_players(7)


# ---------------------------------------------------------------------------
# player_name_map helper
# ---------------------------------------------------------------------------


def test_player_name_map_returns_id_to_name() -> None:
    roster = _roster()
    name_map = player_name_map(roster)
    assert isinstance(name_map, dict)
    assert len(name_map) == len(roster)
    for player in roster:
        assert player.player_id in name_map
        assert name_map[player.player_id] == player.name


def test_player_name_map_empty_roster() -> None:
    assert player_name_map([]) == {}


# ---------------------------------------------------------------------------
# build_overlay: basic structure
# ---------------------------------------------------------------------------


def test_build_overlay_returns_overlay_instance() -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert isinstance(overlay, Overlay)


def test_build_overlay_id_format() -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.overlay_id.startswith("ov_")
    assert len(overlay.overlay_id) == 11  # "ov_" + 8 hex chars


def test_build_overlay_display_duration_12() -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.display_duration_s == 12


def test_build_overlay_calculation_version_from_twin() -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.calculation_version == twin.version
    assert overlay.calculation_version == "twin-v1"


def test_build_overlay_match_clock_s() -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.match_clock_s == packet.moment_minute * 60


# ---------------------------------------------------------------------------
# build_overlay: moment type mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_type, expected",
    [
        ("high_pressure_final_third_pass", MomentType.GHOST_PASS),
        ("ghost_pass", MomentType.GHOST_PASS),
        ("goal", MomentType.GOAL),
        ("final_third_turnover", MomentType.TURNOVER),
        ("turnover", MomentType.TURNOVER),
        ("momentum_swing", MomentType.MOMENTUM_SWING),
        ("pressure_spell", MomentType.PRESSURE_SPELL),
    ],
)
def test_moment_type_mapping(raw_type: str, expected: MomentType) -> None:
    """All raw moment_type strings map to correct MomentType enum values."""
    # For non-ghost types, ghost_shown=False avoids geometry requirement
    ghost_shown = raw_type in ("high_pressure_final_third_pass", "ghost_pass")
    packet = _build_packet(moment_type=raw_type, ghost_shown=ghost_shown)
    twin = _build_twin(ghost_shown=ghost_shown)

    if ghost_shown:
        text = _build_text(packet)
    else:
        text = OverlayText(
            analyst={
                "en": NarrativeText(
                    headline=f"Moment at minute {packet.moment_minute}",
                    body=f"Match action at minute {packet.moment_minute}.",
                )
            },
            fan={
                "en": NarrativeText(
                    headline=f"Action at minute {packet.moment_minute}!",
                    body=f"Important moment at minute {packet.moment_minute}.",
                )
            },
        )

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.moment_type == expected


def test_unknown_moment_type_raises() -> None:
    from agents.overlay import _resolve_moment_type

    with pytest.raises(ValueError, match="Unknown moment_type"):
        _resolve_moment_type("totally_unknown_type")


# ---------------------------------------------------------------------------
# build_overlay: ghost_pass visual and scores
# ---------------------------------------------------------------------------


def test_ghost_pass_gets_visual_and_scores() -> None:
    """Ghost-pass overlays must carry visual geometry and twin scores from twin."""
    packet = _build_packet(moment_type="high_pressure_final_third_pass", ghost_shown=True)
    twin = _build_twin(ghost_shown=True)
    text = _build_text(packet)

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.visual is not None
    assert overlay.visual.actual is not None
    assert overlay.visual.ghost is not None
    assert overlay.scores is not None


def test_non_ghost_pass_has_no_visual() -> None:
    """Non-ghost-pass overlays must NOT carry visual geometry or scores."""
    for moment_type in ("goal", "final_third_turnover", "momentum_swing", "pressure_spell"):
        packet = _build_packet(moment_type=moment_type, ghost_shown=False)
        twin = _build_twin(ghost_shown=False)
        text = OverlayText(
            analyst={
                "en": NarrativeText(
                    headline=f"Moment at minute {packet.moment_minute}",
                    body=f"Match action at minute {packet.moment_minute}.",
                )
            },
            fan={
                "en": NarrativeText(
                    headline=f"Action at minute {packet.moment_minute}!",
                    body=f"Important moment at minute {packet.moment_minute}.",
                )
            },
        )
        overlay = build_overlay(
            packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
        )
        assert overlay.visual is None, f"Expected no visual for {moment_type}"
        assert overlay.scores is None, f"Expected no scores for {moment_type}"


def test_ghost_shown_false_no_visual() -> None:
    """ghost_pass moment type but ghost_shown=False → no visual/scores."""
    packet = _build_packet(moment_type="ghost_pass", ghost_shown=False)
    twin = _build_twin(ghost_shown=False)
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=f"Match action at minute {packet.moment_minute}.",
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Ghost pass at minute {packet.moment_minute}!",
                body=f"Important moment at minute {packet.moment_minute}.",
            )
        },
    )
    # ghost_shown=False → visual+scores are None → Overlay validator should reject ghost_pass
    with pytest.raises((ValueError, Exception)):
        build_overlay(
            packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
        )


# ---------------------------------------------------------------------------
# AT-06: evidence event_ids match packet event_ids
# ---------------------------------------------------------------------------


def test_evidence_event_ids_match_packet() -> None:
    """AT-06: evidence.event_ids must equal packet.event_ids exactly."""
    eids = ["ev_test001", "ev_test002", "ev_test003"]
    packet = _build_packet(event_ids=eids)
    twin = _build_twin()
    text = _build_text(packet)

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    assert overlay.evidence.event_ids == eids, (
        f"AT-06 fail: evidence.event_ids {overlay.evidence.event_ids!r} "
        f"!= packet.event_ids {eids!r}"
    )


# ---------------------------------------------------------------------------
# AT-07: evidence metrics values match packet values
# ---------------------------------------------------------------------------


def test_evidence_metrics_contain_key_packet_values() -> None:
    """AT-07: core packet numbers appear in evidence.metrics after rounding."""
    packet = _build_packet(actual_score=0.41, ghost_score=0.63, delta=0.22)
    twin = _build_twin()
    text = _build_text(packet)

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    m = overlay.evidence.metrics
    assert "twin_actual_score" in m
    assert "twin_ghost_score" in m
    assert "twin_delta" in m
    assert "pass_difficulty" in m
    assert abs(m["twin_actual_score"] - round(0.41, 3)) < 1e-9
    assert abs(m["twin_ghost_score"] - round(0.63, 3)) < 1e-9
    assert abs(m["twin_delta"] - round(0.22, 3)) < 1e-9


def test_evidence_metrics_include_momentum_and_pressure() -> None:
    """AT-07: live momentum and pressure values are included in metrics."""
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    m = overlay.evidence.metrics
    assert any(k.startswith("momentum_") for k in m), "No momentum keys in metrics"
    assert any(k.startswith("pressure_") for k in m), "No pressure keys in metrics"


# ---------------------------------------------------------------------------
# AT-09: validate_text passes on template-generated overlay text
# ---------------------------------------------------------------------------


def test_overlay_text_from_template_passes_validator() -> None:
    """AT-09: build_narrative output passes validate_text on ghost_pass packet."""
    roster = _roster()
    packet = _build_packet()
    twin = _build_twin()
    text = build_narrative(packet, roster)

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )

    errors = validate_text(overlay.text, packet, roster)
    assert errors == [], f"AT-09: validator errors on template overlay: {errors}"


# ---------------------------------------------------------------------------
# Schema round-trip: model_validate passes
# ---------------------------------------------------------------------------


def test_overlay_serialises_to_dict_and_back() -> None:
    """Overlay.model_dump() / model_validate() round-trip should succeed."""
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)

    overlay = build_overlay(
        packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
    )
    raw = overlay.model_dump()
    overlay2 = Overlay.model_validate(raw)
    assert overlay2.overlay_id == overlay.overlay_id
    assert overlay2.moment_type == overlay.moment_type


# ---------------------------------------------------------------------------
# narrative_source and validation_status fields are passed through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", [NarrativeSource.AGENT, NarrativeSource.TEMPLATE])
def test_narrative_source_passthrough(source: NarrativeSource) -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(packet, twin, text, source, ValidationStatus.PASSED)
    assert overlay.narrative_source == source


@pytest.mark.parametrize("status", [ValidationStatus.PASSED, ValidationStatus.FAILED])
def test_validation_status_passthrough(status: ValidationStatus) -> None:
    packet = _build_packet()
    twin = _build_twin()
    text = _build_text(packet)
    overlay = build_overlay(packet, twin, text, NarrativeSource.TEMPLATE, status)
    assert overlay.validation_status == status
