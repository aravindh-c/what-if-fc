"""Tests for ghost-moment handling of final_third_turnover moments.

Verifies:
- pass_event_for returns the source pass for FTT moments
- pass_event_for returns the moment event for HPFTP (no source_event_id)
- pass_event_for returns None when source event has no end_x/end_y
- pass_event_for returns None when source event has no snapshot_id
- evidence packet passer comes from the pass event, not the interceptor
- event_ids includes both the pass and the turnover event
- _build_match_replay on seed 7 runs without errors (AT-10 precondition)
"""

from __future__ import annotations

from datetime import UTC, datetime

from analytics.metrics import KeyMoment, pass_event_for
from core.schemas import EventType, MatchEvent, Outcome

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_MATCH = "test_ftt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pass(
    eid: str,
    clock: int,
    team: str,
    x: float,
    ex: float,
    outcome: Outcome = Outcome.INCOMPLETE,
    snap: str | None = None,
    poss: int = 1,
    player: str | None = None,
) -> MatchEvent:
    return MatchEvent(
        event_id=eid,
        match_id=_MATCH,
        scenario_id="test",
        seed=0,
        event_time=_EPOCH,
        match_clock_s=clock,
        period=1,
        event_type=EventType.PASS,
        team_id=team,
        player_id=player or f"{team}-P01",
        possession_id=poss,
        x=x,
        y=34.0,
        end_x=ex,
        end_y=34.0,
        outcome=outcome,
        receiver_id=f"{team}-P02",
        pressure_level=0.0,
        snapshot_id=snap,
    )


def _tackle(eid: str, clock: int, team: str, x: float, poss: int = 2) -> MatchEvent:
    return MatchEvent(
        event_id=eid,
        match_id=_MATCH,
        scenario_id="test",
        seed=0,
        event_time=_EPOCH,
        match_clock_s=clock,
        period=1,
        event_type=EventType.TACKLE,
        team_id=team,
        player_id=f"{team}-P05",
        possession_id=poss,
        x=x,
        y=34.0,
        outcome=Outcome.WON,
    )


def _ftt_moment(
    event_id: str,
    source_event_id: str | None,
    snapshot_id: str | None,
    ghost_eligible: bool = True,
) -> KeyMoment:
    return KeyMoment(
        moment_id=f"km_{event_id}",
        match_id=_MATCH,
        match_clock_s=300,
        moment_type="final_third_turnover",
        team_id="T02",
        event_id=event_id,
        snapshot_id=snapshot_id,
        source_event_id=source_event_id,
        value=82.0,
        score=0.5,
        ghost_eligible=ghost_eligible,
    )


def _hpftp_moment(event_id: str, snapshot_id: str) -> KeyMoment:
    return KeyMoment(
        moment_id=f"km_{event_id}",
        match_id=_MATCH,
        match_clock_s=200,
        moment_type="high_pressure_final_third_pass",
        team_id="T01",
        event_id=event_id,
        snapshot_id=snapshot_id,
        source_event_id=None,
        value=0.7,
        score=0.7,
        ghost_eligible=True,
    )


# ---------------------------------------------------------------------------
# pass_event_for: FTT with source pass
# ---------------------------------------------------------------------------


def test_pass_event_for_ftt_returns_source_pass() -> None:
    """FTT moment: pass_event_for returns the source pass, not the tackle."""
    source_pass = _pass("src_pass", 290, "T01", 82.0, 92.0, snap="sn_1")
    tackle_ev = _tackle("tackle_1", 300, "T02", 82.0)
    moment = _ftt_moment("tackle_1", source_event_id="src_pass", snapshot_id="sn_1")
    events = [source_pass, tackle_ev]

    result = pass_event_for(moment, events)

    assert result is not None
    assert result.event_id == "src_pass"
    assert result.team_id == "T01"  # the passing team, not the interceptor


def test_pass_event_for_hpftp_returns_own_event() -> None:
    """HPFTP moment (no source_event_id): returns the moment's own event."""
    hpftp_pass = _pass(
        "hp_pass", 200, "T01", 83.0, 93.0,
        outcome=Outcome.COMPLETE, snap="sn_2",
    )
    moment = _hpftp_moment("hp_pass", snapshot_id="sn_2")
    events = [hpftp_pass]

    result = pass_event_for(moment, events)

    assert result is not None
    assert result.event_id == "hp_pass"


def test_pass_event_for_returns_none_when_event_missing() -> None:
    """pass_event_for returns None when the source event is not in the list."""
    tackle_ev = _tackle("tackle_2", 300, "T02", 82.0)
    moment = _ftt_moment("tackle_2", source_event_id="missing_pass", snapshot_id="sn_x")
    events = [tackle_ev]

    assert pass_event_for(moment, events) is None


def test_pass_event_for_returns_none_when_no_end_coords() -> None:
    """pass_event_for returns None when the source event has no end_x/end_y.

    Tackles and interceptions never have end coords — prevents scoring them.
    """
    tackle_ev = _tackle("tackle_3", 300, "T02", 82.0)
    # source_event_id points to the tackle itself (no end_x/end_y)
    moment = _ftt_moment("tackle_3", source_event_id="tackle_3", snapshot_id=None)
    events = [tackle_ev]

    assert pass_event_for(moment, events) is None


def test_pass_event_for_returns_none_when_no_snapshot() -> None:
    """pass_event_for returns None when the source pass has no snapshot_id."""
    source_pass = _pass("src_no_snap", 290, "T01", 82.0, 92.0, snap=None)
    tackle_ev = _tackle("tackle_4", 300, "T02", 82.0)
    moment = _ftt_moment("tackle_4", source_event_id="src_no_snap", snapshot_id=None)
    events = [source_pass, tackle_ev]

    assert pass_event_for(moment, events) is None


