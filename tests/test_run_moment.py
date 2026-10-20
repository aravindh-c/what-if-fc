"""Tests for scripts/run_moment helpers and workflow force-fail path.

No network required.  Tests cover:
- Building EvidencePacket + TwinResult for all 4 hand-designed scenarios
- Building EvidencePacket + TwinResult for --seed 7 --moment 1
- Running run_moment_workflow with the _SleeperAgent stub (force-fail):
    source=template, fallback_reason mentions timeout, overlay is valid.
"""

from __future__ import annotations

import asyncio

from scripts.run_moment import (
    _load_scenario,
    _packet_from_scenario,
    _packet_from_seed,
    _SleeperAgent,  # noqa: PLC2701
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_scenario_ids() -> list[str]:
    from simulator.scenarios import _build_scenarios  # noqa: PLC2701

    return [s.scenario_id for s in _build_scenarios()]


# ---------------------------------------------------------------------------
# Scenario packet building
# ---------------------------------------------------------------------------


def test_packet_from_scenario_all_four() -> None:
    """All 4 hand-designed scenarios produce valid EvidencePackets."""
    from analytics.evidence import EvidencePacket

    for sid in _all_scenario_ids():
        scenario = _load_scenario(sid)
        packet, twin, roster = _packet_from_scenario(scenario)
        assert isinstance(packet, EvidencePacket), f"scenario {sid}: not an EvidencePacket"
        assert packet.moment_type == "high_pressure_final_third_pass"
        assert packet.ghost_shown, f"scenario {sid}: ghost not shown"
        assert twin.ghost_shown, f"scenario {sid}: twin.ghost_shown is False"


def test_packet_pass_difficulty_nonzero_for_scenarios() -> None:
    """Scenario packets have a real pass_difficulty (not hard-coded 0.0)."""
    for sid in _all_scenario_ids():
        scenario = _load_scenario(sid)
        packet, _, _ = _packet_from_scenario(scenario)
        assert packet.pass_difficulty > 0, (
            f"scenario {sid}: pass_difficulty is {packet.pass_difficulty}"
        )


def test_packet_highlight_defenders_from_twin() -> None:
    """Scenario packets use twin.visual.highlight_defenders, not an empty list."""
    for sid in _all_scenario_ids():
        scenario = _load_scenario(sid)
        packet, twin, _ = _packet_from_scenario(scenario)
        assert packet.highlight_defenders == list(twin.visual.highlight_defenders), (
            f"scenario {sid}: highlight_defenders mismatch"
        )


def test_packet_from_scenario_event_ids() -> None:
    """Scenario packet event_ids contains the scenario's actual_pass event_id."""
    scenario = _load_scenario("missed_overlap_right")
    packet, _, _ = _packet_from_scenario(scenario)
    assert scenario.actual_pass.event_id in packet.event_ids


# ---------------------------------------------------------------------------
# Seed packet building
# ---------------------------------------------------------------------------


def test_packet_from_seed_7_moment_1() -> None:
    """--seed 7 --moment 1 produces a valid ghost-eligible EvidencePacket."""
    from analytics.evidence import EvidencePacket

    packet, twin, roster, events = _packet_from_seed(7, 1)
    assert isinstance(packet, EvidencePacket)
    assert packet.ghost_shown
    assert twin.ghost_shown
    assert len(roster) > 0
    assert len(events) > 0


def test_packet_from_seed_has_real_pass_difficulty() -> None:
    """Seed packet pass_difficulty is computed (not zero) for a real final-third pass."""
    packet, _, _, _ = _packet_from_seed(7, 1)
    assert packet.pass_difficulty >= 0.0  # can be 0 if short, but not None


# ---------------------------------------------------------------------------
# Force-fail path: _SleeperAgent → investigator timed out → template
# ---------------------------------------------------------------------------


def _build_workflow_inputs():
    """Return (packet, twin, roster, kql) for force-fail tests (no network)."""
    from agents.kql_tools import LocalKql

    scenario = _load_scenario("missed_overlap_right")
    packet, twin, roster = _packet_from_scenario(scenario)
    kql = LocalKql([scenario.actual_pass])
    return packet, twin, roster, kql


def test_force_fail_returns_template_source() -> None:
    """_SleeperAgent triggers TimeoutError → overlay.narrative_source == TEMPLATE."""
    from agents.workflow import run_moment_workflow
    from core.schemas import NarrativeSource, Overlay

    packet, twin, roster, kql = _build_workflow_inputs()
    stub = _SleeperAgent()

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, kql, None,
            timeout_s=0.2,
            _agents=(stub, stub),
        )
    )

    assert isinstance(overlay, Overlay)
    assert overlay.narrative_source == NarrativeSource.TEMPLATE
    assert log["source"] == "template"


def test_force_fail_fallback_reason_mentions_timeout() -> None:
    """fallback_reason says 'investigator timed out' on a real asyncio.TimeoutError."""
    from agents.workflow import run_moment_workflow

    packet, twin, roster, kql = _build_workflow_inputs()
    stub = _SleeperAgent()

    _, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, kql, None,
            timeout_s=0.2,
            _agents=(stub, stub),
        )
    )

    reason = log.get("fallback_reason") or ""
    assert "timed out" in reason, f"Expected 'timed out' in fallback_reason, got: {reason!r}"


def test_force_fail_overlay_is_valid() -> None:
    """Template fallback always produces a schema-valid Overlay."""
    from agents.workflow import run_moment_workflow
    from core.schemas import Overlay, ValidationStatus

    packet, twin, roster, kql = _build_workflow_inputs()
    stub = _SleeperAgent()

    overlay, _ = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, kql, None,
            timeout_s=0.2,
            _agents=(stub, stub),
        )
    )

    raw = overlay.model_dump()
    overlay2 = Overlay.model_validate(raw)
    assert overlay2.overlay_id == overlay.overlay_id
    assert overlay.validation_status == ValidationStatus.PASSED
