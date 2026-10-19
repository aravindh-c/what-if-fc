"""Compare live KQL function results against the Python reference metrics.

Usage:
    python scripts/check_kql.py --match-id match_s7_T01_T02 \\
        --seed 7 --home T01 --away T02

Environment variables (loaded from .env):
    KQL_CLUSTER_URI   – e.g. https://whatif.eastus.kusto.windows.net
    KQL_DATABASE      – e.g. whatif

Authentication: Azure CLI (az login must be run first).

The script never prints secrets.  It exits 0 if all checks pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# KQL helpers
# ---------------------------------------------------------------------------

def _kusto_client(cluster_uri: str):  # type: ignore[return]
    from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

    kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(cluster_uri)
    return KustoClient(kcsb)


def _run_kql(client, database: str, query: str) -> list[dict[str, Any]]:  # type: ignore[return]
    response = client.execute(database, query)
    rows = []
    for table in response.primary_results:
        for row in table:
            rows.append(dict(zip([c.column_name for c in table.columns], row, strict=False)))
    return rows


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

_TOL = 0.1  # tolerance for percentage comparisons


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _TOL


def _check_match_stats(kql_rows: list[dict], py_rows) -> list[str]:  # type: ignore[type-arg]
    from analytics.metrics import TeamStats

    failures: list[str] = []
    py_by_team: dict[str, TeamStats] = {s.team_id: s for s in py_rows}

    for row in kql_rows:
        t = row["team_id"]
        if t not in py_by_team:
            failures.append(f"match_stats: KQL team {t} not in Python output")
            continue
        py = py_by_team[t]
        checks = [
            ("passes",            row["passes"],            py.passes),
            ("completed_passes",  row["completed_passes"],  py.completed_passes),
            ("completion_pct",    row["completion_pct"],    py.completion_pct),
            ("shots",             row["shots"],             py.shots),
            ("goals",             row["goals"],             py.goals),
            ("possession_proxy_pct", row["possession_proxy_pct"], py.possession_proxy_pct),
        ]
        for name, kql_val, py_val in checks:
            if isinstance(kql_val, float) or isinstance(py_val, float):
                ok = _close(float(kql_val), float(py_val))
            else:
                ok = kql_val == py_val
            if not ok:
                failures.append(
                    f"match_stats {t}.{name}: KQL={kql_val} vs Python={py_val}"
                )
    return failures


def _check_momentum(kql_rows: list[dict], py_rows) -> list[str]:  # type: ignore[type-arg]

    failures: list[str] = []
    py_idx = {(r.minute, r.team_id): r.share for r in py_rows}

    for row in kql_rows:
        key = (int(row["minute"]), row["team_id"])
        kql_share = float(row["share"])
        if key not in py_idx:
            continue  # KQL may produce fewer rows (no gap-fill); not a failure
        py_share = py_idx[key]
        if not _close(kql_share, py_share):
            failures.append(
                f"momentum min={key[0]} {key[1]}: KQL={kql_share:.3f} vs Python={py_share:.3f}"
            )
    return failures


def _check_pressure(kql_rows: list[dict], py_rows) -> list[str]:  # type: ignore[type-arg]
    failures: list[str] = []
    py_idx = {(r.minute, r.team_id): r.pressure_index for r in py_rows}

    for row in kql_rows:
        key = (int(row["minute"]), row["team_id"])
        kql_val = float(row["pressure_index"])
        if key not in py_idx:
            continue
        py_val = py_idx[key]
        if not _close(kql_val, py_val):
            failures.append(
                f"pressure min={key[0]} {key[1]}: KQL={kql_val:.3f} vs Python={py_val:.3f}"
            )
    return failures


def _check_key_moments(kql_rows: list[dict], py_rows) -> list[str]:  # type: ignore[type-arg]
    failures: list[str] = []
    py_types = {k.moment_type for k in py_rows}

    for t in py_types:
        py_count = sum(1 for k in py_rows if k.moment_type == t)
        kql_count = sum(1 for r in kql_rows if r["moment_type"] == t)
        if py_count != kql_count:
            failures.append(
                f"key_moments {t}: KQL={kql_count} vs Python={py_count}"
            )
    return failures


def _check_headline_moments(kql_rows: list[dict], py_rows) -> list[str]:  # type: ignore[type-arg]
    failures: list[str] = []
    kql_count = len(kql_rows)
    py_count = len(py_rows)
    if kql_count != py_count:
        failures.append(f"headline_moments total: KQL={kql_count} vs Python={py_count}")
    # Verify all Python goals appear in KQL output
    py_goal_ids = {k.event_id for k in py_rows if k.moment_type == "goal"}
    kql_goal_ids = {r["event_id"] for r in kql_rows if r.get("moment_type") == "goal"}
    missing = py_goal_ids - kql_goal_ids
    if missing:
        failures.append(f"headline_moments: goals missing in KQL output: {missing}")
    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare KQL functions against Python metrics.")
    p.add_argument("--match-id", required=True, help="match_id to query")
    p.add_argument("--seed",     type=int, default=7)
    p.add_argument("--home",     default="T01")
    p.add_argument("--away",     default="T02")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import os

    args = _parse_args(argv)
    cluster_uri = os.getenv("KQL_CLUSTER_URI", "").strip()
    database    = os.getenv("KQL_DATABASE",    "").strip()

    if not cluster_uri or not database:
        print(
            "ERROR: KQL_CLUSTER_URI and KQL_DATABASE must be set in the environment.",
            file=sys.stderr,
        )
        return 1

    # --- Python reference -------------------------------------------------
    from analytics.metrics import (
        headline_moments,
        key_moments,
        match_stats,
        momentum,
        pressure_index,
    )
    from simulator.engine import MatchEngine
    from simulator.reference_data import build_players, build_teams

    teams = {t.team_id: t for t in build_teams()}
    players = build_players(args.seed)
    engine = MatchEngine(
        home_team=teams[args.home],
        away_team=teams[args.away],
        players=players,
        seed=args.seed,
        match_id=args.match_id,
        scenario_id="live",
    )
    events, _ = engine.run()

    py_stats     = match_stats(events)
    py_momentum  = momentum(events)
    py_pressure  = pressure_index(events)
    py_moments   = key_moments(events)
    py_headlines = headline_moments(events)

    # --- KQL queries -------------------------------------------------------
    client = _kusto_client(cluster_uri)
    mid = args.match_id

    kql_stats     = _run_kql(client, database, f'MatchStats("{mid}")')
    kql_momentum  = _run_kql(client, database, f'Momentum("{mid}")')
    kql_pressure  = _run_kql(client, database, f'PressureIndex("{mid}")')
    kql_moments   = _run_kql(client, database, f'KeyMoments("{mid}")')
    kql_headlines = _run_kql(client, database, f'HeadlineMoments("{mid}")')

    # --- Comparison --------------------------------------------------------
    all_failures: list[str] = []
    checks = [
        ("match_stats",      _check_match_stats(kql_stats,        py_stats)),
        ("momentum",         _check_momentum(kql_momentum,        py_momentum)),
        ("pressure_index",   _check_pressure(kql_pressure,        py_pressure)),
        ("key_moments",      _check_key_moments(kql_moments,      py_moments)),
        ("headline_moments", _check_headline_moments(kql_headlines, py_headlines)),
    ]

    for name, failures in checks:
        status = "PASS" if not failures else "FAIL"
        print(f"  {status}  {name}")
        for f in failures:
            print(f"        {f}")
        all_failures.extend(failures)

    if all_failures:
        print(f"\n{len(all_failures)} check(s) failed.")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