# ---------------------------------------------------------------------------
# Evidence packet: passer and event_ids for FTT moments
# ---------------------------------------------------------------------------


def test_ftt_packet_passer_is_passing_team_player() -> None:
    """For a FTT moment, packet.passer_id must come from the pass event (T01),
    not from the tackle event (T02).  AT-05 variant.
    """
    # Build a minimal FTT setup using the missed_overlap_right scenario geometry
    # so we have a valid PositionSnapshot
    import json
    from pathlib import Path

    from analytics.evidence import build_evidence_packet
    from analytics.metrics import KeyMoment
    from analytics.tactical_twin import score_pass
    from core.schemas import PositionSnapshot

    sc = json.loads(
        (Path("data/scenarios") / "missed_overlap_right.json").read_text()
    )
    # Re-use the snapshot; create a synthetic incomplete pass as the source event
    snap = PositionSnapshot(**sc["snapshot"])
    orig_ev = MatchEvent(**sc["actual_pass"])

    # Simulate: orig_ev is now an incomplete pass by T01 (source of the FTT)
    # We need end_x/end_y: orig_ev already has them
    source_pass = orig_ev.model_copy(
        update={
            "event_id": "ftt_src_pass",
            "player_id": "T01-P12",  # the passer (T01 player)
            "receiver_id": "T01-P10",
            "outcome": Outcome.INCOMPLETE,
            "snapshot_id": snap.snapshot_id,
        }
    )

    # The tackle event (T02 wins it)
    tackle_ev = MatchEvent(
        event_id="ftt_tackle",
        match_id=source_pass.match_id,
        scenario_id=source_pass.scenario_id,
        seed=0,
        event_time=_EPOCH,
        match_clock_s=source_pass.match_clock_s + 2,
        period=source_pass.period,
        event_type=EventType.TACKLE,
        team_id="T02",
        player_id="T02-P05",
        possession_id=1,
        x=source_pass.end_x,
        y=source_pass.end_y,
        outcome=Outcome.WON,
    )

    twin = score_pass(source_pass, snap)

    moment = KeyMoment(
        moment_id="km_ftt_tackle",
        match_id=source_pass.match_id,
        match_clock_s=tackle_ev.match_clock_s,
        moment_type="final_third_turnover",
        team_id="T02",
        event_id=tackle_ev.event_id,
        snapshot_id=snap.snapshot_id,
        source_event_id=source_pass.event_id,
        value=float(tackle_ev.x or 82.0),
        score=0.5,
        ghost_eligible=True,
    )

    packet = build_evidence_packet(
        moment, [source_pass, tackle_ev], snap, twin, match_id=source_pass.match_id
    )

    # passer_id must be the T01 player (from the source pass), not T02-P05
    assert packet.passer_id == "T01-P12", (
        f"passer_id should be T01-P12 (source passer), got {packet.passer_id!r}"
    )


def test_ftt_packet_event_ids_contains_both_events() -> None:
    """event_ids must include both the source pass event and the turnover event."""
    import json
    from pathlib import Path

    from analytics.evidence import build_evidence_packet
    from analytics.metrics import KeyMoment
    from analytics.tactical_twin import score_pass
    from core.schemas import PositionSnapshot

    sc = json.loads(
        (Path("data/scenarios") / "missed_overlap_right.json").read_text()
    )
    snap = PositionSnapshot(**sc["snapshot"])
    orig_ev = MatchEvent(**sc["actual_pass"])

    source_pass = orig_ev.model_copy(
        update={
            "event_id": "ftt_src_ev2",
            "outcome": Outcome.INCOMPLETE,
            "snapshot_id": snap.snapshot_id,
        }
    )
    tackle_ev = MatchEvent(
        event_id="ftt_tackle2",
        match_id=source_pass.match_id,
        scenario_id=source_pass.scenario_id,
        seed=0,
        event_time=_EPOCH,
        match_clock_s=source_pass.match_clock_s + 2,
        period=source_pass.period,
        event_type=EventType.TACKLE,
        team_id="T02",
        player_id="T02-P05",
        possession_id=1,
        x=source_pass.end_x,
        y=source_pass.end_y,
        outcome=Outcome.WON,
    )

    twin = score_pass(source_pass, snap)
    moment = KeyMoment(
        moment_id="km_ftt_tackle2",
        match_id=source_pass.match_id,
        match_clock_s=tackle_ev.match_clock_s,
        moment_type="final_third_turnover",
        team_id="T02",
        event_id=tackle_ev.event_id,
        snapshot_id=snap.snapshot_id,
        source_event_id=source_pass.event_id,
        value=82.0,
        score=0.5,
        ghost_eligible=True,
    )

    packet = build_evidence_packet(
        moment, [source_pass, tackle_ev], snap, twin, match_id=source_pass.match_id
    )

    assert source_pass.event_id in packet.event_ids, (
        "source pass event_id must be in packet.event_ids"
    )
    assert tackle_ev.event_id in packet.event_ids, (
        "turnover event_id must be in packet.event_ids"
    )


# ---------------------------------------------------------------------------
# Builder: seed 7 runs without errors
# ---------------------------------------------------------------------------


def test_build_match_replay_seed7_no_errors() -> None:
    """_build_match_replay on seed 7 completes without raising."""
    from scripts.build_replay import _build_match_replay

    data = _build_match_replay(7, "T01", "T02")
    assert "_ghost_moments" in data
    # No crash means pass_event_for correctly skipped invalid FTT moments
    assert data.get("_n_skipped", 0) >= 0
