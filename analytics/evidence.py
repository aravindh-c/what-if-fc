"""Build a deterministic, JSON-serialisable evidence packet for a key moment.

The packet is the sole input to the agents; every number in it comes from
code (Tactical Twin or metrics.py), never from the LLM.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from analytics.metrics import KeyMoment, momentum, pass_event_for, pressure_index
from analytics.tactical_twin import TwinResult, pass_difficulty
from core.schemas import MatchEvent, PositionSnapshot

# ---------------------------------------------------------------------------
# Evidence packet model
# ---------------------------------------------------------------------------


class LiveMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minute: int
    momentum_share: dict[str, float]    # team_id -> share (0-1)
    pressure_index: dict[str, float]    # team_id -> pressure_index
    scoreline: dict[str, int]           # team_id -> goals scored


class EvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    match_id: str
    moment_type: str
    moment_minute: int              # match_clock_s // 60
    moment_score: float             # heuristic importance 0-1; not a probability
    event_ids: list[str]            # triggering pass + up to 3 previous same-possession events
    live_metrics: LiveMetrics
    twin_version: str
    twin_weights: dict[str, float]
    twin_delta: float               # best_alt.S - actual.S; ghost shown when >= 0.10
    twin_actual_score: float
    twin_ghost_score: float
    twin_ghost_player_id: str | None
    twin_components_actual: dict[str, float]
    twin_components_ghost: dict[str, float]
    pass_difficulty: float          # 0-100; see metrics definition
    ghost_shown: bool
    formula_version: str            # always "twin-v1"
    label: str                      # fixed disclaimer
    passer_id: str | None
    actual_receiver_id: str | None
    highlight_defenders: list[str]
    actual_pass_length_m: float
    ghost_pass_length_m: float | None
    actual_nearest_defender_m: float | None
    ghost_nearest_defender_m: float | None
    actual_progress_m: float | None = None   # end_x − start_x; negative = backwards
    ghost_progress_m: float | None = None


_LABEL = "heuristic tactical option score, not a probability"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_evidence_packet(
    moment: KeyMoment,
    events: Sequence[MatchEvent],
    snapshot: PositionSnapshot | None,
    twin: TwinResult,
    match_id: str,
) -> EvidencePacket:
    """Build a fully deterministic evidence packet.

    `events` is the full match event list (dedup happens inside metrics).
    `snapshot` is the PositionSnapshot for the triggering pass (may be None
    for non-pass moments; pass_difficulty will be 0.0 in that case).
    """
    evs = list(events)

    # --- triggering pass event (source pass for FTT; own event otherwise) ---
    trigger_ev = pass_event_for(moment, evs)
    # Raw moment event used as fallback for player identity (e.g. goal scorer)
    moment_ev = next((e for e in evs if e.event_id == moment.event_id), None)

    # --- event IDs: pass event + moment event (if different) + up to 3 earlier ---
    if trigger_ev is None:
        ev_ids: list[str] = [moment.event_id]
    else:
        ev_ids = [trigger_ev.event_id]
        if moment.event_id != trigger_ev.event_id:
            ev_ids.append(moment.event_id)
        poss_id = trigger_ev.possession_id
        earlier = [
            e for e in evs
            if e.possession_id == poss_id
            and e.match_clock_s < trigger_ev.match_clock_s
            and e.event_id not in {trigger_ev.event_id, moment.event_id}
        ]
        earlier.sort(key=lambda e: e.match_clock_s, reverse=True)
        ev_ids += [e.event_id for e in earlier[:3]]

    # --- live metrics at moment's minute ---
    minute = moment.match_clock_s // 60
    mom_rows = momentum(evs)
    pres_rows = pressure_index(evs)

    mom_at_min = {
        r.team_id: r.share
        for r in mom_rows
        if r.minute == minute
    }
    pres_at_min = {
        r.team_id: round(r.pressure_index, 3)
        for r in pres_rows
        if r.minute == minute
    }

    # --- scoreline: both teams always present (0 if no goals) ---
    all_team_ids: set[str] = {e.team_id for e in evs if e.team_id}
    if snapshot is not None:
        all_team_ids.update(p.team_id for p in snapshot.positions)
    scoreline: dict[str, int] = {tid: 0 for tid in sorted(all_team_ids)}
    for e in evs:
        if e.event_type == "goal" and e.team_id and e.match_clock_s <= moment.match_clock_s:
            scoreline[e.team_id] = scoreline.get(e.team_id, 0) + 1

    live = LiveMetrics(
        minute=minute,
        momentum_share=mom_at_min,
        pressure_index=pres_at_min,
        scoreline=scoreline,
    )

    # --- pass difficulty ---
    diff = 0.0
    if trigger_ev is not None and snapshot is not None:
        opp_positions = [p for p in snapshot.positions if p.team_id != trigger_ev.team_id]
        if (
            trigger_ev.x is not None and trigger_ev.y is not None
            and trigger_ev.end_x is not None and trigger_ev.end_y is not None
        ):
            diff = round(
                pass_difficulty(
                    trigger_ev.x, trigger_ev.y,
                    trigger_ev.end_x, trigger_ev.end_y,
                    opp_positions,
                ),
                1,
            )

    # --- new spacing/identity fields ---
    actual_cand_dict = next((c for c in twin.candidates if c.get("is_actual")), None)
    ghost_cand_dict = (
        next(
            (c for c in twin.candidates if c.get("player_id") == twin.best_alt_player_id),
            None,
        )
        if twin.ghost_shown
        else None
    )
    actual_pass_length_m = round(actual_cand_dict["length"], 1) if actual_cand_dict else 0.0
    ghost_pass_length_m = (
        round(ghost_cand_dict["length"], 1) if ghost_cand_dict else None
    )
    actual_nearest_def = (
        round(actual_cand_dict["nearest_defender_m"], 1) if actual_cand_dict else None
    )
    ghost_nearest_def = (
        round(ghost_cand_dict["nearest_defender_m"], 1) if ghost_cand_dict else None
    )
    start_x = trigger_ev.x if trigger_ev is not None else None
    actual_progress: float | None = (
        round(actual_cand_dict["end_x"] - start_x, 1)
        if actual_cand_dict and start_x is not None
        else None
    )
    ghost_progress: float | None = (
        round(ghost_cand_dict["end_x"] - start_x, 1)
        if ghost_cand_dict and start_x is not None
        else None
    )

    return EvidencePacket(
        match_id=match_id,
        moment_type=moment.moment_type,
        moment_minute=minute,
        moment_score=round(moment.score, 3),
        event_ids=ev_ids,
        live_metrics=live,
        twin_version=twin.version,
        twin_weights=twin.weights,
        twin_delta=round(twin.delta, 3),
        twin_actual_score=twin.scores.actual,
        twin_ghost_score=twin.scores.ghost,
        twin_ghost_player_id=twin.best_alt_player_id,
        twin_components_actual=twin.scores.components_actual,
        twin_components_ghost=twin.scores.components_ghost,
        pass_difficulty=diff,
        ghost_shown=twin.ghost_shown,
        formula_version=twin.version,
        label=_LABEL,
        passer_id=(
            trigger_ev.player_id if trigger_ev
            else (moment_ev.player_id if moment_ev else None)
        ),
        actual_receiver_id=trigger_ev.receiver_id if trigger_ev else None,
        highlight_defenders=list(twin.visual.highlight_defenders),
        actual_pass_length_m=actual_pass_length_m,
        ghost_pass_length_m=ghost_pass_length_m,
        actual_nearest_defender_m=actual_nearest_def,
        ghost_nearest_defender_m=ghost_nearest_def,
        actual_progress_m=actual_progress,
        ghost_progress_m=ghost_progress,
    )
