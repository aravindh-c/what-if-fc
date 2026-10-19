"""Tactical Twin – deterministic heuristic scoring for Ghost Pass detection.

Version: twin-v1
Formula: S = 0.35·T + 0.25·P + 0.25·F − 0.15·R  (not a probability)

All coordinates are in the possessing team's frame (attacking towards x=105).
Goal posts: y=30.34 and y=37.66 (centre y=34.0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from core.schemas import (
    MatchEvent,
    OverlayVisual,
    PassLine,
    PlayerPosition,
    PositionSnapshot,
    TwinScores,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "twin-v1"

WEIGHTS: dict[str, float] = {"T": 0.35, "P": 0.25, "F": 0.25, "R": 0.15}

_GOAL_X: float = 105.0
_GOAL_Y: float = 34.0          # centre of goal
_POST_Y_LOW: float = 30.34
_POST_Y_HIGH: float = 37.66

_MAX_CANDIDATE_DIST: float = 40.0   # m: teammates within this radius
_GHOST_MIN_DELTA: float = 0.10      # best_alt.S - actual.S threshold
_GHOST_MIN_F: float = 0.50          # best_alt.F threshold

_OPENNESS_SCALE: float = 5.0        # m: full openness at this distance from lane
_LENGTH_PENALTY_START: float = 35.0 # m
_LENGTH_PENALTY_RANGE: float = 20.0 # m

_T_GOAL_DIST_SCALE: float = 50.0    # m: normalise distance-to-goal
# Fixed reference for goal-angle normalisation: angle from (94, 34) to the posts.
# Using a single fixed point so T is not distorted by the receiver's own y.
_REF_ANGLE: float = abs(
    math.atan2(_POST_Y_HIGH - _GOAL_Y, _GOAL_X - 94.0)
    - math.atan2(_POST_Y_LOW - _GOAL_Y, _GOAL_X - 94.0)
)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _goal_angle(rx: float, ry: float) -> float:
    """Angle (radians) subtended by the goal posts from receiver position."""
    dx_low = _GOAL_X - rx
    dy_low = _POST_Y_LOW - ry
    dx_high = _GOAL_X - rx
    dy_high = _POST_Y_HIGH - ry
    angle_low = math.atan2(dy_low, dx_low)
    angle_high = math.atan2(dy_high, dx_high)
    return abs(angle_high - angle_low)


def _point_to_segment_dist(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """Minimum distance from point P to segment AB."""
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq == 0.0:
        return _dist(px, py, ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    cx = ax + t * dx
    cy = ay + t * dy
    return _dist(px, py, cx, cy)


def _is_offside(
    rx: float,
    ball_x: float,
    opp_positions: list[PlayerPosition],
) -> bool:
    """True when receiver is in an offside position."""
    if rx <= 52.5:
        return False
    if rx <= ball_x:
        return False
    # Law 11: second-last opponent includes the goalkeeper.
    # Equal (>=) is onside; only strictly greater is offside.
    opp_xs = sorted(p.x for p in opp_positions)
    second_last_x = opp_xs[-2] if len(opp_xs) >= 2 else (opp_xs[-1] if opp_xs else 0.0)
    return rx > second_last_x


# ---------------------------------------------------------------------------
# Score components
# ---------------------------------------------------------------------------

def _score_T(rx: float, ry: float) -> float:
    dist_goal = _dist(rx, ry, _GOAL_X, _GOAL_Y)
    t_dist = 0.6 * (1.0 - min(dist_goal, _T_GOAL_DIST_SCALE) / _T_GOAL_DIST_SCALE)
    t_angle = 0.4 * (_goal_angle(rx, ry) / _REF_ANGLE) if _REF_ANGLE > 0 else 0.0
    return max(0.0, min(1.0, t_dist + t_angle))


def _score_P(start_x: float, end_x: float) -> float:
    return max(0.0, min(1.0, (end_x - start_x) / _MAX_CANDIDATE_DIST))


def _score_FR(
    start_x: float, start_y: float,
    end_x: float, end_y: float,
    opp_positions: list[PlayerPosition],
) -> tuple[float, float, float, float]:
    """Return (F, R, openness, length)."""
    length = _dist(start_x, start_y, end_x, end_y)

    # Nearest opponent distance to the pass segment
    seg_dists = [
        _point_to_segment_dist(p.x, p.y, start_x, start_y, end_x, end_y)
        for p in opp_positions
    ]
    min_seg_dist = min(seg_dists) if seg_dists else _OPENNESS_SCALE
    openness = min(min_seg_dist, _OPENNESS_SCALE) / _OPENNESS_SCALE

    length_penalty = (
        1.0 if length <= _LENGTH_PENALTY_START
        else max(0.0, 1.0 - (length - _LENGTH_PENALTY_START) / _LENGTH_PENALTY_RANGE)
    )
    F = openness * length_penalty

    # Nearest opponent to the end point
    end_dists = [_dist(p.x, p.y, end_x, end_y) for p in opp_positions]
    min_end_dist = min(end_dists) if end_dists else _OPENNESS_SCALE
    receiver_pressure = max(0.0, min(1.0, (_OPENNESS_SCALE - min_end_dist) / _OPENNESS_SCALE))

    R = 0.5 * (1.0 - openness) + 0.5 * receiver_pressure
    return F, R, openness, length


def _score_S(T: float, P: float, F: float, R: float) -> float:
    return WEIGHTS["T"] * T + WEIGHTS["P"] * P + WEIGHTS["F"] * F - WEIGHTS["R"] * R


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateScore:
    player_id: str
    end_x: float
    end_y: float
    dist_from_passer: float
    T: float
    P: float
    F: float
    R: float
    S: float
    openness: float
    length: float
    is_actual: bool = False


class TwinResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    weights: dict[str, float]
    candidates: list[dict]          # list of CandidateScore as dicts
    actual_player_id: str
    best_alt_player_id: str | None
    delta: float                    # best_alt.S - actual.S  (may be negative)
    ghost_shown: bool
    visual: OverlayVisual
    scores: TwinScores


# ---------------------------------------------------------------------------
# Pass difficulty
# ---------------------------------------------------------------------------

def pass_difficulty(
    start_x: float, start_y: float,
    end_x: float, end_y: float,
    opp_positions: list[PlayerPosition],
) -> float:
    """0–100 difficulty rating (not a probability)."""
    length = _dist(start_x, start_y, end_x, end_y)
    end_dists = [_dist(p.x, p.y, end_x, end_y) for p in opp_positions]
    min_end_dist = min(end_dists) if end_dists else _OPENNESS_SCALE
    receiver_pressured = 1.0 if min_end_dist <= 3.0 else 0.0

    seg_dists = [
        _point_to_segment_dist(p.x, p.y, start_x, start_y, end_x, end_y)
        for p in opp_positions
    ]
    min_seg = min(seg_dists) if seg_dists else _OPENNESS_SCALE
    openness = min(min_seg, _OPENNESS_SCALE) / _OPENNESS_SCALE

    raw = 1.5 * length + 30.0 * receiver_pressured + 25.0 * (1.0 - openness)
    return max(0.0, min(100.0, raw))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_pass(
    event: MatchEvent,
    snapshot: PositionSnapshot,
) -> TwinResult:
    """Score all candidates for a pass event and return the TwinResult."""
    passer_id = event.player_id
    passer_team = event.team_id
    ball_x = event.x
    assert ball_x is not None and event.y is not None
    assert event.end_x is not None and event.end_y is not None

    teammates = [
        p for p in snapshot.positions
        if p.team_id == passer_team and p.player_id != passer_id
    ]
    opponents = [p for p in snapshot.positions if p.team_id != passer_team]

    candidates: list[CandidateScore] = []
    actual_receiver_id = event.receiver_id
    assert actual_receiver_id is not None

    for tm in teammates:
        # Exclude GK
        if tm.role == "GK":
            continue
        # Distance filter
        d = _dist(event.x, event.y, tm.x, tm.y)
        if d > _MAX_CANDIDATE_DIST and tm.player_id != actual_receiver_id:
            continue
        # Offside filter (actual receiver always included)
        if tm.player_id != actual_receiver_id and _is_offside(tm.x, ball_x, opponents):
            continue

        is_actual = tm.player_id == actual_receiver_id
        # Use actual pass end coords for the actual receiver; teammate position for alternatives
        if is_actual:
            ex, ey = event.end_x, event.end_y
        else:
            ex, ey = tm.x, tm.y

        T = _score_T(ex, ey)
        P = _score_P(event.x, ex)
        F, R, openness, length = _score_FR(event.x, event.y, ex, ey, opponents)
        S = _score_S(T, P, F, R)

        candidates.append(CandidateScore(
            player_id=tm.player_id,
            end_x=ex,
            end_y=ey,
            dist_from_passer=d,
            T=round(T, 6),
            P=round(P, 6),
            F=round(F, 6),
            R=round(R, 6),
            S=round(S, 6),
            openness=round(openness, 6),
            length=round(length, 6),
            is_actual=is_actual,
        ))

    actual_cand = next((c for c in candidates if c.is_actual), None)
    alts = [c for c in candidates if not c.is_actual]
    best_alt = max(alts, key=lambda c: c.S) if alts else None

    actual_S = actual_cand.S if actual_cand else 0.0
    best_alt_S = best_alt.S if best_alt else actual_S
    delta = round(best_alt_S - actual_S, 6)

    ghost_shown = (
        best_alt is not None
        and delta >= _GHOST_MIN_DELTA
        and best_alt.F >= _GHOST_MIN_F
    )

    # Visual
    actual_line: PassLine | None = None
    ghost_line: PassLine | None = None
    if actual_cand:
        actual_line = PassLine(**{
            "from": (event.x, event.y),
            "to": (actual_cand.end_x, actual_cand.end_y),
            "receiver_id": actual_cand.player_id,
        })
    if ghost_shown and best_alt:
        ghost_line = PassLine(**{
            "from": (event.x, event.y),
            "to": (best_alt.end_x, best_alt.end_y),
            "receiver_id": best_alt.player_id,
        })

    # Highlight up to 3 defenders nearest to the actual lane or receiver
    highlight_defenders: list[str] = []
    if actual_cand:
        scored = sorted(
            opponents,
            key=lambda p: min(
                _point_to_segment_dist(
                    p.x, p.y, event.x, event.y, actual_cand.end_x, actual_cand.end_y
                ),
                _dist(p.x, p.y, actual_cand.end_x, actual_cand.end_y),
            ),
        )
        highlight_defenders = [p.player_id for p in scored[:3]]

    visual = OverlayVisual(
        actual=actual_line,
        ghost=ghost_line,
        highlight_defenders=highlight_defenders,
    )

    # TwinScores
    def _comps(c: CandidateScore | None) -> dict:
        if c is None:
            return {"T": 0.0, "P": 0.0, "F": 0.0, "R": 0.0}
        return {"T": round(c.T, 3), "P": round(c.P, 3), "F": round(c.F, 3), "R": round(c.R, 3)}

    scores = TwinScores(
        actual=round(actual_S, 3),
        ghost=round(best_alt_S, 3),
        components_actual=_comps(actual_cand),
        components_ghost=_comps(best_alt),
    )

    return TwinResult(
        version=VERSION,
        weights=WEIGHTS,
        candidates=[vars(c) for c in candidates],
        actual_player_id=actual_receiver_id,
        best_alt_player_id=best_alt.player_id if best_alt else None,
        delta=delta,
        ghost_shown=ghost_shown,
        visual=visual,
        scores=scores,
    )
