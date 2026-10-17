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
_MID_X = PITCH_LENGTH_M / 2   # 52.5
_MID_Y = PITCH_WIDTH_M  / 2   # 34.0


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
    carrier_id: str | None = None,
) -> PositionSnapshot:
    """Return a PositionSnapshot with all 22 players in the possessing team's frame.

    Both shapes are shifted toward the ball's x and y positions, then jittered.
    RNG consumption is always 44 calls (2 per player) regardless of carrier_id.
    If carrier_id is given, that player is placed exactly at (ball_x, ball_y);
    their two RNG jitter calls are still consumed (values discarded) so the
    stream stays identical whether or not a carrier override is applied.
    """
    x_shift_att = (ball_x - _MID_X) * 0.25
    x_shift_def = (ball_x - _MID_X) * 0.25 * 0.60

    # Lateral shift keeps players away from the touchlines when play is wide
    y_shift_att = (ball_y - _MID_Y) * 0.15
    y_shift_def = (ball_y - _MID_Y) * 0.35

    att_slots = base_shape(poss_team.formation, mirrored=False)
    def_slots = base_shape(def_team.formation,  mirrored=True)

    positions: list[PlayerPosition] = []

    for player, (role, bx, by) in zip(poss_xi, att_slots, strict=True):
        jx = rng.uniform(-_JITTER_M, _JITTER_M)   # always consumed
        jy = rng.uniform(-_JITTER_M, _JITTER_M)   # always consumed
        if carrier_id is not None and player.player_id == carrier_id:
            x, y = ball_x, ball_y                  # carrier exactly at ball
        else:
            x = _cx(bx + x_shift_att + jx)
            y = _cy(by + y_shift_att + jy)
        positions.append(
            PlayerPosition(player_id=player.player_id, team_id=player.team_id, role=role, x=x, y=y)
        )

    for player, (role, bx, by) in zip(def_xi, def_slots, strict=True):
        jx = rng.uniform(-_JITTER_M, _JITTER_M)
        jy = rng.uniform(-_JITTER_M, _JITTER_M)
        x = _cx(bx + x_shift_def + jx)
        y = _cy(by + y_shift_def + jy)
        positions.append(
            PlayerPosition(player_id=player.player_id, team_id=player.team_id, role=role, x=x, y=y)
        )

    return PositionSnapshot(
        snapshot_id=snapshot_id,
        match_id=match_id,
        match_clock_s=match_clock_s,
        positions=positions,
    )
