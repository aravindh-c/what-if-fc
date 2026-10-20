"""Build Overlay objects from evidence packets and twin results.

Roster lookup helper: player_name_map() returns {player_id: name} for use
by callers; it does not change EvidencePacket fields.
"""

from __future__ import annotations

import uuid

from core.schemas import (
    Evidence,
    MomentType,
    NarrativeSource,
    Overlay,
    OverlayText,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Moment-type mapping
# ---------------------------------------------------------------------------

_MOMENT_TYPE_MAP: dict[str, MomentType] = {
    # From analytics.metrics.key_moments() moment_type strings
    "goal": MomentType.GOAL,
    "high_pressure_final_third_pass": MomentType.GHOST_PASS,
    "final_third_turnover": MomentType.TURNOVER,
    "momentum_swing": MomentType.MOMENTUM_SWING,
    # Direct MomentType string values (if packet already uses them)
    "ghost_pass": MomentType.GHOST_PASS,
    "turnover": MomentType.TURNOVER,
    "pressure_spell": MomentType.PRESSURE_SPELL,
}


def _resolve_moment_type(raw: str) -> MomentType:
    try:
        return _MOMENT_TYPE_MAP[raw]
    except KeyError:
        raise ValueError(f"Unknown moment_type {raw!r}") from None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def player_name_map(roster: list) -> dict[str, str]:
    """Return {player_id: full_name} from a roster list.

    Does NOT modify EvidencePacket; callers use this for narrative rendering
    or logging without adding new fields to the packet schema.
    """
    return {p.player_id: p.name for p in roster}


def _build_metrics(packet) -> dict[str, float]:
    """Flatten key packet metrics into the Evidence.metrics dict."""
    metrics: dict[str, float] = {
        "twin_actual_score": round(packet.twin_actual_score, 3),
        "twin_ghost_score": round(packet.twin_ghost_score, 3),
        "twin_delta": round(packet.twin_delta, 3),
        "pass_difficulty": round(packet.pass_difficulty, 1),
    }
    for tid, share in packet.live_metrics.momentum_share.items():
        metrics[f"momentum_{tid}"] = round(share, 3)
    for tid, pres in packet.live_metrics.pressure_index.items():
        metrics[f"pressure_{tid}"] = round(pres, 3)
    return metrics


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_overlay(
    packet,
    twin,
    text: OverlayText,
    narrative_source: NarrativeSource,
    validation_status: ValidationStatus,
) -> Overlay:
    """Build a validated Overlay from an evidence packet and twin result.

    Parameters
    ----------
    packet:
        EvidencePacket for the moment.
    twin:
        TwinResult from analytics.tactical_twin.score_pass.
    text:
        OverlayText (from an agent or build_narrative fallback).
    narrative_source:
        NarrativeSource.AGENT or NarrativeSource.TEMPLATE.
    validation_status:
        ValidationStatus.PASSED or ValidationStatus.FAILED.

    Returns
    -------
    Overlay
        Schema-validated overlay ready for the API.
    """
    moment_type = _resolve_moment_type(packet.moment_type)

    # Ghost-pass moments expose visual geometry and twin scores; others do not.
    if moment_type == MomentType.GHOST_PASS and packet.ghost_shown:
        visual = twin.visual
        scores = twin.scores
    else:
        visual = None
        scores = None

    return Overlay(
        overlay_id=f"ov_{uuid.uuid4().hex[:8]}",
        match_id=packet.match_id,
        match_clock_s=packet.moment_minute * 60,
        display_duration_s=12,
        moment_type=moment_type,
        calculation_version=twin.version,
        validation_status=validation_status,
        narrative_source=narrative_source,
        visual=visual,
        scores=scores,
        evidence=Evidence(
            event_ids=packet.event_ids,
            metrics=_build_metrics(packet),
        ),
        text=text,
    )
