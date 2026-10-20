"""CLI entry point for the match simulator.

Usage:
    python -m simulator.run --seed 7 --home T01 --away T02

Writes:
    data/generated/<match_id>_events.jsonl
    data/generated/<match_id>_snapshots.jsonl

Prints a one-line summary: score, passes, completion %, shots, snapshots.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.schemas import EventType, Outcome
from simulator.engine import MatchEngine
from simulator.ids import make_match_id
from simulator.reference_data import build_players, build_teams

OUT_DIR = Path("data/generated")


def run_match(
    seed: int,
    home_id: str,
    away_id: str,
    scenario_id: str = "live",
) -> tuple[str, list, list]:
    """Run one match; return (match_id, events, snapshots)."""
    teams   = {t.team_id: t for t in build_teams()}
    players = build_players(seed)

    if home_id not in teams:
        raise ValueError(f"unknown team id: {home_id!r}")
    if away_id not in teams:
        raise ValueError(f"unknown team id: {away_id!r}")

    match_id = make_match_id(seed, home_id, away_id)
    engine   = MatchEngine(
        home_team=teams[home_id],
        away_team=teams[away_id],
        players=players,
        seed=seed,
        match_id=match_id,
        scenario_id=scenario_id,
    )
    events, snapshots = engine.run()
    return match_id, events, snapshots


def write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.model_dump(mode="json")) + "\n")


def summarise(home_id: str, away_id: str, events: list, snapshots: list) -> str:
    home_goals = sum(
        1 for e in events
        if e.event_type == EventType.GOAL and e.team_id == home_id
    )
    away_goals = sum(
        1 for e in events
        if e.event_type == EventType.GOAL and e.team_id == away_id
    )
    passes     = [e for e in events if e.event_type == EventType.PASS]
    complete   = sum(1 for p in passes if p.outcome == Outcome.COMPLETE)
    shots      = sum(1 for e in events if e.event_type == EventType.SHOT)
    comp_pct   = (complete / len(passes) * 100) if passes else 0.0
    return (
        f"Score: {home_id} {home_goals}–{away_goals} {away_id} | "
        f"Events: {len(events)} | "
        f"Passes: {len(passes)} ({comp_pct:.1f}% complete) | "
        f"Shots: {shots} | "
        f"Snapshots: {len(snapshots)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a synthetic football match.")
    parser.add_argument("--seed",     type=int, default=7)
    parser.add_argument("--home",     default="T01")
    parser.add_argument("--away",     default="T02")
    parser.add_argument("--scenario", default="live")
    args = parser.parse_args()

    match_id, events, snapshots = run_match(args.seed, args.home, args.away, args.scenario)

    ev_path  = OUT_DIR / f"{match_id}_events.jsonl"
    sn_path  = OUT_DIR / f"{match_id}_snapshots.jsonl"
    write_jsonl(ev_path,  events)
    write_jsonl(sn_path,  snapshots)

    print(summarise(args.home, args.away, events, snapshots))
    print(f"wrote {ev_path}  ({len(events)} lines)")
    print(f"wrote {sn_path}  ({len(snapshots)} lines)")


if __name__ == "__main__":
    main()
