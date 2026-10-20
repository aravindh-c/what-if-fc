"""Read-only KQL tools for the agent workflow.

Two backends share the same KqlBackend protocol:
  FabricKql — queries live Eventhouse stored functions (needs azure-kusto-data + az login)
  LocalKql  — computes from a local event list (tests and replay; no Fabric required)

Validation:
  match_id must match ^match_[A-Za-z0-9_]+$
  minute   must be an integer 0–120
  n        must be an integer 1–10

No free-form KQL is constructed outside this module.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

_MATCH_ID_RE = re.compile(r"^match_[A-Za-z0-9_]+$")
_MAX_RECENT = 10
_MAX_MINUTE = 120


# ---------------------------------------------------------------------------
# Input validators
# ---------------------------------------------------------------------------


def _validate_match_id(match_id: str) -> None:
    if not isinstance(match_id, str) or not _MATCH_ID_RE.match(match_id):
        raise ValueError(
            f"match_id {match_id!r} must match ^match_[A-Za-z0-9_]+$"
        )


def _validate_minute(minute: int) -> None:
    if not isinstance(minute, int) or minute < 0 or minute > _MAX_MINUTE:
        raise ValueError(
            f"minute must be an integer 0–{_MAX_MINUTE}, got {minute!r}"
        )


def _validate_n(n: int) -> None:
    if not isinstance(n, int) or n < 1 or n > _MAX_RECENT:
        raise ValueError(
            f"n must be an integer 1–{_MAX_RECENT}, got {n!r}"
        )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class KqlBackend(Protocol):
    """Read-only access to match data (live Fabric Eventhouse or local Python)."""

    def match_stats(self, match_id: str) -> dict:
        """Per-team pass completion, shots, goals and possession proxy.

        Returns {team_id: {passes, completed_passes, completion_pct,
                           shots, goals, possession_proxy_pct}},
        with float values rounded to 3 dp.
        """
        ...

    def momentum_at(self, match_id: str, minute: int) -> dict:
        """Momentum share per team at the given minute (rolling 5-minute window).

        Returns {team_id: share (0–1, rounded to 3 dp)}.
        """
        ...

    def pressure_at(self, match_id: str, minute: int) -> dict:
        """Pressure index per team at the given minute (rolling 5-minute average).

        Returns {team_id: pressure_index (rounded to 3 dp)}.
        """
        ...

    def recent_events(self, match_id: str, minute: int, n: int = 5) -> list[dict]:
        """The n most recent events up to and including the given minute.

        n is capped at 10.  Returns list of {event_id, match_clock_s,
        event_type, team_id, player_id, outcome} dicts.
        """
        ...


# ---------------------------------------------------------------------------
# FabricKql – live Eventhouse
# ---------------------------------------------------------------------------


class FabricKql:
    """Queries the live Eventhouse via stored functions using Azure CLI auth.

    Calls only our stored functions (MatchStats, Momentum, PressureIndex,
    EventsClean). No free-form queries.
    """

    def __init__(self, cluster_uri: str, database: str) -> None:
        self._cluster_uri = cluster_uri
        self._database = database

    def _run(self, query: str) -> list[dict]:
        from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

        kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(
            self._cluster_uri
        )
        client = KustoClient(kcsb)
        response = client.execute(self._database, query)
        rows: list[dict] = []
        for table in response.primary_results:
            for row in table:
                rows.append(
                    dict(
                        zip(
                            [c.column_name for c in table.columns],
                            row,
                            strict=False,
                        )
                    )
                )
        return rows

    def match_stats(self, match_id: str) -> dict:
        _validate_match_id(match_id)
        rows = self._run(f'MatchStats("{match_id}")')
        return {
            r["team_id"]: {
                "passes": int(r["passes"]),
                "completed_passes": int(r["completed_passes"]),
                "completion_pct": round(float(r["completion_pct"]), 3),
                "shots": int(r["shots"]),
                "goals": int(r["goals"]),
                "possession_proxy_pct": round(float(r["possession_proxy_pct"]), 3),
            }
            for r in rows
        }

    def momentum_at(self, match_id: str, minute: int) -> dict:
        _validate_match_id(match_id)
        _validate_minute(minute)
        rows = self._run(f'Momentum("{match_id}")')
        return {
            r["team_id"]: round(float(r["share"]), 3)
            for r in rows
            if int(r["minute"]) == minute
        }

    def pressure_at(self, match_id: str, minute: int) -> dict:
        _validate_match_id(match_id)
        _validate_minute(minute)
        rows = self._run(f'PressureIndex("{match_id}")')
        return {
            r["team_id"]: round(float(r["pressure_index"]), 3)
            for r in rows
            if int(r["minute"]) == minute
        }

    def recent_events(self, match_id: str, minute: int, n: int = 5) -> list[dict]:
        _validate_match_id(match_id)
        _validate_minute(minute)
        _validate_n(n)
        rows = self._run(
            f'EventsClean() | where match_id == "{match_id}" '
            f"and match_clock_s / 60 <= {minute} "
            f"| order by match_clock_s desc | take {n}"
        )
        return [
            {
                "event_id": r.get("event_id"),
                "match_clock_s": r.get("match_clock_s"),
                "event_type": r.get("event_type"),
                "team_id": r.get("team_id"),
                "player_id": r.get("player_id"),
                "outcome": r.get("outcome"),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# LocalKql – local Python (tests and replay)
# ---------------------------------------------------------------------------


class LocalKql:
    """Computes match data locally from a list of MatchEvent objects.

    Identical answers to FabricKql, computed via analytics.metrics.
    No network required; suitable for tests and replay mode.
    """

    def __init__(self, events: list) -> None:
        self._events = events

    def match_stats(self, match_id: str) -> dict:
        _validate_match_id(match_id)
        from analytics import metrics

        evs = [e for e in self._events if e.match_id == match_id]
        rows = metrics.match_stats(evs)
        return {
            r.team_id: {
                "passes": r.passes,
                "completed_passes": r.completed_passes,
                "completion_pct": round(r.completion_pct, 3),
                "shots": r.shots,
                "goals": r.goals,
                "possession_proxy_pct": round(r.possession_proxy_pct, 3),
            }
            for r in rows
        }

    def momentum_at(self, match_id: str, minute: int) -> dict:
        _validate_match_id(match_id)
        _validate_minute(minute)
        from analytics import metrics

        evs = [e for e in self._events if e.match_id == match_id]
        rows = metrics.momentum(evs)
        return {
            r.team_id: round(r.share, 3)
            for r in rows
            if r.minute == minute
        }

    def pressure_at(self, match_id: str, minute: int) -> dict:
        _validate_match_id(match_id)
        _validate_minute(minute)
        from analytics import metrics

        evs = [e for e in self._events if e.match_id == match_id]
        rows = metrics.pressure_index(evs)
        return {
            r.team_id: round(r.pressure_index, 3)
            for r in rows
            if r.minute == minute
        }

    def recent_events(self, match_id: str, minute: int, n: int = 5) -> list[dict]:
        _validate_match_id(match_id)
        _validate_minute(minute)
        _validate_n(n)
        evs = sorted(
            (
                e
                for e in self._events
                if e.match_id == match_id and e.match_clock_s // 60 <= minute
            ),
            key=lambda e: e.match_clock_s,
            reverse=True,
        )
        return [
            {
                "event_id": e.event_id,
                "match_clock_s": e.match_clock_s,
                "event_type": str(e.event_type),
                "team_id": e.team_id,
                "player_id": e.player_id,
                "outcome": str(e.outcome) if e.outcome else None,
            }
            for e in evs[:n]
        ]
