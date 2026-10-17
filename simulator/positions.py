"""Build PositionSnapshot from formation base shapes.

Coordinates are always in the possessing team's frame:
  x in [0, 105] towards the attacking goal, y in [0, 68].

The defending team's base shape is already mirrored so that x=105 is their
goal (the same goal the possessing team attacks).
"""

from __future__ import annotations

import random as _random

from core.formations import base_shape
from core.pitch import PITCH_LENGTH_M, PITCH_WIDTH_M
from core.schemas import Player, PlayerPosition, PositionSnapshot, Team

_JITTER_M = 2.0  # max per-axis jitter in metres


def _cx(v: float) -> float:
    return max(0.0, min(PITCH_LENGTH_M, v))


def _cy(v: float) -> float:
    return max(0.0, min(PITCH_WIDTH_M, v))


def build_snapshot(
    *,
    snapshot_id: str,
    match_id: str,
    match_clock_s: int,
    poss_team: Team,
    def_team: Team,
    poss_xi: list[Player],
    def_xi: list[Player],
    ball_x: float,
    ball_y: float,
    rng: _random.Random,
) -> PositionSnapshot:
    """Return a PositionSnapshot with all 22 players in the possessing team's frame.

    Both shapes are shifted toward the ball's x-position, then jittered.
    The defending team's shape is already mirrored so their goal is at x=105.
    """
    # How far the ball is from the centre line, used to compress/stretch both shapes
    mid = PITCH_LENGTH_M / 2
    ball_shift = (ball_x - mid) * 0.25   # ±13 m at most
    def_shift  = ball_shift * 0.60        # defenders track with ball, less aggressively

    att_slots = base_shape(poss_team.formation, mirrored=False)
    def_slots = base_shape(def_team.formation,  mirrored=True)

    positions: list[PlayerPosition] = []

    for player, (role, bx, by) in zip(poss_xi, att_slots, strict=True):
        x = _cx(bx + ball_shift + rng.uniform(-_JITTER_M, _JITTER_M))
        y = _cy(by             + rng.uniform(-_JITTER_M, _JITTER_M))
        positions.append(
            PlayerPosition(player_id=player.player_id, team_id=player.team_id, role=role, x=x, y=y)
        )

    for player, (role, bx, by) in zip(def_xi, def_slots, strict=True):
        x = _cx(bx + def_shift + rng.uniform(-_JITTER_M, _JITTER_M))
        y = _cy(by             + rng.uniform(-_JITTER_M, _JITTER_M))
        positions.append(
            PlayerPosition(player_id=player.player_id, team_id=player.team_id, role=role, x=x, y=y)
        )

    return PositionSnapshot(
        snapshot_id=snapshot_id,
        match_id=match_id,
        match_clock_s=match_clock_s,
        positions=positions,
    )
