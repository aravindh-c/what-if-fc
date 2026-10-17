"""Reference data: deterministic, complete squads, unique identifiers."""

from __future__ import annotations

from collections import Counter

from core.formations import FORMATION_SLOTS, base_shape, starting_xi
from core.pitch import in_bounds
from simulator.reference_data import build_players, build_teams


def test_same_seed_same_players() -> None:
    assert build_players(7) == build_players(7)


def test_different_seed_changes_players() -> None:
    assert build_players(7) != build_players(8)


def test_four_teams_of_eighteen() -> None:
    teams = build_teams()
    players = build_players()
    assert len(teams) == 4
    counts = Counter(p.team_id for p in players)
    assert counts == {t.team_id: 18 for t in teams}


def test_ids_names_and_shirts_unique() -> None:
    players = build_players()
    assert len({p.player_id for p in players}) == len(players)
    assert len({p.name for p in players}) == len(players)
    for team in build_teams():
        shirts = [p.shirt_number for p in players if p.team_id == team.team_id]
        assert len(set(shirts)) == len(shirts)


def test_every_team_can_field_its_formation() -> None:
    players = build_players()
    for team in build_teams():
        xi = starting_xi([p for p in players if p.team_id == team.team_id], team.formation)
        assert len(xi) == 11
        assert [p.role for p in xi] == [r for r, _, _ in FORMATION_SLOTS[team.formation]]


def test_formation_shapes_on_pitch() -> None:
    for formation in FORMATION_SLOTS:
        for mirrored in (False, True):
            for _, x, y in base_shape(formation, mirrored):
                assert in_bounds(x, y)
