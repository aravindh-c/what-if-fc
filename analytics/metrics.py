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
_HPFTP_X: float = 80.0       # high_pressure_final_third_pass x threshold
_HPFTP_PRESSURE: float = 0.6 # high_pressure_final_third_pass pressure threshold
_FTT_X: float = 80.0         # final_third_turnover x threshold
_SWING_MIN_MINUTE: int = 8    # momentum_swing ignored before this minute
_SWING_CONFIRM_MINS: int = 3  # consecutive minutes new leader must hold ≥0.60 to confirm
_SWING_SCORE: float = 0.55    # headline score for a confirmed momentum swing

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
    # for pass-caused FTT: preceding incomplete pass's event_id (and its snapshot)
    source_event_id: str | None
    value: float
    score: float  # 0–1 heuristic importance; not a probability
    # True when snapshot_id is set and moment is a pass or a pass-caused turnover
    ghost_eligible: bool


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


def _km_score(moment_type: str, pressure_level: float, x: float) -> float:
    """Heuristic importance score 0–1 for a key moment candidate."""
    if moment_type == "goal":
        return 1.0
    if moment_type == "momentum_swing":
        return _SWING_SCORE
    if moment_type == "high_pressure_final_third_pass":
        return min(1.0, max(0.0, 0.3 + 0.4 * pressure_level + 0.3 * ((x - 80.0) / 25.0)))
    if moment_type == "final_third_turnover":
        return min(1.0, max(0.0, 0.4 + 0.4 * ((x - 80.0) / 25.0)))
    return 0.0


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
                                 – pass, x >= 80, pressure_level >= 0.6, snapshot_id set
      final_third_turnover       – tackle/interception won, x >= 80 (possessing-team frame)
      momentum_swing             – leader changes, new leader share >= 0.60, minute >= 8

    Mirrors KQL KeyMoments().
    """
    evs = _dedup(events)
    if not evs:
        return []

    mid = _match_id(evs)
    moments: list[KeyMoment] = []

    for i, ev in enumerate(evs):
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
                    source_event_id=None,
                    value=1.0,
                    score=1.0,
                    ghost_eligible=False,
                )
            )

        elif (
            ev.event_type == EventType.PASS
            and ev.x is not None
            and ev.x >= _HPFTP_X
            and ev.pressure_level >= _HPFTP_PRESSURE
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
                    source_event_id=None,
                    value=ev.pressure_level,
                    score=_km_score("high_pressure_final_third_pass", ev.pressure_level, ev.x),
                    ghost_eligible=True,  # snapshot_id always set for HPFTP
                )
            )

        elif (
            ev.event_type in {EventType.TACKLE, EventType.INTERCEPTION}
            and ev.outcome == Outcome.WON
            and ev.x is not None
            and ev.x >= _FTT_X
        ):
            # Attach the preceding incomplete pass by the other team when present
            src_id: str | None = None
            ftt_snap: str | None = ev.snapshot_id
            for j in range(i - 1, -1, -1):
                prev_ev = evs[j]
                if prev_ev.team_id is None:
                    continue  # skip team-less events (period_end etc.)
                if (
                    prev_ev.event_type == EventType.PASS
                    and prev_ev.outcome == Outcome.INCOMPLETE
                    and prev_ev.team_id != t
                ):
                    src_id = prev_ev.event_id
                    ftt_snap = prev_ev.snapshot_id
                break  # stop at the first event that has a team_id
            ghost_el = src_id is not None and ftt_snap is not None
            moments.append(
                KeyMoment(
                    moment_id=f"km_{ev.event_id}",
                    match_id=mid,
                    match_clock_s=ev.match_clock_s,
                    moment_type="final_third_turnover",
                    team_id=t,
                    event_id=ev.event_id,
                    snapshot_id=ftt_snap,
                    source_event_id=src_id,
                    value=float(ev.x),
                    score=_km_score("final_third_turnover", 0.0, ev.x),
                    ghost_eligible=ghost_el,
                )
            )

    # Momentum swing: new leader must hold >= 0.60 for _SWING_CONFIRM_MINS consecutive
    # minutes before a swing is fired (at the last confirming minute).
    mom_rows = momentum(evs)
    if mom_rows:
        min_to_rows: dict[int, list[MomentumRow]] = defaultdict(list)
        for row in mom_rows:
            min_to_rows[row.minute].append(row)

        # Index events by minute (only team-owned events) for picking a representative
        evs_by_minute: dict[int, list[MatchEvent]] = defaultdict(list)
        for ev in evs:
            if ev.team_id is not None:
                evs_by_minute[ev.match_clock_s // 60].append(ev)

        prev_confirmed_leader: str | None = None
        streak_team: str | None = None
        streak_count: int = 0

        for m in sorted(min_to_rows.keys()):
            best = max(min_to_rows[m], key=lambda r: r.share)
            cur_leader = best.team_id if best.share >= 0.60 else None

            if cur_leader == streak_team and cur_leader is not None:
                streak_count += 1
            else:
                streak_team = cur_leader
                streak_count = 1 if cur_leader is not None else 0

            if streak_count == _SWING_CONFIRM_MINS and streak_team is not None:
                if (
                    m >= _SWING_MIN_MINUTE
                    and prev_confirmed_leader is not None
                    and streak_team != prev_confirmed_leader
                ):
                    # Search back up to _ROLL_MINS minutes for a team event to represent
                    rep: MatchEvent | None = None
                    for sm in range(m, max(-1, m - _ROLL_MINS), -1):
                        for e in evs_by_minute.get(sm, []):
                            if e.team_id == streak_team:
                                rep = e
                                break
                        if rep is not None:
                            break
                    if rep is None:
                        any_evs = evs_by_minute.get(m, [])
                        rep = any_evs[0] if any_evs else None
                    if rep is not None:
                        moments.append(
                            KeyMoment(
                                moment_id=f"km_swing_{mid}_{m * 60}",
                                match_id=mid,
                                match_clock_s=m * 60,
                                moment_type="momentum_swing",
                                team_id=streak_team,
                                event_id=rep.event_id,
                                snapshot_id=rep.snapshot_id,
                                source_event_id=None,
                                value=round(best.share, 3),
                                score=_SWING_SCORE,
                                ghost_eligible=False,
                            )
                        )
                # Always record this team as the confirmed leader (even if no swing fired)
                prev_confirmed_leader = streak_team

    moments.sort(key=lambda km: km.match_clock_s)
    return moments


# ---------------------------------------------------------------------------
# headline_moments
# ---------------------------------------------------------------------------


_SWING_CAP: int = 3          # max momentum_swings kept per headline list
_GHOST_RESERVE: int = 5      # slots reserved for ghost_eligible moments when supply >= 5


def headline_moments(
    events: Sequence[MatchEvent], window_s: int = 180, cap: int = 12
) -> list[KeyMoment]:
    """Select the most important key moments for display.

    Selection rules (mirrors KQL HeadlineMoments()):
      1. All goals always included.
      2. Non-goals are window-deduplicated (best score per bin(match_clock_s, window_s);
         ties broken by earlier match_clock_s).
      3. From the deduped survivors, take up to _SWING_CAP (3) momentum_swings by score.
      4. Fill remaining slots (cap − goals − swings) by score, but when the deduped
         non-swing pool has ≥ _GHOST_RESERVE ghost_eligible moments, reserve at least
         _GHOST_RESERVE of those slots for ghost_eligible moments.
    Returns moments sorted by match_clock_s.
    """
    candidates = key_moments(events)
    goals = [km for km in candidates if km.moment_type == "goal"]
    others = [km for km in candidates if km.moment_type != "goal"]

    # Window-deduplicate across all non-goals
    window_best: dict[int, KeyMoment] = {}
    for km in others:
        win = km.match_clock_s // window_s
        prev = window_best.get(win)
        if (
            prev is None
            or km.score > prev.score
            or (km.score == prev.score and km.match_clock_s < prev.match_clock_s)
        ):
            window_best[win] = km

    # Survivors sorted by score desc (windows already deduplicated)
    survivors = sorted(window_best.values(), key=lambda km: (-km.score, km.match_clock_s))

    # Take up to _SWING_CAP swings
    swings = [km for km in survivors if km.moment_type == "momentum_swing"]
    non_swings = [km for km in survivors if km.moment_type != "momentum_swing"]
    selected_swings = swings[:_SWING_CAP]

    # Fill remaining slots with ghost-eligible reservation
    remaining = max(0, cap - len(goals) - len(selected_swings))
    ghost_pool = [km for km in non_swings if km.ghost_eligible]
    other_pool = [km for km in non_swings if not km.ghost_eligible]

    if len(ghost_pool) >= _GHOST_RESERVE and remaining > 0:
        n_forced = min(_GHOST_RESERVE, remaining)
        forced = ghost_pool[:n_forced]
        rest = sorted(
            ghost_pool[n_forced:] + other_pool,
            key=lambda km: (-km.score, km.match_clock_s),
        )[: max(0, remaining - n_forced)]
        selected_rest = forced + rest
    else:
        selected_rest = (
            sorted(ghost_pool + other_pool, key=lambda km: (-km.score, km.match_clock_s))
        )[:remaining]

    result = goals + selected_swings + selected_rest
    result.sort(key=lambda km: km.match_clock_s)
    return result
