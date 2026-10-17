"""Seeded generator for fictional clubs and players.

Usage:
    python -m simulator.reference_data --out data/reference --seed 7

All names are invented. Any resemblance to real clubs or players is
coincidental; change the name pools below if a combination looks real.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from core.schemas import Player, PlayerRatings, Position, Role, Team, TeamStyle

DEFAULT_SEED = 7

TEAMS: list[Team] = [
    Team(team_id="T01", name="Kestrel Vale FC", short_name="KVF",
         primary_color="#1F6F5B", secondary_color="#F2C14E",
         formation="4-3-3", style=TeamStyle.POSSESSION),
    Team(team_id="T02", name="Thornfield Rovers", short_name="THR",
         primary_color="#8C1C13", secondary_color="#F4F1DE",
         formation="4-2-3-1", style=TeamStyle.HIGH_PRESS),
    Team(team_id="T03", name="Saltmere Mariners", short_name="SMM",
         primary_color="#1D3557", secondary_color="#A8DADC",
         formation="3-5-2", style=TeamStyle.DIRECT),
    Team(team_id="T04", name="Copperhill Athletic", short_name="CPA",
         primary_color="#B5651D", secondary_color="#2B2D42",
         formation="4-3-3", style=TeamStyle.HIGH_PRESS),
]

# 18-player squad: role and shirt number. Covers every formation in core.formations.
SQUAD_TEMPLATE: list[tuple[Role, int]] = [
    (Role.GK, 1), (Role.GK, 13),
    (Role.CB, 4), (Role.CB, 5), (Role.CB, 15), (Role.CB, 16),
    (Role.FB, 2), (Role.FB, 3), (Role.FB, 12),
    (Role.DM, 6), (Role.DM, 14),
    (Role.CM, 8), (Role.CM, 18),
    (Role.AM, 10),
    (Role.W, 7), (Role.W, 11),
    (Role.ST, 9), (Role.ST, 19),
]

ROLE_TO_POSITION: dict[Role, Position] = {
    Role.GK: Position.GK,
    Role.CB: Position.DF, Role.FB: Position.DF,
    Role.DM: Position.MF, Role.CM: Position.MF, Role.AM: Position.MF,
    Role.W: Position.FW, Role.ST: Position.FW,
}

# Baseline ratings per role: (passing, pace, finishing, pressing)
ROLE_BASELINE: dict[Role, tuple[int, int, int, int]] = {
    Role.GK: (55, 45, 15, 30),
    Role.CB: (62, 60, 30, 65),
    Role.FB: (66, 74, 38, 68),
    Role.DM: (72, 62, 45, 74),
    Role.CM: (76, 66, 55, 70),
    Role.AM: (80, 70, 68, 62),
    Role.W:  (72, 82, 66, 64),
    Role.ST: (64, 76, 80, 60),
}

STYLE_BONUS: dict[TeamStyle, tuple[int, int, int, int]] = {
    TeamStyle.POSSESSION: (6, 0, 0, 0),
    TeamStyle.DIRECT: (0, 4, 3, 0),
    TeamStyle.HIGH_PRESS: (0, 2, 0, 6),
}

FIRST_NAMES = [
    "Arlo", "Bastian", "Caio", "Dario", "Emeka", "Felix", "Goran", "Hiro", "Idris", "Jonas",
    "Kian", "Luca", "Mateo", "Nikhil", "Oskar", "Pavel", "Quinn", "Rafael", "Soren", "Tariq",
    "Umar", "Viktor", "Wren", "Xander", "Yusuf", "Zane", "Anders", "Bruno", "Cyril", "Dmitri",
    "Elio", "Farid", "Gael", "Hugo", "Ilan", "Joaquin", "Kofi", "Lennart", "Marek", "Noel",
]

LAST_NAMES = [
    "Ashgrove", "Brannick", "Calloway", "Dunmore", "Elsworth", "Falkner", "Garrow", "Holloway",
    "Iverson", "Jarrell", "Kettering", "Lanfear", "Marchetti", "Nkemelu", "Okonkwo-Hale",
    "Pellerin", "Quarles", "Rosswell", "Strand", "Thackeray", "Underhill", "Valcourt",
    "Whitlock", "Yarrow", "Zelenko", "Abernathy", "Blackwood", "Castellan", "Dorsey",
    "Eastham", "Fairbrook", "Greaves", "Hartigan", "Ingram", "Juniper", "Kowalczyk",
    "Lindqvist", "Moravec", "Northcott", "Oyelaran", "Penhallow", "Rutherglen", "Sandoval",
]


def _clamp(v: int, lo: int = 10, hi: int = 92) -> int:
    return max(lo, min(hi, v))


def build_teams() -> list[Team]:
    """Return the fixed list of fictional clubs."""
    return list(TEAMS)


def build_players(seed: int = DEFAULT_SEED) -> list[Player]:
    """Generate 18 players per club. Same seed -> identical squads."""
    rng = random.Random(seed)
    used_names: set[str] = set()
    players: list[Player] = []
    for team in TEAMS:
        bonus = STYLE_BONUS[team.style]
        for idx, (role, shirt) in enumerate(SQUAD_TEMPLATE, start=1):
            name = ""
            while not name or name in used_names:
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            used_names.add(name)
            base = ROLE_BASELINE[role]
            vals = [_clamp(b + bonus[i] + rng.randint(-8, 8)) for i, b in enumerate(base)]
            players.append(
                Player(
                    player_id=f"{team.team_id}-P{idx:02d}",
                    team_id=team.team_id,
                    name=name,
                    shirt_number=shirt,
                    position=ROLE_TO_POSITION[role],
                    role=role,
                    ratings=PlayerRatings(
                        passing=vals[0], pace=vals[1], finishing=vals[2], pressing=vals[3]
                    ),
                )
            )
    return players


def write_reference(out_dir: Path, seed: int = DEFAULT_SEED) -> tuple[Path, Path]:
    """Write teams.json and players.json; return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    teams_path = out_dir / "teams.json"
    players_path = out_dir / "players.json"
    teams_path.write_text(
        json.dumps([t.model_dump(mode="json") for t in build_teams()], indent=2) + "\n"
    )
    players_path.write_text(
        json.dumps([p.model_dump(mode="json") for p in build_players(seed)], indent=2) + "\n"
    )
    return teams_path, players_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fictional clubs and players.")
    parser.add_argument("--out", type=Path, default=Path("data/reference"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    teams_path, players_path = write_reference(args.out, args.seed)
    print(f"wrote {teams_path} and {players_path}")


if __name__ == "__main__":
    main()
