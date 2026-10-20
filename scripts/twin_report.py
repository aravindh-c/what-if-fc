"""Print a Ghost Pass summary for seeds 1-10 and all demo scenarios.

Usage:
    python scripts/twin_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

from analytics.metrics import headline_moments, pass_event_for
from analytics.tactical_twin import score_pass
from core.schemas import MatchEvent, PositionSnapshot
from simulator.engine import MatchEngine
from simulator.ids import make_match_id
from simulator.reference_data import build_players, build_teams

SCENARIOS_DIR = Path("data/scenarios")
_SCENARIO_IDS = [
    "missed_overlap_right",
    "forced_pass_into_traffic",
    "late_counter",
    "high_press_escape",
]


def _run_seeds() -> None:
    print("=" * 70)
    print("Ghost Pass stats: seeds 1-10")
    print("=" * 70)
    print(
        f"{'Seed':>5}  {'ghost-elig':>10}  {'turnovers':>9}"
        f"  {'ghost_shown':>11}  {'avg_delta':>9}"
    )
    print("-" * 55)

    teams = {t.team_id: t for t in build_teams()}
    for seed in range(1, 11):
        players = build_players(seed)
        engine = MatchEngine(
            home_team=teams["T01"],
            away_team=teams["T02"],
            players=players,
            seed=seed,
            match_id=make_match_id(seed, "T01", "T02"),
            scenario_id="live",
        )
        events, snapshots = engine.run()
        snap_lookup = {s.snapshot_id: s for s in snapshots}

        headlines = headline_moments(events)
        ghost_eligible = [h for h in headlines if h.ghost_eligible]
        n_turnovers = sum(
            1 for h in ghost_eligible if h.moment_type == "final_third_turnover"
        )

        shown = 0
        deltas: list[float] = []
        for moment in ghost_eligible:
            pass_ev = pass_event_for(moment, events)
            if pass_ev is None:
                continue
            snap = snap_lookup.get(pass_ev.snapshot_id)  # snapshot_id non-None per pass_event_for
            if snap is None:
                continue
            result = score_pass(pass_ev, snap)
            if result.ghost_shown:
                shown += 1
                deltas.append(result.delta)

        avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
        print(
            f"{seed:>5}  {len(ghost_eligible):>10}  {n_turnovers:>9}"
            f"  {shown:>11}  {avg_delta:>9.3f}"
        )

    print()


def _run_scenarios() -> None:
    print("=" * 60)
    print("Demo scenario results")
    print("=" * 60)
    print(
        f"{'Scenario':<32}  {'expected':<12}  {'got':<12}"
        f"  {'delta':>6}  {'F_ghost':>7}  {'ok':>4}"
    )
    print("-" * 80)

    for scen_id in _SCENARIO_IDS:
        sc = json.loads((SCENARIOS_DIR / f"{scen_id}.json").read_text())
        ev = MatchEvent(**sc["actual_pass"])
        snap = PositionSnapshot(**sc["snapshot"])
        result = score_pass(ev, snap)

        expected = sc["expected_ghost_receiver_id"]
        got = result.best_alt_player_id or "-"
        f_ghost = next(
            (c["F"] for c in result.candidates if c["player_id"] == got), 0.0
        )
        ok = (expected == got and result.delta >= 0.10 and result.ghost_shown)
        mark = "ok" if ok else "FAIL"
        print(
            f"{scen_id:<32}  {expected:<12}  {got:<12}"
            f"  {result.delta:>6.3f}  {f_ghost:>7.3f}  {mark:>4}"
        )

    print()


if __name__ == "__main__":
    _run_scenarios()
    _run_seeds()
