"""Tests for agents.workflow – run_moment_workflow with fake agents.

No network required: agents are mocked via _agents= injection.

AT-08: timeout → template fallback
Retry:  malformed output / validation fail → retry or template
AT-06/07/09: validated numbers and event IDs on agent output
Overlay: always a valid Overlay instance
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from agents.workflow import (
    Claim,
    DirectorText,
    Findings,
    run_moment_workflow,
)
from analytics.evidence import EvidencePacket, LiveMetrics
from analytics.tactical_twin import TwinResult
from analytics.validation import validate_text
from core.schemas import (
    NarrativeSource,
    Overlay,
    OverlayVisual,
    PassLine,
    TwinScores,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _build_packet() -> EvidencePacket:
    live = LiveMetrics(
        minute=34,
        momentum_share={"T01": 0.55, "T02": 0.45},
        pressure_index={"T01": 1.2, "T02": 0.8},
        scoreline={"T01": 0, "T02": 0},
    )
    return EvidencePacket(
        match_id="match_wf_test",
        moment_type="high_pressure_final_third_pass",
        moment_minute=34,
        moment_score=0.7,
        event_ids=["ev_wf001", "ev_wf002"],
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
        label="Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.",
        passer_id="T01-P07",
        actual_receiver_id="T01-P10",
        highlight_defenders=["T02-P03"],
        actual_pass_length_m=18.5,
        ghost_pass_length_m=31.2,
        actual_nearest_defender_m=3.1,
        ghost_nearest_defender_m=8.3,
    )


def _build_twin() -> TwinResult:
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
    return TwinResult(
        version="twin-v1",
        weights={"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15},
        candidates=[],
        actual_player_id="T01-P10",
        best_alt_player_id="T01-P08",
        delta=0.22,
        ghost_shown=True,
        visual=visual,
        scores=TwinScores(
            actual=0.41,
            ghost=0.63,
            components_actual={"T": 0.4, "P": 0.3, "F": 0.7, "R": 0.2},
            components_ghost={"T": 0.7, "P": 0.6, "F": 0.9, "R": 0.1},
        ),
    )


def _build_roster():
    from simulator.reference_data import build_players

    return build_players(7)


def _good_findings() -> Findings:
    return Findings(
        claims=[
            Claim(
                text="The pass at minute 34 was the key event.",
                evidence_fields=["moment_minute", "twin_delta"],
                event_ids=["ev_wf001"],
            )
        ]
    )


def _good_director_text(packet: EvidencePacket) -> DirectorText:
    """DirectorText whose numbers all come from the packet → passes validation."""
    return DirectorText(
        analyst_headline=f"Ghost Pass at minute {packet.moment_minute}",
        analyst_body=(
            f"Actual tactical option score {packet.twin_actual_score:.2f}, "
            f"ghost {packet.twin_ghost_score:.2f}."
        ),
        fan_headline=f"Free player at minute {packet.moment_minute}!",
        fan_body=f"Option score {packet.twin_actual_score:.2f}.",
    )


def _bad_director_text() -> DirectorText:
    """DirectorText with a banned term → fails validation."""
    return DirectorText(
        analyst_headline="xG analysis at minute 34",
        analyst_body="The xG value suggests a high-quality chance.",
        fan_headline="Wow!",
        fan_body="Amazing moment at minute 34.",
    )


class _FakeResp:
    """Fake agent response with a .value property."""

    def __init__(self, val):
        self.value = val
        self.text = str(val)


def _mock_agent(responses: list) -> MagicMock:
    """Create a mock agent whose run() returns the given responses in sequence."""
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=[_FakeResp(r) for r in responses])
    return agent


def _null_kql() -> MagicMock:
    kql = MagicMock()
    kql.match_stats.return_value = {}
    kql.momentum_at.return_value = {}
    kql.pressure_at.return_value = {}
    kql.recent_events.return_value = []
    return kql


# ---------------------------------------------------------------------------
# AT-08: timeout → template fallback
# ---------------------------------------------------------------------------


def test_investigator_timeout_falls_back_to_template() -> None:
    """AT-08: investigator timeout → overlay from template."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = MagicMock()
    investigator.run = AsyncMock(side_effect=TimeoutError())
    director = _mock_agent([_good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert isinstance(overlay, Overlay)
    assert overlay.narrative_source == NarrativeSource.TEMPLATE
    assert log["source"] == "template"
    assert "investigator timed out" in (log["fallback_reason"] or "")


def test_director_timeout_falls_back_to_template() -> None:
    """AT-08: director timeout on attempt 1 → template fallback."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = MagicMock()
    director.run = AsyncMock(side_effect=TimeoutError())

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.TEMPLATE
    assert "director timed out" in (log["fallback_reason"] or "")


# ---------------------------------------------------------------------------
# Malformed / None output → fallback
# ---------------------------------------------------------------------------


def test_investigator_none_output_falls_back() -> None:
    """Investigator returning value=None → template fallback."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([None])
    director = _mock_agent([_good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.TEMPLATE
    assert "no structured output" in (log["fallback_reason"] or "")


def test_director_none_output_falls_back() -> None:
    """Director returning value=None → template fallback."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([None])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.TEMPLATE


# ---------------------------------------------------------------------------
# Retry: validation error on attempt 1, fixed on attempt 2 → agent source
# ---------------------------------------------------------------------------


def test_retry_succeeds_on_attempt_2() -> None:
    """Validation error on attempt 1, fixed on attempt 2 → agent overlay, 2 attempts."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([_bad_director_text(), _good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.AGENT
    assert log["source"] == "agent"
    assert log["attempts"] == 2
    assert log["errors_attempt1"]  # errors were present on attempt 1


def test_retry_exhausted_falls_back_to_template() -> None:
    """Both director attempts fail validation → template fallback."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([_bad_director_text(), _bad_director_text()])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.TEMPLATE
    assert log["attempts"] == 2
    assert log["errors_attempt1"]
    assert log["errors_attempt2"]
    assert "validation failed after 2 attempts" in (log["fallback_reason"] or "")


# ---------------------------------------------------------------------------
# AT-06/07/09: validated agent output
# ---------------------------------------------------------------------------


def test_agent_output_passes_at06_at07_at09() -> None:
    """AT-06/07/09: agent-source overlay text passes validate_text."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([_good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.AGENT, f"log: {log}"
    errors = validate_text(overlay.text, packet, roster)
    assert errors == [], f"AT-06/07/09 errors on agent overlay: {errors}"


def test_agent_attempt_1_passes_validation() -> None:
    """Happy path: attempt 1 passes → agent source with 1 attempt."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([_good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert log["attempts"] == 1
    assert log["source"] == "agent"
    assert not log["errors_attempt1"]


# ---------------------------------------------------------------------------
# Overlay always valid
# ---------------------------------------------------------------------------


def test_overlay_is_always_valid_on_timeout() -> None:
    """Regardless of agent failure, run_moment_workflow returns a valid Overlay."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = MagicMock()
    investigator.run = AsyncMock(side_effect=RuntimeError("boom"))
    director = _mock_agent([])

    overlay, _ = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert isinstance(overlay, Overlay)
    assert overlay.validation_status == ValidationStatus.PASSED


def test_length_error_on_attempt1_retried_not_template() -> None:
    """Schema length error on attempt 1 triggers retry; agent succeeds on attempt 2."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    long_body = "A" * 290  # 290 chars > 280 limit
    long_dt = DirectorText(
        analyst_headline="Ghost Pass at minute 34",
        analyst_body=long_body,
        fan_headline="Free!",
        fan_body="Option score.",
    )

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([long_dt, _good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert overlay.narrative_source == NarrativeSource.AGENT
    assert log["source"] == "agent"
    assert log["attempts"] == 2
    assert any("analyst body" in e for e in log["errors_attempt1"]), (
        f"Expected length error in errors_attempt1, got: {log['errors_attempt1']}"
    )


def test_overlay_valid_schema_after_template_fallback() -> None:
    """Template fallback produces an Overlay that round-trips model_validate."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([None])
    director = _mock_agent([None])

    overlay, _ = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    raw = overlay.model_dump()
    overlay2 = Overlay.model_validate(raw)
    assert overlay2.overlay_id == overlay.overlay_id


# ---------------------------------------------------------------------------
# WorkflowBuilder graph tests
# ---------------------------------------------------------------------------


def test_retry_visits_director_twice() -> None:
    """Validation fail on attempt 1 causes Director to be called twice."""
    packet = _build_packet()
    twin = _build_twin()
    roster = _build_roster()

    investigator = _mock_agent([_good_findings()])
    director = _mock_agent([_bad_director_text(), _good_director_text(packet)])

    overlay, log = asyncio.run(
        run_moment_workflow(
            packet, twin, roster, _null_kql(), None,
            _agents=(investigator, director),
        )
    )
    assert director.run.call_count == 2
    assert overlay.narrative_source == NarrativeSource.AGENT
    assert log["attempts"] == 2


def test_graph_has_five_executors() -> None:
    """WorkflowBuilder graph contains the five expected executor nodes."""
    from agent_framework import WorkflowViz  # noqa: PLC0415

    from agents.workflow import _build_workflow  # noqa: PLC0415

    workflow = _build_workflow(client=None, kql=None, timeout_s=1.0)
    mermaid = WorkflowViz(workflow).to_mermaid()
    for exe_id in ("investigator", "director", "validator", "overlay", "template"):
        assert exe_id in mermaid, f"Executor {exe_id!r} not found in workflow diagram"
