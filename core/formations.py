"""Formation shapes and starting line-ups.

Base shapes are in the frame of a team attacking towards x = 105 (the team in
possession). For the defending team, use mirrored=True (x -> 105 - x,
y -> 68 - y), so both teams share the possessing team's frame.

The Day 2 simulator shifts these shapes with the ball and phase of play;
here they are static templates.
"""

from __future__ import annotations

from collections.abc import Sequence

from core.pitch import PITCH_LENGTH_M, PITCH_WIDTH_M
from core.schemas import Player, Role

# (role, x, y) for each of the 11 slots, team attacking towards x = 105.
FORMATION_SLOTS: dict[str, list[tuple[Role, float, float]]] = {
    "4-3-3": [
        (Role.GK, 5, 34),
        (Role.CB, 25, 26), (Role.CB, 25, 42),
        (Role.FB, 30, 10), (Role.FB, 30, 58),
        (Role.DM, 40, 34),
        (Role.CM, 50, 24), (Role.CM, 50, 44),
        (Role.W, 68, 10), (Role.W, 68, 58),
        (Role.ST, 75, 34),
    ],
    "4-2-3-1": [
        (Role.GK, 5, 34),
        (Role.CB, 25, 26), (Role.CB, 25, 42),
        (Role.FB, 30, 10), (Role.FB, 30, 58),
        (Role.DM, 42, 27), (Role.DM, 42, 41),
        (Role.AM, 60, 34),
        (Role.W, 65, 12), (Role.W, 65, 56),
        (Role.ST, 75, 34),
    ],
    "3-5-2": [
        (Role.GK, 5, 34),
        (Role.CB, 24, 20), (Role.CB, 22, 34), (Role.CB, 24, 48),
        (Role.FB, 48, 6), (Role.FB, 48, 62),
        (Role.DM, 40, 34),
        (Role.CM, 52, 24), (Role.CM, 52, 44),
        (Role.ST, 72, 28), (Role.ST, 72, 40),
    ],
}


def base_shape(formation: str, mirrored: bool = False) -> list[tuple[Role, float, float]]:
    """Return the 11 (role, x, y) slots, optionally mirrored for the defending team."""
    slots = FORMATION_SLOTS[formation]
    if not mirrored:
        return list(slots)
    return [(r, PITCH_LENGTH_M - x, PITCH_WIDTH_M - y) for r, x, y in slots]


def starting_xi(squad: Sequence[Player], formation: str) -> list[Player]:
    """Pick 11 players matching the formation's roles, in slot order.

    Players are taken in squad order for each role (lower shirt numbers first),
    so the result is deterministic. Raises ValueError if the squad cannot fill
    a slot.
    """
    available = sorted(squad, key=lambda p: p.shirt_number)
    used: set[str] = set()
    xi: list[Player] = []
    for role, _, _ in FORMATION_SLOTS[formation]:
        pick = next((p for p in available if p.role == role and p.player_id not in used), None)
        if pick is None:
            raise ValueError(f"squad cannot fill a {role} slot for {formation}")
        used.add(pick.player_id)
        xi.append(pick)
    return xi
