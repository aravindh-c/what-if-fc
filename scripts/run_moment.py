"""Run the moment workflow for one key moment and print the overlay.

Usage:
    python -m scripts.run_moment --scenario missed_overlap
    python -m scripts.run_moment --seed 7 --moment 1
    python -m scripts.run_moment --seed 7 --moment 1 --fabric
    python -m scripts.run_moment --scenario high_press_escape --force-fail

Flags:
    --scenario <id>   Load a hand-designed demo scenario by scenario_id
    --seed N          Seed for the match simulator (use with --moment)
    --moment K        K-th ghost-eligible headline moment (1-indexed)
    --fabric          Use FabricKql instead of LocalKql
    --force-fail      Demo template fallback via a stub that sleeps past the timeout

Environment variables (required when using --fabric or without --force-fail):
    FOUNDRY_PROJECT_ENDPOINT
    FOUNDRY_MODEL
    KQL_CLUSTER_URI  (--fabric only)
    KQL_DATABASE     (--fabric only)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"ERROR: {name!r} is not set. Copy .env.example to .env.", file=sys.stderr)
        sys.exit(1)
    return value


# ---------------------------------------------------------------------------
# Force-fail stub
# ---------------------------------------------------------------------------


class _SleeperAgent:
    """Stub agent whose run() sleeps indefinitely, causing asyncio.wait_for to time out."""

    async def run(self, *args: object, **kwargs: object) -> None:
        await asyncio.sleep(9999)


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------


def _load_scenario(scenario_id: str):
    from simulator.scenarios import _build_scenarios  # noqa: PLC2701

    scenarios = _build_scenarios()
    match = [s for s in scenarios if s.scenario_id == scenario_id]
    if not match:
        ids = [s.scenario_id for s in scenarios]
        print(f"ERROR: scenario {scenario_id!r} not found. Available: {ids}", file=sys.stderr)
        sys.exit(1)
    return match[0]


def _packet_from_scenario(scenario):
    """Build EvidencePacket + TwinResult from a hand-designed Scenario.

    Returns (packet, twin, roster, ev) where ev has the corrected match_id
    suitable for LocalKql (^match_[A-Za-z0-9_]+$).
    """
    from analytics.evidence import EvidencePacket, LiveMetrics
    from analytics.tactical_twin import pass_difficulty as _pass_difficulty
    from analytics.tactical_twin import score_pass
    from simulator.reference_data import build_players

    players = build_players(7)
    # Remap match_id from "demo" to a KQL-valid id so LocalKql accepts it.
    match_id = f"match_demo_{scenario.scenario_id}"
    ev = scenario.actual_pass.model_copy(update={"match_id": match_id})
    snap = scenario.snapshot.model_copy(update={"match_id": match_id})

    twin = score_pass(ev, snap)

    minute = ev.match_clock_s // 60
    live = LiveMetrics(
        minute=minute,
        momentum_share={},
        pressure_index={},
        scoreline={"T01": 0, "T02": 0},
    )

    # Re-derive pass length and defender distance from twin candidates
    actual_cand = next((c for c in twin.candidates if c.get("is_actual")), None)
    ghost_cand = (
        next(
            (c for c in twin.candidates if c.get("player_id") == twin.best_alt_player_id),
            None,
        )
        if twin.ghost_shown
        else None
    )

    # Compute pass difficulty from event coordinates and opponent positions
    opp_positions = [p for p in snap.positions if p.team_id != ev.team_id]
    if (
        ev.x is not None
        and ev.y is not None
        and ev.end_x is not None
        and ev.end_y is not None
    ):
        pd = round(_pass_difficulty(ev.x, ev.y, ev.end_x, ev.end_y, opp_positions), 1)
    else:
        pd = 0.0

    start_x = ev.x
    actual_progress = (
        round(actual_cand["end_x"] - start_x, 1)
        if actual_cand and start_x is not None
        else None
    )
    ghost_progress = (
        round(ghost_cand["end_x"] - start_x, 1)
        if ghost_cand and start_x is not None
        else None
    )

    packet = EvidencePacket(
        match_id=match_id,
        moment_type="high_pressure_final_third_pass",
        moment_minute=minute,
        moment_score=0.7,
        event_ids=[ev.event_id],
        live_metrics=live,
        twin_version=twin.version,
        twin_weights=twin.weights,
        twin_delta=twin.delta,
        twin_actual_score=twin.scores.actual,
        twin_ghost_score=twin.scores.ghost,
        twin_ghost_player_id=twin.best_alt_player_id,
        twin_components_actual=dict(twin.scores.components_actual),
        twin_components_ghost=dict(twin.scores.components_ghost),
        pass_difficulty=pd,
        ghost_shown=twin.ghost_shown,
        formula_version=twin.version,
        label="Tactical option score, roughly 0 to 1 (very risky passes can go below 0): how threatening, forward, open and safe a pass was. Higher is better. Not a probability.",
        passer_id=ev.player_id,
        actual_receiver_id=ev.receiver_id,
        highlight_defenders=list(twin.visual.highlight_defenders),
        actual_pass_length_m=round(actual_cand["length"], 1) if actual_cand else 0.0,
        ghost_pass_length_m=round(ghost_cand["length"], 1) if ghost_cand else None,
        actual_nearest_defender_m=(
            round(actual_cand["nearest_defender_m"], 1) if actual_cand else None
        ),
        ghost_nearest_defender_m=(
            round(ghost_cand["nearest_defender_m"], 1) if ghost_cand else None
        ),
        actual_progress_m=actual_progress,
        ghost_progress_m=ghost_progress,
    )
    return packet, twin, players, ev


# ---------------------------------------------------------------------------
# Seed + moment loading
# ---------------------------------------------------------------------------


def _packet_from_seed(seed: int, moment_k: int):
    """Build EvidencePacket + TwinResult from the K-th ghost moment in a seeded match."""
    from analytics.evidence import build_evidence_packet
    from analytics.metrics import key_moments, pass_event_for
    from analytics.tactical_twin import score_pass
    from simulator.reference_data import build_players
    from simulator.run import run_match

    match_id, events, snapshots = run_match(seed, "T01", "T02")
    players = build_players(seed)

    snap_map = {s.snapshot_id: s for s in snapshots}

    moments = key_moments(events)
    ghost_moments = []
    for km in moments:
        if km.moment_type != "high_pressure_final_third_pass":
            continue
        pass_ev = pass_event_for(km, events)
        if pass_ev is None:
            continue
        snap = snap_map.get(pass_ev.snapshot_id)  # snapshot_id non-None per pass_event_for
        if snap is None:
            continue
        twin = score_pass(pass_ev, snap)
        if twin.ghost_shown:
            ghost_moments.append((km, pass_ev, snap, twin))

    if not ghost_moments:
        print(f"ERROR: no ghost-eligible moments found for seed {seed}.", file=sys.stderr)
        sys.exit(1)
    if moment_k < 1 or moment_k > len(ghost_moments):
        print(
            f"ERROR: --moment {moment_k} out of range (1–{len(ghost_moments)}).",
            file=sys.stderr,
        )
        sys.exit(1)

    km, ev, snap, twin = ghost_moments[moment_k - 1]
    packet = build_evidence_packet(km, events, snap, twin, match_id)
    return packet, twin, players, events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description="Run the moment workflow and print the overlay.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--scenario", metavar="ID", help="Hand-designed scenario ID")
    src.add_argument("--seed", type=int, metavar="N", help="Match simulator seed")
    p.add_argument(
        "--moment", type=int, default=1, metavar="K", help="K-th ghost moment (default 1)"
    )
    p.add_argument("--fabric", action="store_true", help="Use FabricKql instead of LocalKql")
    p.add_argument(
        "--force-fail", action="store_true", help="Stub agents sleep past timeout (demos fallback)"
    )
    args = p.parse_args()

    if args.seed is not None and args.scenario is not None:
        p.error("use --scenario OR --seed, not both")

    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    from agents.workflow import run_moment_workflow

    # Build packet, twin and roster
    events: list | None = None
    if args.scenario:
        scenario = _load_scenario(args.scenario)
        packet, twin, roster, ev = _packet_from_scenario(scenario)
        events = [ev]  # event has the KQL-valid match_id
    else:
        packet, twin, roster, events = _packet_from_seed(args.seed, args.moment)

    # Build KQL backend
    if args.fabric:
        from agents.kql_tools import FabricKql

        cluster = _require_env("KQL_CLUSTER_URI")
        database = _require_env("KQL_DATABASE")
        kql = FabricKql(cluster, database)
    else:
        from agents.kql_tools import LocalKql

        kql = LocalKql(events or [])

    # Build agents / client
    if args.force_fail:
        # Stub agents sleep past the timeout so a real TimeoutError fires
        stub = _SleeperAgent()
        _agents: tuple | None = (stub, stub)
        client = None
        timeout_s = 0.5
    else:
        _agents = None
        timeout_s = 30.0
        from agent_framework_foundry import FoundryChatClient
        from azure.identity import AzureCliCredential

        client = FoundryChatClient(
            project_endpoint=_require_env("FOUNDRY_PROJECT_ENDPOINT"),
            model=_require_env("FOUNDRY_MODEL"),
            credential=AzureCliCredential(),
        )

    # Run workflow
    t_start = time.monotonic()
    overlay, log = await run_moment_workflow(
        packet, twin, roster, kql, client, timeout_s=timeout_s, _agents=_agents
    )
    elapsed = round(time.monotonic() - t_start, 3)

    # Print results
    print(json.dumps(overlay.model_dump(by_alias=True, mode="json"), indent=2))
    print()
    print(f"source   : {log['source']}")
    print(f"attempts : {log['attempts']}")
    print(f"seconds  : {elapsed}")
    step_labels = ["investigator", "director_1", "director_2"]
    for label, dur in zip(step_labels, log["durations_s"], strict=False):
        print(f"  {label}: {dur}s")
    if log.get("fallback_reason"):
        print(f"fallback : {log['fallback_reason']}")
    if log.get("errors_attempt1"):
        print(f"errors1  : {log['errors_attempt1']}")
    if log.get("errors_attempt2"):
        print(f"errors2  : {log['errors_attempt2']}")


if __name__ == "__main__":
    main()
