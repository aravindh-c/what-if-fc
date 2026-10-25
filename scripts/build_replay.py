"""Build a self-contained replay bundle for one match or scenario.

Usage:
    python -m scripts.build_replay                  # seeded match + 4 scenarios, no agents
    python -m scripts.build_replay --no-agents       # same (explicit)
    python -m scripts.build_replay --agents          # run agents for ghost moments
    python -m scripts.build_replay --upload          # build then upload to Blob storage

Output:
    data/replay/<replay_id>.json   (git-ignored)

Bundle schema (all dict keys use camelCase aliases via model_dump(by_alias=True)):
{
  "meta": {
    "replay_id", "kind" ("match"|"scenario"), "title",
    "teams": {team_id: {name, short_name, formation, style}},
    "players": {player_id: {name, role, team_id}},
    "built_at", "twin_version"
  },
  "events":    [MatchEvent …],
  "snapshots": [PositionSnapshot …],
  "metrics": {
    "match_stats": [{team_id, passes, …}],
    "momentum":    [{minute, team_id, share}],
    "pressure":    [{minute, team_id, pressure_index}]
  },
  "headline_moments": [{moment_id, moment_type, match_clock_s, event_id, score, …}],
  "overlays":  [Overlay …]
}
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agents.moments import NoOpAgent as _NoOpAgent
from agents.moments import build_ledger as _build_ledger
from agents.moments import make_goal_twin as _make_goal_twin
from agents.moments import overlay_id as _overlay_id

# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _metrics_bundle(events: list) -> dict[str, Any]:
    from analytics.metrics import match_stats, momentum, pressure_index

    ms = [dataclasses.asdict(s) for s in match_stats(events)]
    mom = [
        {"minute": r.minute, "team_id": r.team_id, "share": r.share}
        for r in momentum(events)
    ]
    pres = [
        {"minute": r.minute, "team_id": r.team_id, "pressure_index": r.pressure_index}
        for r in pressure_index(events)
    ]
    return {"match_stats": ms, "momentum": mom, "pressure": pres}


# ---------------------------------------------------------------------------
# Overlay runner
# ---------------------------------------------------------------------------


async def _run_overlay(
    packet,
    twin,
    roster: list,
    events: list,
    *,
    use_agents: bool,
    client: Any,
    timeout_s: float,
) -> tuple[Any, dict]:
    from agents.kql_tools import LocalKql
    from agents.workflow import run_moment_workflow

    kql = LocalKql(events)
    overlay, log = await run_moment_workflow(
        packet,
        twin,
        roster,
        kql,
        client if use_agents else None,
        timeout_s=timeout_s,
        _agents=None if use_agents else (_NoOpAgent(), _NoOpAgent()),
    )
    if not use_agents and log.get("source") == "template":
        log = {**log, "fallback_reason": "agents were not run for this build"}
    return overlay, log


# ---------------------------------------------------------------------------
# Match replay builder
# ---------------------------------------------------------------------------


def _build_match_replay(seed: int, home_id: str, away_id: str) -> dict[str, Any]:
    from analytics.evidence import build_evidence_packet
    from analytics.metrics import key_moments, pass_event_for
    from analytics.tactical_twin import score_pass
    from simulator.ids import make_match_id
    from simulator.reference_data import build_players, build_teams
    from simulator.run import run_match

    match_id, events, snapshots = run_match(seed, home_id, away_id)
    players = build_players(seed)
    teams = {t.team_id: t for t in build_teams()}

    snap_map = {s.snapshot_id: s for s in snapshots}
    moments = key_moments(events)

    meta = {
        "replay_id": make_match_id(seed, home_id, away_id),
        "kind": "match",
        "title": f"{teams[home_id].name} vs {teams[away_id].name} (seed {seed})",
        "teams": {
            t.team_id: {
                "name": t.name,
                "short_name": t.short_name,
                "formation": t.formation,
                "style": t.style,
            }
            for t in (teams[home_id], teams[away_id])
        },
        "players": {
            p.player_id: {
                "name": p.name,
                "role": p.role,
                "team_id": p.team_id,
                "shirt_number": p.shirt_number,
            }
            for p in players
        },
        "built_at": datetime.now(UTC).isoformat(),
        "twin_version": "twin-v1",
    }

    n_skipped = 0
    ghost_moments: list[tuple] = []
    goal_moments: list[tuple] = []
    for km in moments:
        if km.ghost_eligible:
            pass_ev = pass_event_for(km, events)
            if pass_ev is None:
                n_skipped += 1
                continue
            snap = snap_map.get(pass_ev.snapshot_id)  # snapshot_id non-None per pass_event_for
            if snap is None:
                n_skipped += 1
                continue
            twin = score_pass(pass_ev, snap)
            if twin.ghost_shown:
                packet = build_evidence_packet(km, events, snap, twin, match_id)
                ghost_moments.append((km, pass_ev, snap, twin, packet))
        elif km.moment_type == "goal":
            ev = next((e for e in events if e.event_id == km.event_id), None)
            if ev is None or ev.player_id is None:
                continue
            goal_twin = _make_goal_twin(ev.player_id)
            packet = build_evidence_packet(km, events, None, goal_twin, match_id)
            goal_moments.append((km, goal_twin, packet))

    return {
        "_meta": meta,
        "_events": events,
        "_snapshots": snapshots,
        "_moments": moments,
        "_ghost_moments": ghost_moments,
        "_goal_moments": goal_moments,
        "_players": players,
        "_match_id": match_id,
        "_n_skipped": n_skipped,
    }


# ---------------------------------------------------------------------------
# Scenario replay builder
# ---------------------------------------------------------------------------


def _build_scenario_replay(scenario_id: str) -> dict[str, Any]:
    from analytics.evidence import EvidencePacket, LiveMetrics
    from analytics.tactical_twin import pass_difficulty as _pass_difficulty
    from analytics.tactical_twin import score_pass
    from simulator.reference_data import build_players, build_teams
    from simulator.scenarios import _build_scenarios  # noqa: PLC2701

    scenarios = _build_scenarios()
    scen = next((s for s in scenarios if s.scenario_id == scenario_id), None)
    if scen is None:
        raise ValueError(f"scenario {scenario_id!r} not found")

    players = build_players(7)
    teams = {t.team_id: t for t in build_teams()}

    match_id = f"match_demo_{scenario_id}"
    ev = scen.actual_pass.model_copy(update={"match_id": match_id})
    snap = scen.snapshot.model_copy(update={"match_id": match_id})

    twin = score_pass(ev, snap)

    minute = ev.match_clock_s // 60
    live = LiveMetrics(
        minute=minute,
        momentum_share={},
        pressure_index={},
        scoreline={"T01": 0, "T02": 0},
    )

    actual_cand = next((c for c in twin.candidates if c.get("is_actual")), None)
    ghost_cand = (
        next(
            (c for c in twin.candidates if c.get("player_id") == twin.best_alt_player_id),
            None,
        )
        if twin.ghost_shown
        else None
    )

    opp_positions = [p for p in snap.positions if p.team_id != ev.team_id]
    if ev.x is not None and ev.y is not None and ev.end_x is not None and ev.end_y is not None:
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
        label="heuristic tactical option score, not a probability",
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

    t01, t02 = teams.get("T01"), teams.get("T02")
    meta = {
        "replay_id": f"scenario_{scenario_id}",
        "kind": "scenario",
        "title": scen.title,
        "scenario_description": scen.description,
        "scenario_why": scen.why,
        "teams": {
            t.team_id: {
                "name": t.name,
                "short_name": t.short_name,
                "formation": t.formation,
                "style": t.style,
            }
            for t in [t01, t02]
            if t is not None
        },
        "players": {
            p.player_id: {
                "name": p.name,
                "role": p.role,
                "team_id": p.team_id,
                "shirt_number": p.shirt_number,
            }
            for p in players
        },
        "built_at": datetime.now(UTC).isoformat(),
        "twin_version": twin.version,
    }

    from analytics.metrics import KeyMoment  # noqa: PLC0415

    km = KeyMoment(
        moment_id=f"km_{ev.event_id}",
        match_id=match_id,
        match_clock_s=ev.match_clock_s,
        moment_type="high_pressure_final_third_pass",
        team_id=ev.team_id or "T01",
        event_id=ev.event_id,
        snapshot_id=snap.snapshot_id,
        source_event_id=None,
        value=0.7,
        score=0.7,
        ghost_eligible=twin.ghost_shown,
    )

    return {
        "_meta": meta,
        "_events": [ev],
        "_snapshots": [snap],
        "_moments": [km] if twin.ghost_shown else [],
        "_ghost_moments": [(km, ev, snap, twin, packet)] if twin.ghost_shown else [],
        "_players": players,
        "_match_id": match_id,
    }


# ---------------------------------------------------------------------------
# Assemble bundle (run overlays async)
# ---------------------------------------------------------------------------


async def _assemble_bundle(
    data: dict[str, Any],
    *,
    use_agents: bool,
    client: Any,
    timeout_s: float,
) -> tuple[dict[str, Any], dict[str, int]]:
    meta = data["_meta"]
    events = data["_events"]
    snapshots = data["_snapshots"]
    moments = data["_moments"]
    ghost_moments = data["_ghost_moments"]
    goal_moments = data.get("_goal_moments", [])
    players = data["_players"]

    # Run overlays for ghost-eligible moments
    overlays_json: list[dict] = []
    ledger_inputs: list[tuple[str, Any, Any, dict]] = []  # (ov_id, packet, twin, log)
    n_agent = 0
    n_template = 0

    for km, _ev, _snap, _twin, packet in ghost_moments:
        ov_id = _overlay_id(meta["replay_id"], km.event_id)
        overlay, log = await _run_overlay(
            packet,
            _twin,
            players,
            events,
            use_agents=use_agents,
            client=client,
            timeout_s=timeout_s,
        )
        ov_dict = overlay.model_dump(by_alias=True, mode="json")
        ov_dict["overlay_id"] = ov_id
        overlays_json.append(ov_dict)
        ledger_inputs.append((ov_id, packet, _twin, log))
        if log.get("source") == "agent":
            n_agent += 1
        else:
            n_template += 1

    # Run overlays for goal moments
    n_goal = 0
    for km, _twin, packet in goal_moments:
        ov_id = _overlay_id(meta["replay_id"], km.event_id)
        overlay, log = await _run_overlay(
            packet,
            _twin,
            players,
            events,
            use_agents=use_agents,
            client=client,
            timeout_s=timeout_s,
        )
        ov_dict = overlay.model_dump(by_alias=True, mode="json")
        ov_dict["overlay_id"] = ov_id
        overlays_json.append(ov_dict)
        ledger_inputs.append((ov_id, packet, _twin, log))
        n_goal += 1

    # Build possession-frame lookup for the frontend coordinate transform.
    # snapshots: team_id of the event that references each snapshot (possessing team).
    # overlays: team_id of the pass / goal event (first event_id in evidence).
    events_by_id: dict[str, Any] = {e.event_id: e for e in events}
    snap_team: dict[str, str] = {}
    for ev in events:
        if ev.snapshot_id and ev.team_id:
            snap_team[ev.snapshot_id] = ev.team_id
    ov_team: dict[str, str] = {}
    for ov_dict in overlays_json:
        ov_id = ov_dict["overlay_id"]
        ev_ids_list = ov_dict.get("evidence", {}).get("event_ids", [])
        if ev_ids_list:
            src_ev = events_by_id.get(ev_ids_list[0])
            if src_ev is not None and src_ev.team_id:
                ov_team[ov_id] = src_ev.team_id

    ledgers: dict[str, Any] = {
        ov_id: _build_ledger(packet, twin, players, events, log)
        for ov_id, packet, twin, log in ledger_inputs
    }

    bundle: dict[str, Any] = {
        "meta": meta,
        "events": [e.model_dump(by_alias=True, mode="json") for e in events],
        "snapshots": [s.model_dump(by_alias=True, mode="json") for s in snapshots],
        "metrics": _metrics_bundle(events),
        "headline_moments": [dataclasses.asdict(km) for km in moments],
        "overlays": overlays_json,
        "frames": {"snapshots": snap_team, "overlays": ov_team},
        "ledgers": ledgers,
    }

    counts = {
        "events": len(events),
        "snapshots": len(snapshots),
        "overlays_agent": n_agent,
        "overlays_template": n_template,
        "overlays_goal": n_goal,
        "skipped": data.get("_n_skipped", 0),
    }
    return bundle, counts


# ---------------------------------------------------------------------------
# Upload to Blob
# ---------------------------------------------------------------------------


def _upload_blob(replay_id: str, content: bytes) -> str:
    import os

    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    account_url = os.environ["REPLAY_STORAGE_ACCOUNT_URL"]
    container = os.environ.get("REPLAY_CONTAINER", "replays")
    credential = DefaultAzureCredential()
    client = BlobServiceClient(account_url=account_url, credential=credential)
    blob_name = f"{replay_id}.json"
    blob_client = client.get_blob_client(container=container, blob=blob_name)
    blob_client.upload_blob(content, overwrite=True)
    return f"{account_url}/{container}/{blob_name}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _main(args: argparse.Namespace) -> None:
    use_agents = args.agents
    client: Any = None
    timeout_s = 30.0

    if use_agents:
        from agent_framework_foundry import FoundryChatClient
        from azure.identity import AzureCliCredential

        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),
        )

    out_dir = Path("data/replay")
    out_dir.mkdir(parents=True, exist_ok=True)

    # (replay_id, events, snapshots, ov_agent, ov_template, ov_goal, skipped, size_bytes)
    replays: list[tuple[str, int, int, int, int, int, int, int]] = []

    # Seeded match
    match_data = _build_match_replay(7, "T01", "T02")
    match_bundle, match_counts = await _assemble_bundle(
        match_data, use_agents=use_agents, client=client, timeout_s=timeout_s
    )
    replay_id = match_data["_meta"]["replay_id"]
    out_path = out_dir / f"{replay_id}.json"
    content = json.dumps(match_bundle, indent=2).encode()
    out_path.write_bytes(content)
    if args.upload:
        _upload_blob(replay_id, content)
    replays.append((
        replay_id,
        match_counts["events"],
        match_counts["snapshots"],
        match_counts["overlays_agent"],
        match_counts["overlays_template"],
        match_counts["overlays_goal"],
        match_counts["skipped"],
        len(content),
    ))

    # Scenarios
    from simulator.scenarios import _build_scenarios  # noqa: PLC2701

    scenario_ids = [s.scenario_id for s in _build_scenarios()]
    for sid in scenario_ids:
        scen_data = _build_scenario_replay(sid)
        scen_bundle, scen_counts = await _assemble_bundle(
            scen_data, use_agents=use_agents, client=client, timeout_s=timeout_s
        )
        replay_id = scen_data["_meta"]["replay_id"]
        out_path = out_dir / f"{replay_id}.json"
        content = json.dumps(scen_bundle, indent=2).encode()
        out_path.write_bytes(content)
        if args.upload:
            _upload_blob(replay_id, content)
        replays.append((
            replay_id,
            scen_counts["events"],
            scen_counts["snapshots"],
            scen_counts["overlays_agent"],
            scen_counts["overlays_template"],
            scen_counts["overlays_goal"],
            scen_counts["skipped"],
            len(content),
        ))

    # Summary table
    col_w = max(len(r[0]) for r in replays) + 2
    header = (
        f"{'replay_id':<{col_w}} {'events':>7} {'snaps':>6}"
        f" {'ov_agent':>9} {'ov_tmpl':>8} {'ov_goal':>7} {'skipped':>8} {'size_kb':>8}"
    )
    print(header)
    print("-" * len(header))
    for r_id, ev_n, sn_n, ov_a, ov_t, ov_g, sk, sz in replays:
        print(
            f"{r_id:<{col_w}} {ev_n:>7} {sn_n:>6}"
            f" {ov_a:>9} {ov_t:>8} {ov_g:>7} {sk:>8} {sz // 1024:>7}K"
        )


def main() -> None:
    load_dotenv()

    p = argparse.ArgumentParser(description="Build replay bundles for all matches and scenarios.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--no-agents",
        dest="agents",
        action="store_false",
        default=False,
        help="Use template fallback only (default, free, offline)",
    )
    mode.add_argument(
        "--agents",
        dest="agents",
        action="store_true",
        help="Run agents for ghost-eligible moments",
    )
    p.add_argument("--upload", action="store_true", help="Upload bundles to Azure Blob storage")
    args = p.parse_args()

    if args.upload and not os.environ.get("REPLAY_STORAGE_ACCOUNT_URL", "").strip():
        print(
            "error: --upload requires REPLAY_STORAGE_ACCOUNT_URL to be set"
            " in the environment or .env file",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.agents:
        missing = [
            v for v in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL")
            if not os.environ.get(v, "").strip()
        ]
        if missing:
            for v in missing:
                print(
                    f"error: --agents requires {v} to be set"
                    " in the environment or .env file",
                    file=sys.stderr,
                )
            sys.exit(1)

    t0 = time.monotonic()
    asyncio.run(_main(args))
    elapsed = round(time.monotonic() - t0, 1)
    print(f"\nDone in {elapsed}s")


if __name__ == "__main__":
    main()
