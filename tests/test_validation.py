"""Tests for analytics.validation – overlay text validator.

AT-06: event_id integrity
AT-07: numeric integrity
AT-09: analyst/fan persona consistency
"""

from __future__ import annotations

import pytest

from analytics.validation import validate_text
from core.schemas import NarrativeText, OverlayText

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _build_packet(
    moment_minute: int = 35,
    actual_score: float = 0.41,
    ghost_score: float = 0.63,
    delta: float = 0.22,
    pass_difficulty: float = 28.5,
    scoreline: dict | None = None,
    event_ids: list[str] | None = None,
    passer_id: str | None = "T01-P12",
    ghost_player_id: str | None = "T01-P08",
    ghost_pass_length: float | None = 31.2,
    ghost_nearest_def: float | None = 8.3,
):
    """Build a minimal EvidencePacket for testing (uses pydantic directly)."""
    from analytics.evidence import EvidencePacket, LiveMetrics

    sl = scoreline or {"T01": 0, "T02": 0}
    eids = event_ids or ["ev_test001"]

    live = LiveMetrics(
        minute=moment_minute,
        momentum_share={"T01": 0.55, "T02": 0.45},
        pressure_index={"T01": 1.2, "T02": 0.8},
        scoreline=sl,
    )
    return EvidencePacket(
        match_id="match_test",
        moment_type="ghost_pass",
        moment_minute=moment_minute,
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
        pass_difficulty=pass_difficulty,
        ghost_shown=True,
        formula_version="twin-v1",
        label="Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.",
        passer_id=passer_id,
        actual_receiver_id="T01-P10",
        highlight_defenders=["T02-P03"],
        actual_pass_length_m=18.5,
        ghost_pass_length_m=ghost_pass_length,
        actual_nearest_defender_m=3.1,
        ghost_nearest_defender_m=ghost_nearest_def,
    )


def _good_overlay_text(packet) -> OverlayText:
    """Build an OverlayText that should pass all checks."""
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
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )


def _roster():
    from simulator.reference_data import build_players

    return build_players(7)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_text_passes() -> None:
    """AT-07, AT-09: a correctly constructed overlay text has no errors."""
    packet = _build_packet()
    text = _good_overlay_text(packet)
    errors = validate_text(text, packet, _roster())
    assert errors == [], errors


