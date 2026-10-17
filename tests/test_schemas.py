"""AT-02 (schema validation) plus contract checks for snapshots and overlays."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.schemas import MatchEvent, Overlay, PositionSnapshot
from simulator.samples import sample_event, sample_overlay, sample_snapshot

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


@pytest.fixture()
def snapshot() -> PositionSnapshot:
    return sample_snapshot()


@pytest.fixture()
def event(snapshot: PositionSnapshot) -> MatchEvent:
    return sample_event(snapshot)


def _event_dict(event: MatchEvent, **changes) -> dict:
    data = event.model_dump(mode="json")
    data.update(changes)
    return data


# --- MatchEvent ------------------------------------------------------------


def test_valid_pass_event(event: MatchEvent) -> None:
    assert event.event_type == "pass"
    assert MatchEvent.model_validate(event.model_dump(mode="json")) == event


@pytest.mark.parametrize("field,value", [("x", 105.1), ("x", -0.1), ("y", 68.5), ("end_y", -2)])
def test_out_of_bounds_rejected(event: MatchEvent, field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        MatchEvent.model_validate(_event_dict(event, **{field: value}))


def test_unknown_event_type_rejected(event: MatchEvent) -> None:
    with pytest.raises(ValidationError):
        MatchEvent.model_validate(_event_dict(event, event_type="dribble_magic"))


def test_unknown_field_rejected(event: MatchEvent) -> None:
    with pytest.raises(ValidationError):
        MatchEvent.model_validate(_event_dict(event, xg=0.3))


def test_pass_needs_receiver(event: MatchEvent) -> None:
    with pytest.raises(ValidationError, match="receiver_id"):
        MatchEvent.model_validate(_event_dict(event, receiver_id=None))


def test_outcome_must_match_event_type(event: MatchEvent) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        MatchEvent.model_validate(_event_dict(event, outcome="saved"))


def test_shot_needs_outcome(event: MatchEvent) -> None:
    data = _event_dict(event, event_type="shot", outcome=None, receiver_id=None)
    with pytest.raises(ValidationError, match="outcome"):
        MatchEvent.model_validate(data)


def test_period_end_needs_no_actor(event: MatchEvent) -> None:
    data = _event_dict(
        event, event_type="period_end", team_id=None, player_id=None, x=None, y=None,
        end_x=None, end_y=None, outcome=None, receiver_id=None, snapshot_id=None,
    )
    assert MatchEvent.model_validate(data).event_type == "period_end"


def test_end_coordinates_set_together(event: MatchEvent) -> None:
    with pytest.raises(ValidationError):
        MatchEvent.model_validate(_event_dict(event, end_y=None))


# --- PositionSnapshot ------------------------------------------------------


def test_valid_snapshot(snapshot: PositionSnapshot) -> None:
    assert len(snapshot.positions) == 22
    assert {p.team_id for p in snapshot.positions} == {"T01", "T02"}


def test_snapshot_rejects_21_players(snapshot: PositionSnapshot) -> None:
    data = snapshot.model_dump(mode="json")
    data["positions"] = data["positions"][:21]
    with pytest.raises(ValidationError):
        PositionSnapshot.model_validate(data)


def test_snapshot_rejects_duplicate_player(snapshot: PositionSnapshot) -> None:
    data = snapshot.model_dump(mode="json")
    data["positions"][1]["player_id"] = data["positions"][0]["player_id"]
    with pytest.raises(ValidationError, match="unique"):
        PositionSnapshot.model_validate(data)


def test_snapshot_rejects_unbalanced_teams(snapshot: PositionSnapshot) -> None:
    data = snapshot.model_dump(mode="json")
    data["positions"][11]["team_id"] = "T01"
    with pytest.raises(ValidationError):
        PositionSnapshot.model_validate(data)


# --- Overlay ---------------------------------------------------------------


def test_valid_overlay(event: MatchEvent, snapshot: PositionSnapshot) -> None:
    overlay = sample_overlay(event, snapshot)
    dumped = overlay.model_dump(mode="json", by_alias=True)
    assert "from" in dumped["visual"]["ghost"]
    assert Overlay.model_validate(dumped) == overlay


def test_ghost_pass_needs_ghost_line(event: MatchEvent, snapshot: PositionSnapshot) -> None:
    data = sample_overlay(event, snapshot).model_dump(mode="json", by_alias=True)
    data["visual"]["ghost"] = None
    with pytest.raises(ValidationError, match="ghost"):
        Overlay.model_validate(data)


def test_overlay_needs_english(event: MatchEvent, snapshot: PositionSnapshot) -> None:
    data = sample_overlay(event, snapshot).model_dump(mode="json", by_alias=True)
    data["text"]["fan"] = {"hi": data["text"]["fan"]["en"]}
    with pytest.raises(ValidationError, match="English"):
        Overlay.model_validate(data)


def test_overlay_needs_evidence(event: MatchEvent, snapshot: PositionSnapshot) -> None:
    data = sample_overlay(event, snapshot).model_dump(mode="json", by_alias=True)
    data["evidence"]["event_ids"] = []
    with pytest.raises(ValidationError):
        Overlay.model_validate(data)


# --- Committed sample files stay valid -------------------------------------


@pytest.mark.parametrize(
    "filename,model",
    [
        ("sample_event.json", MatchEvent),
        ("sample_snapshot.json", PositionSnapshot),
        ("sample_overlay.json", Overlay),
    ],
)
def test_committed_samples_validate(filename: str, model: type) -> None:
    model.model_validate(json.loads((SAMPLES / filename).read_text()))
