"""Shared moment-processing helpers for the replay builder and live watcher.

Exports:
    overlay_id(match_id, event_id)  -> str
    make_goal_twin(scorer_id)       -> TwinResult
    build_ledger(...)               -> dict
    build_live_meta(match_id)       -> dict   (same shape as replay bundles)
    NoOpAgent                       -- forces template fallback
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

_MATCH_ID_RE = re.compile(r"_s(\d+)_([A-Za-z0-9]+)_([A-Za-z0-9]+)$")


def overlay_id(match_id: str, event_id: str) -> str:
    raw = (match_id + event_id).encode()
    return "ov_" + hashlib.sha256(raw).hexdigest()[:10]


def make_goal_twin(scorer_id: str) -> Any:
    """Return a minimal TwinResult for a goal moment (no pass scoring needed)."""
    from analytics.tactical_twin import VERSION, WEIGHTS, TwinResult
    from core.schemas import OverlayVisual, TwinScores

    return TwinResult(
        version=VERSION,
        weights=dict(WEIGHTS),
        candidates=[],
        actual_player_id=scorer_id,
        best_alt_player_id=None,
        delta=0.0,
        ghost_shown=False,
        visual=OverlayVisual(),
        scores=TwinScores(
            actual=0.0,
            ghost=0.0,
            components_actual={},
            components_ghost={},
        ),
    )


def build_ledger(
    packet: Any,
    twin: Any,
    players: list,
    events: list,
    log: dict,
) -> dict[str, Any]:
    from agents.workflow import _packet_summary  # noqa: PLC2701
    from analytics.tactical_twin import _GHOST_MIN_DELTA, _GHOST_MIN_F  # noqa: PLC2701

    player_name = {p.player_id: p.name for p in players}
    players_dict = {
        p.player_id: {"name": p.name, "role": str(p.role), "team_id": p.team_id}
        for p in players
    }

    psum = _packet_summary(packet, players_dict)

    ev_map = {e.event_id: e for e in events}
    cited: list[dict[str, Any]] = []
    for eid in packet.event_ids:
        ev = ev_map.get(eid)
        if ev is None:
            continue
        cited.append({
            "event_id": eid,
            "match_clock_s": ev.match_clock_s,
            "event_type": ev.event_type.value,
            "player_name": player_name.get(ev.player_id) if ev.player_id else None,
            "team_id": ev.team_id,
            "outcome": ev.outcome.value if ev.outcome else None,
        })

    sorted_cands = sorted(twin.candidates, key=lambda c: c.get("S", 0.0), reverse=True)
    top5 = [
        {
            "player_id": c.get("player_id"),
            "player_name": player_name.get(c.get("player_id") or ""),
            "T": round(c.get("T", 0.0), 3),
            "P": round(c.get("P", 0.0), 3),
            "F": round(c.get("F", 0.0), 3),
            "R": round(c.get("R", 0.0), 3),
            "S": round(c.get("S", 0.0), 3),
            "nearest_defender_m": round(c.get("nearest_defender_m", 0.0), 1),
            "is_actual": bool(c.get("is_actual", False)),
        }
        for c in sorted_cands[:5]
    ]

    return {
        "packet": psum,
        "events": cited,
        "candidates": top5,
        "formula": {
            "version": twin.version,
            "weights": dict(twin.weights),
            "ghost_rule": f"delta >= {_GHOST_MIN_DELTA} and F >= {_GHOST_MIN_F}",
        },
        "run": {
            "source": log.get("source", "template"),
            "attempts": log.get("attempts", 0),
            "fallback_reason": log.get("fallback_reason"),
            "errors_attempt1": log.get("errors_attempt1", []),
            "durations_s": log.get("durations_s", []),
        },
    }


class NoOpAgent:
    """Stub agent that immediately raises — forces template fallback."""

    async def run(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("agents disabled")


def build_live_meta(match_id: str) -> dict[str, Any]:
    """Return meta for a live match in the same shape as offline replay bundles."""
    m = _MATCH_ID_RE.search(match_id)
    if m:
        seed, home_id, away_id = int(m.group(1)), m.group(2), m.group(3)
    else:
        seed, home_id, away_id = 7, "T01", "T02"

    from simulator.reference_data import build_players, build_teams

    players = build_players(seed)
    all_teams = {t.team_id: t for t in build_teams()}
    home = all_teams.get(home_id)
    away = all_teams.get(away_id)

    teams_out: dict[str, Any] = {}
    for t_id, t_obj in ((home_id, home), (away_id, away)):
        if t_obj is not None:
            teams_out[t_id] = {
                "name": t_obj.name,
                "short_name": t_obj.short_name,
                "formation": t_obj.formation,
                "style": t_obj.style,
            }

    home_name = home.name if home else home_id
    away_name = away.name if away else away_id
    return {
        "replay_id": match_id,
        "kind": "match",
        "title": f"{home_name} vs {away_name}",
        "teams": teams_out,
        "players": {
            p.player_id: {
                "name": p.name,
                "role": str(p.role),
                "team_id": p.team_id,
                "shirt_number": p.shirt_number,
            }
            for p in players
        },
        "built_at": datetime.now(UTC).isoformat(),
        "twin_version": "twin-v1",
    }
