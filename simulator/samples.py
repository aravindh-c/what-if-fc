"""Build one valid example of each contract and write them to data/samples.

Usage:
    python -m simulator.samples --out data/samples

The values only illustrate the shape of each record; the Day 2 simulator and
the Tactical Twin produce the real ones.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from core.formations import base_shape, starting_xi
from core.schemas import (
    EventType,
    Evidence,
    MatchEvent,
    MomentType,
    NarrativeSource,
    NarrativeText,
    Outcome,
    Overlay,
    OverlayText,
    OverlayVisual,
    PassLine,
    PlayerPosition,
    PositionSnapshot,
    TwinScores,
    ValidationStatus,
)
from simulator.reference_data import DEFAULT_SEED, build_players, build_teams

MATCH_ID = "m_0001"
SCENARIO_ID = "sample"
SNAPSHOT_ID = "s_0001"


def sample_snapshot(seed: int = DEFAULT_SEED) -> PositionSnapshot:
    """T01 in possession (attacking towards x = 105), T02 defending."""
    teams = {t.team_id: t for t in build_teams()}
    players = build_players(seed)
    attack, defend = teams["T01"], teams["T02"]
    att_xi = starting_xi([p for p in players if p.team_id == attack.team_id], attack.formation)
    def_xi = starting_xi([p for p in players if p.team_id == defend.team_id], defend.formation)
    positions = [
        PlayerPosition(player_id=p.player_id, team_id=p.team_id, role=role, x=x, y=y)
        for p, (role, x, y) in zip(att_xi, base_shape(attack.formation), strict=True)
    ] + [
        PlayerPosition(player_id=p.player_id, team_id=p.team_id, role=role, x=x, y=y)
        for p, (role, x, y) in zip(def_xi, base_shape(defend.formation, mirrored=True), strict=True)
    ]
    return PositionSnapshot(
        snapshot_id=SNAPSHOT_ID, match_id=MATCH_ID, match_clock_s=4275, positions=positions
    )


def sample_event(snapshot: PositionSnapshot) -> MatchEvent:
    """A pass from T01's defensive midfielder to a central midfielder."""
    by_role = {(p.team_id, p.role): p for p in snapshot.positions}
    passer = next(p for p in snapshot.positions if p.team_id == "T01" and p.role == "DM")
    receiver = by_role[("T01", "CM")]
    return MatchEvent(
        event_id="ev_9012",
        match_id=MATCH_ID,
        scenario_id=SCENARIO_ID,
        seed=DEFAULT_SEED,
        event_time=datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC),
        match_clock_s=snapshot.match_clock_s,
        period=2,
        event_type=EventType.PASS,
        team_id="T01",
        player_id=passer.player_id,
        possession_id=118,
        x=passer.x,
        y=passer.y,
        end_x=receiver.x,
        end_y=receiver.y,
        outcome=Outcome.COMPLETE,
        receiver_id=receiver.player_id,
        pressure_level=0.62,
        snapshot_id=snapshot.snapshot_id,
    )


def sample_overlay(event: MatchEvent, snapshot: PositionSnapshot) -> Overlay:
    """A ghost_pass overlay: actual pass vs a better option to the right winger."""
    ghost_target = [p for p in snapshot.positions if p.team_id == "T01" and p.role == "W"][-1]
    defenders = [p.player_id for p in snapshot.positions if p.team_id == "T02" and p.role == "FB"]
    return Overlay(
        overlay_id="ov_0001",
        match_id=event.match_id,
        match_clock_s=event.match_clock_s,
        display_duration_s=8,
        moment_type=MomentType.GHOST_PASS,
        calculation_version="twin-v1",
        validation_status=ValidationStatus.PASSED,
        narrative_source=NarrativeSource.TEMPLATE,
        visual=OverlayVisual(
            actual=PassLine(
                from_=(event.x, event.y), to=(event.end_x, event.end_y),
                receiver_id=event.receiver_id,
            ),
            ghost=PassLine(
                from_=(event.x, event.y), to=(ghost_target.x, ghost_target.y),
                receiver_id=ghost_target.player_id,
            ),
            highlight_defenders=defenders,
        ),
        scores=TwinScores(
            actual=0.41, ghost=0.63,
            components_actual={"T": 0.4, "P": 0.3, "F": 0.9, "R": 0.3},
            components_ghost={"T": 0.7, "P": 0.6, "F": 0.8, "R": 0.2},
        ),
        evidence=Evidence(event_ids=[event.event_id], metrics={"pressure_level": 0.62}),
        text=OverlayText(
            analyst={"en": NarrativeText(
                headline="Switch was on",
                body="Option score 0.63 vs 0.41 for the pass played: more progress, open lane.",
            )},
            fan={"en": NarrativeText(
                headline="The ball out wide was free!",
                body="A pass to the right wing would have opened the game up.",
            )},
            cue="Watch the space on the right touchline.",
        ),
    )


def write_samples(out_dir: Path, seed: int = DEFAULT_SEED) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = sample_snapshot(seed)
    event = sample_event(snapshot)
    overlay = sample_overlay(event, snapshot)
    paths = []
    for name, model in (("event", event), ("snapshot", snapshot), ("overlay", overlay)):
        path = out_dir / f"sample_{name}.json"
        path.write_text(json.dumps(model.model_dump(mode="json", by_alias=True), indent=2) + "\n")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Write one sample of each contract.")
    parser.add_argument("--out", type=Path, default=Path("data/samples"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    for p in write_samples(args.out, args.seed):
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
