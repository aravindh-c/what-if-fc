"""Data contracts for What If FC.

Three streams/contracts, all validated with pydantic:
- MatchEvent: one on-ball action, streamed to Fabric Eventstream
- PositionSnapshot: all 22 player positions at an eligible pass or key moment
- Overlay: validated output sent from the API to the frontend

Reference data (Team, Player) is generated once by simulator.reference_data.
All clubs and players are fictional.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.pitch import PITCH_LENGTH_M, PITCH_WIDTH_M

# ---------------------------------------------------------------------------
# Shared field types
# ---------------------------------------------------------------------------

X = Annotated[float, Field(ge=0.0, le=PITCH_LENGTH_M, description="metres along the pitch")]
Y = Annotated[float, Field(ge=0.0, le=PITCH_WIDTH_M, description="metres across the pitch")]
Rating = Annotated[int, Field(ge=1, le=99)]
Id = Annotated[str, Field(min_length=1, max_length=64)]
LanguageCode = Literal["en", "hi", "es"]

MAX_MATCH_CLOCK_S = 7200  # 120 minutes, covers stoppage time


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    PASS = "pass"
    RECEPTION = "reception"
    CARRY = "carry"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    PRESSURE = "pressure"
    FOUL = "foul"
    GOAL = "goal"
    KICKOFF = "kickoff"
    PERIOD_END = "period_end"


class Outcome(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    ON_TARGET = "on_target"
    OFF_TARGET = "off_target"
    SAVED = "saved"
    BLOCKED = "blocked"
    WON = "won"
    LOST = "lost"


class Position(StrEnum):
    GK = "GK"
    DF = "DF"
    MF = "MF"
    FW = "FW"


class Role(StrEnum):
    GK = "GK"
    CB = "CB"
    FB = "FB"
    DM = "DM"
    CM = "CM"
    AM = "AM"
    W = "W"
    ST = "ST"


class TeamStyle(StrEnum):
    POSSESSION = "possession"
    DIRECT = "direct"
    HIGH_PRESS = "high_press"


class MomentType(StrEnum):
    GHOST_PASS = "ghost_pass"
    GOAL = "goal"
    TURNOVER = "turnover"
    MOMENTUM_SWING = "momentum_swing"
    PRESSURE_SPELL = "pressure_spell"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class NarrativeSource(StrEnum):
    AGENT = "agent"
    TEMPLATE = "template"


# Which outcomes are allowed for which event types.
ALLOWED_OUTCOMES: dict[EventType, set[Outcome]] = {
    EventType.PASS: {Outcome.COMPLETE, Outcome.INCOMPLETE},
    EventType.SHOT: {Outcome.ON_TARGET, Outcome.OFF_TARGET, Outcome.SAVED, Outcome.BLOCKED},
    EventType.TACKLE: {Outcome.WON, Outcome.LOST},
    EventType.INTERCEPTION: {Outcome.WON, Outcome.LOST},
    EventType.PRESSURE: {Outcome.WON, Outcome.LOST},
    EventType.CARRY: {Outcome.COMPLETE, Outcome.LOST},
}
EVENTS_NEEDING_OUTCOME = {EventType.PASS, EventType.SHOT, EventType.TACKLE}
EVENTS_NEEDING_END = {EventType.PASS, EventType.CARRY}
EVENTS_WITHOUT_ACTOR = {EventType.PERIOD_END}


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


class Team(StrictModel):
    team_id: Id
    name: str = Field(min_length=3, max_length=40)
    short_name: str = Field(pattern=r"^[A-Z]{3}$")
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    formation: Literal["4-3-3", "4-2-3-1", "3-5-2"]
    style: TeamStyle


class PlayerRatings(StrictModel):
    passing: Rating
    pace: Rating
    finishing: Rating
    pressing: Rating


class Player(StrictModel):
    player_id: Id
    team_id: Id
    name: str = Field(min_length=3, max_length=40)
    shirt_number: int = Field(ge=1, le=99)
    position: Position
    role: Role
    ratings: PlayerRatings


# ---------------------------------------------------------------------------
# Stream 1: match events
# ---------------------------------------------------------------------------


class MatchEvent(StrictModel):
    event_id: Id
    match_id: Id
    scenario_id: Id
    seed: int = Field(ge=0)
    event_time: datetime
    match_clock_s: int = Field(ge=0, le=MAX_MATCH_CLOCK_S)
    period: Literal[1, 2]
    event_type: EventType
    team_id: Id | None = None
    player_id: Id | None = None
    possession_id: int = Field(ge=0)
    x: X | None = None
    y: Y | None = None
    end_x: X | None = None
    end_y: Y | None = None
    outcome: Outcome | None = None
    receiver_id: Id | None = None
    pressure_level: float = Field(default=0.0, ge=0.0, le=1.0)
    snapshot_id: Id | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> MatchEvent:
        et = self.event_type
        if et not in EVENTS_WITHOUT_ACTOR:
            if self.team_id is None or self.player_id is None:
                raise ValueError(f"{et} needs team_id and player_id")
            if self.x is None or self.y is None:
                raise ValueError(f"{et} needs a start location (x, y)")
        if et in EVENTS_NEEDING_END and (self.end_x is None or self.end_y is None):
            raise ValueError(f"{et} needs an end location (end_x, end_y)")
        if (self.end_x is None) != (self.end_y is None):
            raise ValueError("end_x and end_y must be set together")
        if et in EVENTS_NEEDING_OUTCOME and self.outcome is None:
            raise ValueError(f"{et} needs an outcome")
        if self.outcome is not None and et in ALLOWED_OUTCOMES:
            if self.outcome not in ALLOWED_OUTCOMES[et]:
                raise ValueError(f"outcome {self.outcome} not allowed for {et}")
        if et == EventType.PASS and self.receiver_id is None:
            raise ValueError("pass needs receiver_id (intended receiver)")
        if et != EventType.PASS and self.receiver_id is not None:
            raise ValueError("receiver_id is only valid on passes")
        return self


# ---------------------------------------------------------------------------
# Stream 2: position snapshots
# ---------------------------------------------------------------------------


class PlayerPosition(StrictModel):
    player_id: Id
    team_id: Id
    role: Role
    x: X
    y: Y


class PositionSnapshot(StrictModel):
    snapshot_id: Id
    match_id: Id
    match_clock_s: int = Field(ge=0, le=MAX_MATCH_CLOCK_S)
    positions: list[PlayerPosition] = Field(min_length=22, max_length=22)

    @model_validator(mode="after")
    def _check_squads(self) -> PositionSnapshot:
        ids = [p.player_id for p in self.positions]
        if len(set(ids)) != len(ids):
            raise ValueError("player_id values must be unique within a snapshot")
        counts: dict[str, int] = {}
        for p in self.positions:
            counts[p.team_id] = counts.get(p.team_id, 0) + 1
        if len(counts) != 2 or any(c != 11 for c in counts.values()):
            raise ValueError(f"snapshot needs 11 players for each of 2 teams, got {counts}")
        keepers = [p for p in self.positions if p.role == Role.GK]
        if len(keepers) != 2 or len({k.team_id for k in keepers}) != 2:
            raise ValueError("snapshot needs exactly one goalkeeper per team")
        return self


# ---------------------------------------------------------------------------
# Contract 3: overlays (API -> frontend)
# ---------------------------------------------------------------------------

Point = tuple[X, Y]


class PassLine(StrictModel):
    from_: Point = Field(alias="from")
    to: Point
    receiver_id: Id


class OverlayVisual(StrictModel):
    actual: PassLine | None = None
    ghost: PassLine | None = None
    highlight_defenders: list[Id] = Field(default_factory=list)


class TwinScores(StrictModel):
    """Heuristic tactical scores from the Tactical Twin. Not probabilities, not xG/xA."""

    actual: float = Field(ge=-1.0, le=1.0)
    ghost: float = Field(ge=-1.0, le=1.0)
    components_actual: dict[Literal["T", "P", "F", "R"], float]
    components_ghost: dict[Literal["T", "P", "F", "R"], float]


class Evidence(StrictModel):
    event_ids: list[Id] = Field(min_length=1)
    metrics: dict[str, float] = Field(default_factory=dict)


class NarrativeText(StrictModel):
    headline: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=280)


class OverlayText(StrictModel):
    analyst: dict[LanguageCode, NarrativeText]
    fan: dict[LanguageCode, NarrativeText]
    cue: str | None = Field(default=None, max_length=280)

    @model_validator(mode="after")
    def _english_required(self) -> OverlayText:
        if "en" not in self.analyst or "en" not in self.fan:
            raise ValueError("analyst and fan text must both include English ('en')")
        return self


class Overlay(StrictModel):
    overlay_id: Id
    match_id: Id
    match_clock_s: int = Field(ge=0, le=MAX_MATCH_CLOCK_S)
    display_duration_s: int = Field(ge=1, le=30)
    moment_type: MomentType
    calculation_version: str = Field(pattern=r"^[a-z]+-v\d+$")
    validation_status: ValidationStatus
    narrative_source: NarrativeSource
    visual: OverlayVisual | None = None
    scores: TwinScores | None = None
    evidence: Evidence
    text: OverlayText

    @model_validator(mode="after")
    def _ghost_pass_needs_geometry(self) -> Overlay:
        if self.moment_type == MomentType.GHOST_PASS:
            if self.visual is None or self.visual.actual is None or self.visual.ghost is None:
                raise ValueError("ghost_pass overlay needs visual.actual and visual.ghost")
            if self.scores is None:
                raise ValueError("ghost_pass overlay needs scores")
        return self
