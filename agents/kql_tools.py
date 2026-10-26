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
_MAX_CLOCK_S = 7200  # 120 minutes in seconds


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


def _validate_clock_s(clock_s: int) -> None:
    if not isinstance(clock_s, int) or clock_s < 0 or clock_s > _MAX_CLOCK_S:
        raise ValueError(
            f"clock_s must be an integer 0–{_MAX_CLOCK_S}, got {clock_s!r}"
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

    def live_matches(self) -> list[dict]:
        """Matches that received events in the last 30 minutes.

        Returns list of {match_id, event_count, last_clock_s, last_ingested}.
        """
        ...

    def events_since(self, match_id: str, clock_s: int) -> list[dict]:
        """All events for a match with match_clock_s > clock_s, ascending.

        Returns list of event dicts with same shape as recent_events rows plus
        x, y, end_x, end_y and all other MatchEvent fields.
        """
        ...

    def latest_snapshot(self, match_id: str) -> dict | None:
        """Most recent position snapshot for a match, or None if none exists."""
        ...

    def match_snapshot(self, match_id: str, snapshot_id: str) -> dict | None:
        """A specific snapshot by id, or None if not found."""
        ...


# ---------------------------------------------------------------------------
# FabricKql – live Eventhouse
# ---------------------------------------------------------------------------


class FabricKql:
    """Queries the live Eventhouse via stored functions.

    Uses DefaultAzureCredential so the container's managed identity
    (AZURE_CLIENT_ID) and az login both work without code changes.
    Calls only our stored functions (MatchStats, Momentum, PressureIndex,
    EventsClean). No free-form queries.
    """

    def __init__(self, cluster_uri: str, database: str) -> None:
        self._cluster_uri = cluster_uri
        self._database = database
        self._client = None  # created lazily on first _run, then reused

    def _run(self, query: str) -> list[dict]:
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
                self._cluster_uri, DefaultAzureCredential()
            )
            self._client = KustoClient(kcsb)
        response = self._client.execute(self._database, query)
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

    def live_matches(self) -> list[dict]:
        rows = self._run("LiveMatches()")
        return [
            {
                "match_id": r.get("match_id"),
                "event_count": int(r.get("event_count", 0)),
                "last_clock_s": int(r.get("last_clock_s", 0)),
                "last_ingested": str(r.get("last_ingested", "")),
            }
            for r in rows
        ]

    def events_since(self, match_id: str, clock_s: int) -> list[dict]:
        _validate_match_id(match_id)
        _validate_clock_s(clock_s)
        rows = self._run(f'EventsSince("{match_id}", {clock_s})')
        return [dict(r) for r in rows]

    def latest_snapshot(self, match_id: str) -> dict | None:
        _validate_match_id(match_id)
        rows = self._run(f'LatestSnapshot("{match_id}")')
        if not rows:
            return None
        r = rows[0]
        return {
            "snapshot_id": r.get("snapshot_id"),
            "match_id": r.get("match_id"),
            "match_clock_s": r.get("match_clock_s"),
            "positions": r.get("positions"),
        }

    def match_snapshot(self, match_id: str, snapshot_id: str) -> dict | None:
        _validate_match_id(match_id)
        if not isinstance(snapshot_id, str) or not snapshot_id.startswith("sn_"):
            raise ValueError(
                f"snapshot_id {snapshot_id!r} must start with 'sn_'"
            )
        rows = self._run(f'MatchSnapshot("{match_id}", "{snapshot_id}")')
        if not rows:
            return None
        r = rows[0]
        return {
            "snapshot_id": r.get("snapshot_id"),
            "match_id": r.get("match_id"),
            "match_clock_s": r.get("match_clock_s"),
            "positions": r.get("positions"),
        }


# ---------------------------------------------------------------------------
# LocalKql – local Python (tests and replay)
# ---------------------------------------------------------------------------


class LocalKql:
    """Computes match data locally from a list of MatchEvent objects.

    Identical answers to FabricKql, computed via analytics.metrics.
    No network required; suitable for tests and replay mode.
    """

    def __init__(self, events: list, snapshots: list | None = None) -> None:
        self._events = events
        self._snapshots = snapshots or []

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

    def live_matches(self) -> list[dict]:
        """Local: treat all match_ids as live, reporting last event clock."""
        seen: dict[str, dict] = {}
        for e in self._events:
            mid = e.match_id
            if mid not in seen or e.match_clock_s > seen[mid]["last_clock_s"]:
                seen[mid] = {
                    "match_id": mid,
                    "event_count": 0,
                    "last_clock_s": e.match_clock_s,
                    "last_ingested": "",
                }
            seen[mid]["event_count"] += 1
        return list(seen.values())

    def events_since(self, match_id: str, clock_s: int) -> list[dict]:
        _validate_match_id(match_id)
        _validate_clock_s(clock_s)
        evs = sorted(
            (e for e in self._events if e.match_id == match_id and e.match_clock_s > clock_s),
            key=lambda e: e.match_clock_s,
        )
        return [
            {
                "event_id": e.event_id,
                "match_id": e.match_id,
                "scenario_id": e.scenario_id,
                "seed": e.seed,
                "event_time": e.event_time,
                "match_clock_s": e.match_clock_s,
                "period": e.period,
                "event_type": e.event_type.value,
                "team_id": e.team_id,
                "player_id": e.player_id,
                "possession_id": e.possession_id,
                "x": e.x,
                "y": e.y,
                "end_x": e.end_x,
                "end_y": e.end_y,
                "outcome": e.outcome.value if e.outcome else None,
                "receiver_id": e.receiver_id,
                "pressure_level": e.pressure_level,
                "snapshot_id": e.snapshot_id,
            }
            for e in evs
        ]

    def latest_snapshot(self, match_id: str) -> dict | None:
        _validate_match_id(match_id)
        snaps = getattr(self, "_snapshots", [])
        candidates = [s for s in snaps if s.match_id == match_id]
        if not candidates:
            return None
        best = max(candidates, key=lambda s: s.match_clock_s)
        return {
            "snapshot_id": best.snapshot_id,
            "match_id": best.match_id,
            "match_clock_s": best.match_clock_s,
            "positions": [p.model_dump() for p in best.positions],
        }

    def match_snapshot(self, match_id: str, snapshot_id: str) -> dict | None:
        _validate_match_id(match_id)
        if not isinstance(snapshot_id, str) or not snapshot_id.startswith("sn_"):
            raise ValueError(
                f"snapshot_id {snapshot_id!r} must start with 'sn_'"
            )
        snaps = getattr(self, "_snapshots", [])
        for s in snaps:
            if s.match_id == match_id and s.snapshot_id == snapshot_id:
                return {
                    "snapshot_id": s.snapshot_id,
                    "match_id": s.match_id,
                    "match_clock_s": s.match_clock_s,
                    "positions": [p.model_dump() for p in s.positions],
                }
        return None
