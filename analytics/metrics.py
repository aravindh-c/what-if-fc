"""Pure-Python reference implementations of the live KQL metrics.

Coordinate rule: x,y are in the frame of the team IN POSSESSION (attacking
towards x=105). Defensive events (pressure, tackle, interception) are recorded
in the possessing team's frame, so for the DEFENDING team "opponent half"
means x < 52.5.

Input for every function: list[MatchEvent] — typically a single match.
Duplicate event_ids are deduplicated before processing (same as KQL EventsClean).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from core.schemas import EventType, MatchEvent, Outcome

# ---------------------------------------------------------------------------
# Constants (mirror the KQL functions exactly)
# ---------------------------------------------------------------------------

_HALF_X: float = 52.5        # boundary for pressure_index (possessing-team frame)
_FINAL_THIRD_X: float = 70.0 # x threshold for attacking actions and final-third events
_ROLL_MINS: int = 5          # rolling-window width in minutes

_POSSESSION_TYPES = frozenset(
    {EventType.PASS, EventType.CARRY, EventType.RECEPTION, EventType.SHOT}
)
_ATTACKING_TYPES = frozenset(
    {EventType.PASS, EventType.CARRY, EventType.SHOT}
)
_PRESSURE_TYPES = frozenset(
    {EventType.PRESSURE, EventType.TACKLE, EventType.INTERCEPTION}
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TeamStats:
    team_id: str
    passes: int
    completed_passes: int
    completion_pct: float   # rounded to 1 decimal
    shots: int
    goals: int
    possession_proxy_pct: float  # rounded to 1 decimal


@dataclass(frozen=True)
class MomentumRow:
    match_id: str
    minute: int
    team_id: str
    share: float  # 0–1 share of attacking actions in the rolling window


@dataclass(frozen=True)
class PressureRow:
    match_id: str
    minute: int
    team_id: str
    pressure_index: float  # rolling-average count per minute


@dataclass(frozen=True)
class KeyMoment:
    moment_id: str
    match_id: str
    match_clock_s: int
    # goal | high_pressure_final_third_pass | final_third_turnover | momentum_swing
    moment_type: str
    team_id: str
    event_id: str
    snapshot_id: str | None
    value: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dedup(events: Sequence[MatchEvent]) -> list[MatchEvent]:
    """Deduplicate by event_id, keeping the first occurrence (stable order)."""
    seen: set[str] = set()
    out: list[MatchEvent] = []
    for ev in events:
        if ev.event_id not in seen:
            seen.add(ev.event_id)
            out.append(ev)
    return out


def _match_id(events: Sequence[MatchEvent]) -> str:
    for ev in events:
        return ev.match_id
    return ""


def _teams(events: Sequence[MatchEvent]) -> list[str]:
    return sorted({ev.team_id for ev in events if ev.team_id is not None})


# ---------------------------------------------------------------------------
# match_stats
# ---------------------------------------------------------------------------


def match_stats(events: Sequence[MatchEvent]) -> list[TeamStats]:
    """Per-team passes, completion %, shots, goals, and possession-proxy %.

    Possession proxy = share of on-ball events (pass, carry, reception, shot)
    per team.  Mirrors KQL MatchStats().
    """
    evs = _dedup(events)

    passes: dict[str, int] = defaultdict(int)
    completed: dict[str, int] = defaultdict(int)
    shots: dict[str, int] = defaultdict(int)
    goals: dict[str, int] = defaultdict(int)
    poss: dict[str, int] = defaultdict(int)

    for ev in evs:
        t = ev.team_id
        if t is None:
            continue
        if ev.event_type == EventType.PASS:
            passes[t] += 1
            if ev.outcome == Outcome.COMPLETE:
                completed[t] += 1
        elif ev.event_type == EventType.SHOT:
            shots[t] += 1
        elif ev.event_type == EventType.GOAL:
            goals[t] += 1
        if ev.event_type in _POSSESSION_TYPES:
            poss[t] += 1

    total_poss = sum(poss.values())
    result: list[TeamStats] = []
    for t in _teams(evs):
        p = passes[t]
        c = completed[t]
        completion = round(100.0 * c / p, 1) if p > 0 else 0.0
        poss_pct = round(100.0 * poss[t] / total_poss, 1) if total_poss > 0 else 0.0
        result.append(
            TeamStats(
                team_id=t,
                passes=p,
                completed_passes=c,
                completion_pct=completion,
                shots=shots[t],
                goals=goals[t],
                possession_proxy_pct=poss_pct,
            )
        )
    return result


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------


def momentum(events: Sequence[MatchEvent]) -> list[MomentumRow]:
    """Per-minute rolling 5-minute share of attacking actions between the two teams.

    Attacking action = pass/carry/shot with x >= 70; shots count 3×.
    Share = team's weighted count / total; 0.5 each when total is zero.
    Mirrors KQL Momentum().
    """
    evs = _dedup(events)
    if not evs:
        return []

    mid = _match_id(evs)
    team_list = _teams(evs)
    attacks: dict[tuple[int, str], float] = defaultdict(float)

    for ev in evs:
        if ev.team_id is None or ev.x is None:
            continue
        if ev.event_type not in _ATTACKING_TYPES:
            continue
        if ev.x < _FINAL_THIRD_X:
            continue
        w = 3.0 if ev.event_type == EventType.SHOT else 1.0
        attacks[(ev.match_clock_s // 60, ev.team_id)] += w

    max_min = max(ev.match_clock_s // 60 for ev in evs)
    n_teams = len(team_list) or 1

    result: list[MomentumRow] = []
    for m in range(max_min + 1):
        w_start = max(0, m - _ROLL_MINS + 1)
        rolling: dict[str, float] = {t: 0.0 for t in team_list}
        for w in range(w_start, m + 1):
            for t in team_list:
                rolling[t] += attacks.get((w, t), 0.0)
        total = sum(rolling.values())
        for t in team_list:
            share = rolling[t] / total if total > 0 else 1.0 / n_teams
            result.append(MomentumRow(match_id=mid, minute=m, team_id=t, share=share))
    return result


# ---------------------------------------------------------------------------
# pressure_index
# ---------------------------------------------------------------------------


def pressure_index(events: Sequence[MatchEvent]) -> list[PressureRow]:
    """Per-minute rolling 5-minute pressure count per team.

    Counts pressure + tackle + interception events by each team where x < 52.5
    (in the possessing team's frame, i.e. the defending team is pressing in the
    possessing team's defensive half).  Averaged over the rolling window.
    Mirrors KQL PressureIndex().
    """
    evs = _dedup(events)
    if not evs:
        return []

    mid = _match_id(evs)
    team_list = _teams(evs)
    press: dict[tuple[int, str], int] = defaultdict(int)

    for ev in evs:
        if ev.team_id is None or ev.x is None:
            continue
        if ev.event_type not in _PRESSURE_TYPES:
            continue
        if ev.x >= _HALF_X:
            continue
        press[(ev.match_clock_s // 60, ev.team_id)] += 1

    max_min = max(ev.match_clock_s // 60 for ev in evs)

    result: list[PressureRow] = []
    for m in range(max_min + 1):
        w_start = max(0, m - _ROLL_MINS + 1)
        window_size = m - w_start + 1
        for t in team_list:
            total = sum(press.get((w, t), 0) for w in range(w_start, m + 1))
            result.append(
                PressureRow(
                    match_id=mid,
                    minute=m,
                    team_id=t,
                    pressure_index=round(total / window_size, 3),
                )
            )
    return result


# ---------------------------------------------------------------------------
# key_moments
# ---------------------------------------------------------------------------


def key_moments(events: Sequence[MatchEvent]) -> list[KeyMoment]:
    """Detect the four key moment types.

    moment_type values and trigger conditions:
      goal                       – EventType.GOAL
      high_pressure_final_third_pass
                                 – pass, x >= 70, pressure_level >= 0.5, snapshot_id set
      final_third_turnover       – tackle/interception won, x >= 70 (possessing-team frame)
      momentum_swing             – first minute where the rolling-window momentum leader
                                   changes and the new leader's share >= 0.60

    Mirrors KQL KeyMoments().
    """
    evs = _dedup(events)
    if not evs:
        return []

    mid = _match_id(evs)
    moments: list[KeyMoment] = []

    for ev in evs:
        t = ev.team_id
        if t is None:
            continue

        if ev.event_type == EventType.GOAL:
            moments.append(
                KeyMoment(
                    moment_id=f"km_{ev.event_id}",
                    match_id=mid,
                    match_clock_s=ev.match_clock_s,
                    moment_type="goal",
                    team_id=t,
                    event_id=ev.event_id,
                    snapshot_id=ev.snapshot_id,
                    value=1.0,
                )
            )

        elif (
            ev.event_type == EventType.PASS
            and ev.x is not None
            and ev.x >= _FINAL_THIRD_X
            and ev.pressure_level >= 0.5
            and ev.snapshot_id is not None
        ):
            moments.append(
                KeyMoment(
                    moment_id=f"km_{ev.event_id}",
                    match_id=mid,
                    match_clock_s=ev.match_clock_s,
                    moment_type="high_pressure_final_third_pass",
                    team_id=t,
                    event_id=ev.event_id,
                    snapshot_id=ev.snapshot_id,
                    value=ev.pressure_level,
                )
            )

        elif (
            ev.event_type in {EventType.TACKLE, EventType.INTERCEPTION}
            and ev.outcome == Outcome.WON
            and ev.x is not None
            and ev.x >= _FINAL_THIRD_X
        ):
            moments.append(
                KeyMoment(
                    moment_id=f"km_{ev.event_id}",
                    match_id=mid,
                    match_clock_s=ev.match_clock_s,
                    moment_type="final_third_turnover",
                    team_id=t,
                    event_id=ev.event_id,
                    snapshot_id=ev.snapshot_id,
                    value=float(ev.x),
                )
            )

    # Momentum swing: track the last team to hold >= 0.60 share; fire when it changes.
    mom_rows = momentum(evs)
    if mom_rows:
        min_to_rows: dict[int, list[MomentumRow]] = defaultdict(list)
        for row in mom_rows:
            min_to_rows[row.minute].append(row)

        # Index events by minute for picking a representative event_id
        evs_by_minute: dict[int, list[MatchEvent]] = defaultdict(list)
        for ev in evs:
            if ev.team_id is not None:
                evs_by_minute[ev.match_clock_s // 60].append(ev)

        prev_leader: str | None = None
        for m in sorted(min_to_rows.keys()):
            best = max(min_to_rows[m], key=lambda r: r.share)
            if best.share < 0.60:
                continue  # no dominant leader; keep prev_leader unchanged
            leader = best.team_id
            if prev_leader is not None and leader != prev_leader:
                rep = next(
                    (e for e in evs_by_minute.get(m, []) if e.team_id == leader),
                    evs_by_minute.get(m, [None])[0],  # type: ignore[index]
                )
                if rep is not None:
                    moments.append(
                        KeyMoment(
                            moment_id=f"km_swing_{mid}_{m * 60}",
                            match_id=mid,
                            match_clock_s=m * 60,
                            moment_type="momentum_swing",
                            team_id=leader,
                            event_id=rep.event_id,
                            snapshot_id=rep.snapshot_id,
                            value=round(best.share, 3),
                        )
                    )
            prev_leader = leader

    moments.sort(key=lambda km: km.match_clock_s)
    return moments
