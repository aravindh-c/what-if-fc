"""Pitch geometry shared by the simulator, analytics and frontend contract.

Coordinate system (metres), always in the frame of the team in possession:
- origin (0, 0) at that team's left corner flag
- x runs towards the goal it attacks (0 to 105)
- y runs across the pitch (0 to 68)

A position snapshot expresses all 22 players in the possessing team's frame,
so the defending team's goal is always at x = 105.
"""

PITCH_LENGTH_M: float = 105.0
PITCH_WIDTH_M: float = 68.0
GOAL_CENTER: tuple[float, float] = (PITCH_LENGTH_M, PITCH_WIDTH_M / 2)
GOAL_WIDTH_M: float = 7.32


def in_bounds(x: float, y: float) -> bool:
    """True when (x, y) lies on the pitch, edges included."""
    return 0.0 <= x <= PITCH_LENGTH_M and 0.0 <= y <= PITCH_WIDTH_M