# ---------------------------------------------------------------------------
# Banned terms (AT-07 / NFR-08)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "banned",
    ["xG", "xA", "xT", "expected goals", "expected assists",
     "probability", "% chance"],
)
def test_banned_term_fails(banned: str) -> None:
    packet = _build_packet()
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=f"Actual score {packet.twin_actual_score:.2f} ({banned}).",
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert any("banned term" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Invented number (AT-07)
# ---------------------------------------------------------------------------


def test_invented_number_fails() -> None:
    """AT-07: a number not in the packet triggers a numeric-integrity error."""
    packet = _build_packet()
    invented = 73.7  # not in any packet field
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Option score {packet.twin_actual_score:.2f} vs {invented}."
                ),
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert any("73.7" in e or "AT-07" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Wrong player name
# ---------------------------------------------------------------------------


def test_wrong_player_name_fails() -> None:
    """Names not in the fictional roster must be rejected."""
    packet = _build_packet()
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Lionel Messi scored {packet.twin_actual_score:.2f}."
                ),
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert any("not found in roster" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Long body (schema check, not just validator)
# ---------------------------------------------------------------------------


def test_long_body_rejected_by_schema() -> None:
    """NarrativeText.body max_length=280 must be enforced by pydantic."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        NarrativeText(headline="OK", body="x" * 300)


def test_long_headline_rejected_by_schema() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        NarrativeText(headline="H" * 81, body="body")


def test_validator_catches_bypassed_long_body() -> None:
    """AT-07: validate_text itself also checks lengths when schema is bypassed."""
    packet = _build_packet()
    # Bypass pydantic to inject a too-long body
    analyst_nt = NarrativeText.model_construct(
        headline=f"Ghost Pass at minute {packet.moment_minute}",
        body="x " * 150,  # 300 chars
    )
    fan_nt = NarrativeText(
        headline=f"Free player at minute {packet.moment_minute}!",
        body=f"Better option scored {packet.twin_ghost_score:.2f}.",
    )
    text = OverlayText.model_construct(
        analyst={"en": analyst_nt},
        fan={"en": fan_nt},
        cue=None,
    )
    errors = validate_text(text, packet, _roster())
    assert any("too long" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Event ID integrity (AT-06)
# ---------------------------------------------------------------------------


def test_invalid_event_id_fails() -> None:
    """AT-06: an event_id in text not present in packet.event_ids is flagged."""
    packet = _build_packet(event_ids=["ev_real001"])
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"See event ev_fake999. "
                    f"Actual score {packet.twin_actual_score:.2f}."
                ),
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert any("ev_fake999" in e and "AT-06" in e for e in errors), errors


def test_valid_event_id_passes() -> None:
    """AT-06: mentioning a packet event_id in text should not fail."""
    packet = _build_packet(event_ids=["ev_test001", "ev_test002"])
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"See ev_test001. "
                    f"Actual score {packet.twin_actual_score:.2f}."
                ),
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert not any("AT-06" in e for e in errors), errors


# ---------------------------------------------------------------------------
# Fan numbers ⊆ analyst numbers (AT-09)
# ---------------------------------------------------------------------------


def test_fan_number_not_in_analyst_fails() -> None:
    """AT-09: a number in fan text but absent from analyst text is an error."""
    packet = _build_packet()
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=f"Actual score {packet.twin_actual_score:.2f}.",
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                # ghost_score is in packet but NOT in analyst body/headline
                body=f"Better option scored {packet.twin_ghost_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert any("AT-09" in e for e in errors), errors


def test_fan_same_numbers_as_analyst_passes() -> None:
    """AT-09: fan text is exactly the analyst numbers → should pass."""
    packet = _build_packet()
    body = (
        f"Actual score {packet.twin_actual_score:.2f}, "
        f"ghost score {packet.twin_ghost_score:.2f}."
    )
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=body,
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=body,
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    at09_errors = [e for e in errors if "AT-09" in e]
    assert not at09_errors, at09_errors


# ---------------------------------------------------------------------------
# Regression tests for tightened validator
# ---------------------------------------------------------------------------


def _both_scores_fan(packet) -> NarrativeText:
    return NarrativeText(
        headline=f"Free player at minute {packet.moment_minute}!",
        body=(
            f"Actual score {packet.twin_actual_score:.2f}, "
            f"ghost score {packet.twin_ghost_score:.2f}."
        ),
    )


def test_next_does_not_trigger_banned_xt() -> None:
    """'next', 'extra', 'text', 'exactly' must NOT trigger the xT ban."""
    packet = _build_packet()
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}. "
                    "The next pass should go wide."
                ),
            )
        },
        fan={"en": _both_scores_fan(packet)},
    )
    errors = validate_text(text, packet, _roster())
    assert not any("banned" in e for e in errors), errors


def test_sentence_initial_caps_not_flagged() -> None:
    """Capitalised words starting sentences must never be treated as names."""
    packet = _build_packet()
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}, "
                    f"ghost score {packet.twin_ghost_score:.2f}. "
                    "Meanwhile the winger stood unmarked. Brilliant space."
                ),
            )
        },
        fan={"en": _both_scores_fan(packet)},
    )
    errors = validate_text(text, packet, _roster())
    name_errors = [e for e in errors if "not found in roster" in e or "capitalised" in e]
    assert not name_errors, name_errors


def test_invented_decimal_fails_precision_check() -> None:
    """A decimal with no matching packet value at its own dp must fail AT-07."""
    from analytics.evidence import EvidencePacket, LiveMetrics

    live = LiveMetrics(
        minute=35,
        momentum_share={"T01": 0.55, "T02": 0.45},
        pressure_index={"T01": 1.2, "T02": 0.8},
        scoreline={"T01": 0, "T02": 0},
    )
    # No packet value rounds to 0.4 at 1 dp: components avoid 0.4, scores are 0.63/0.71
    packet = EvidencePacket(
        match_id="match_test",
        moment_type="ghost_pass",
        moment_minute=35,
        moment_score=0.7,
        event_ids=["ev_test001"],
        live_metrics=live,
        twin_version="twin-v1",
        twin_weights={"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15},
        twin_delta=0.08,
        twin_actual_score=0.63,
        twin_ghost_score=0.71,
        twin_ghost_player_id="T01-P08",
        twin_components_actual={"T": 0.5, "P": 0.3, "F": 0.7, "R": 0.2},
        twin_components_ghost={"T": 0.7, "P": 0.6, "F": 0.9, "R": 0.1},
        pass_difficulty=28.5,
        ghost_shown=True,
        formula_version="twin-v1",
        label="Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.",
        passer_id="T01-P12",
        actual_receiver_id="T01-P10",
        highlight_defenders=["T02-P03"],
        actual_pass_length_m=18.5,
        ghost_pass_length_m=31.2,
        actual_nearest_defender_m=3.1,
        ghost_nearest_defender_m=8.3,
    )
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}. "
                    "Option delta is 0.4."
                ),
            )
        },
        fan={
            "en": NarrativeText(
                headline=f"Free player at minute {packet.moment_minute}!",
                body=f"Option score {packet.twin_actual_score:.2f}.",
            )
        },
    )
    errors = validate_text(text, packet, _roster())
    assert any("0.4" in e or "AT-07" in e for e in errors), errors


def test_percentage_passes_when_share_matches() -> None:
    """'55%' must pass when a momentum share is 0.55 (0.55 × 100 = 55)."""
    packet = _build_packet()  # momentum_share T01=0.55
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}. "
                    "Dominant team holds 55% of momentum."
                ),
            )
        },
        fan={"en": _both_scores_fan(packet)},
    )
    errors = validate_text(text, packet, _roster())
    at07_errors = [e for e in errors if "AT-07" in e]
    assert not at07_errors, at07_errors


def test_forbidden_roster_player_fails() -> None:
    """Mentioning a real roster player not in the moment must be flagged."""
    roster = _roster()
    packet = _build_packet(passer_id=roster[0].player_id, ghost_player_id=None)
    # Use a player who is NOT the passer/receiver/ghost/defender
    forbidden = next(
        p for p in roster
        if p.player_id not in {
            packet.passer_id,
            packet.actual_receiver_id,
            packet.twin_ghost_player_id,
            *packet.highlight_defenders,
        }
    )
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}. "
                    f"{forbidden.name} was involved."
                ),
            )
        },
        fan={"en": _both_scores_fan(packet)},
    )
    errors = validate_text(text, packet, roster)
    assert any("not in this moment" in e for e in errors), errors


def test_invented_name_mid_sentence_fails() -> None:
    """A capitalized name mid-sentence that is not in the roster must fail."""
    packet = _build_packet()
    text = OverlayText(
        analyst={
            "en": NarrativeText(
                headline=f"Ghost Pass at minute {packet.moment_minute}",
                body=(
                    f"Actual score {packet.twin_actual_score:.2f}. "
                    "The pass was played to Marco Bellini."
                ),
            )
        },
        fan={"en": _both_scores_fan(packet)},
    )
    errors = validate_text(text, packet, _roster())
    assert any("not found in roster" in e for e in errors), errors
