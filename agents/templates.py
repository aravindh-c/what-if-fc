"""Deterministic template fallback narratives for all moment types.

Builds OverlayText from an EvidencePacket and roster without any LLM call.
Output always uses only numbers and names drawn directly from the packet,
so it is guaranteed to pass analytics.validation.validate_text.

Moment types handled: ghost_pass, goal, turnover, momentum_swing, pressure_spell
(and the raw KQL moment types: high_pressure_final_third_pass, final_third_turnover).
"""

from __future__ import annotations

from core.schemas import NarrativeText, OverlayText

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _name(player_id: str | None, roster_map: dict[str, str]) -> str:
    """Return the player's full name (61 of 72 players share a surname)."""
    if player_id is None:
        return "the player"
    return roster_map.get(player_id, "the player")


def _scoreline(packet) -> str:
    """Format scoreline as 'T01 1-0 T02' or just '1-0' when two teams."""
    sl = packet.live_metrics.scoreline
    teams = sorted(sl.keys())
    if len(teams) == 2:
        return f"{sl[teams[0]]}-{sl[teams[1]]}"
    return ", ".join(f"{t} {v}" for t, v in sorted(sl.items()))


def _team_momentum(packet) -> tuple[str, float]:
    """Return (team_id, share) for the team with the highest momentum."""
    shares = packet.live_metrics.momentum_share
    if not shares:
        return ("", 0.5)
    best = max(shares.items(), key=lambda kv: kv[1])
    return best


def _team_pressure(packet) -> tuple[str, float]:
    """Return (team_id, pressure_index) for the team with the highest pressure."""
    pres = packet.live_metrics.pressure_index
    if not pres:
        return ("", 0.0)
    best = max(pres.items(), key=lambda kv: kv[1])
    return best


# ---------------------------------------------------------------------------
# Per-moment-type builders
# ---------------------------------------------------------------------------

_COMPONENT_REASON: dict[str, str] = {
    "F": "a clearer passing lane",
    "R": "far less risk of losing it",
    "P": "more forward progress",
    "T": "a more threatening position",
}


def _biggest_component_reason(packet) -> str:
    """Plain-English explanation of the component with the largest ghost advantage."""
    actual = packet.twin_components_actual or {}
    ghost = packet.twin_components_ghost or {}
    if not actual or not ghost:
        return "a better option overall"
    best = max(
        _COMPONENT_REASON,
        key=lambda k: float(ghost.get(k, 0.0)) - float(actual.get(k, 0.0)),
    )
    return _COMPONENT_REASON[best]


def _ghost_pass_text(packet, roster_map: dict[str, str]) -> OverlayText:
    receiver = _name(packet.actual_receiver_id, roster_map)
    ghost = _name(packet.twin_ghost_player_id, roster_map)
    a_score = packet.twin_actual_score
    g_score = packet.twin_ghost_score

    # Pass direction: note backwards passes (negative progress)
    prog = packet.actual_progress_m
    if prog is not None and prog < 0:
        direction = f" (backwards, {prog:.1f} m)"
    else:
        direction = ""

    # Defender distance context when available
    a_def = packet.actual_nearest_defender_m
    g_def = packet.ghost_nearest_defender_m
    if a_def is not None and g_def is not None:
        def_note = (
            f" Pass to {receiver} had a defender {a_def:.1f} m away;"
            f" {ghost} was {g_def:.1f} m clear."
        )
    else:
        def_note = ""

    a_headline = f"Ghost Pass at minute {packet.moment_minute}"
    a_body = (
        f"Pass to {receiver}{direction}: option score {a_score:.2f}."
        f" Ghost target {ghost}: option score {g_score:.2f}.{def_note}"
    )

    # Only claim the receiver was "free" when ghost_nearest_defender_m >= 10
    # AND it is greater than the actual receiver's defender distance.
    is_truly_free = (
        g_def is not None and g_def >= 10.0
        and a_def is not None and g_def > a_def
    )
    if is_truly_free:
        f_headline = f"{ghost} was free at {g_def:.1f} m!"
        f_body = (
            f"{ghost} had {g_def:.1f} m of space; "
            f"better option score {g_score:.2f} vs {a_score:.2f}."
        )
    else:
        reason = _biggest_component_reason(packet)
        f_headline = f"Better option at minute {packet.moment_minute}!"
        f_body = (
            f"{ghost} offered {reason}; "
            f"better option score {g_score:.2f} vs {a_score:.2f}."
        )

    return OverlayText(
        analyst={"en": NarrativeText(headline=a_headline, body=a_body)},
        fan={"en": NarrativeText(headline=f_headline, body=f_body)},
    )


def _goal_text(packet, roster_map: dict[str, str]) -> OverlayText:
    scorer = _name(packet.passer_id, roster_map)
    sl = _scoreline(packet)
    pres_val = _team_pressure(packet)[1]

    a_headline = f"Goal! {scorer} at minute {packet.moment_minute}"
    a_body = f"Score: {sl}. Pressure index: {pres_val:.3f}."

    f_headline = f"Goal! {scorer} scores!"
    f_body = f"Score is {sl} at minute {packet.moment_minute}."

    return OverlayText(
        analyst={"en": NarrativeText(headline=a_headline, body=a_body)},
        fan={"en": NarrativeText(headline=f_headline, body=f_body)},
    )


def _turnover_text(packet, roster_map: dict[str, str]) -> OverlayText:
    winner_id = packet.ball_won_by if packet.ball_won_by is not None else packet.passer_id
    player = _name(winner_id, roster_map)
    pres_team, pres_val = _team_pressure(packet)
    # Both teams' pressure indices for analyst body
    pres = packet.live_metrics.pressure_index
    pres_teams = sorted(pres.keys())

    a_headline = f"Turnover at minute {packet.moment_minute}"
    if len(pres_teams) >= 2:
        a_body = (
            f"{player} wins possession. "
            f"Pressure index: {pres.get(pres_teams[0], 0.0):.3f} vs "
            f"{pres.get(pres_teams[1], 0.0):.3f}."
        )
    elif len(pres_teams) == 1:
        a_body = (
            f"{player} wins possession. "
            f"Pressure index: {pres.get(pres_teams[0], 0.0):.3f}."
        )
    else:
        a_body = f"{player} wins possession at minute {packet.moment_minute}."

    f_headline = f"Big tackle! {player} wins it back!"
    f_body = f"Minute {packet.moment_minute}: great work to win the ball."

    return OverlayText(
        analyst={"en": NarrativeText(headline=a_headline, body=a_body)},
        fan={"en": NarrativeText(headline=f_headline, body=f_body)},
    )


def _momentum_swing_text(packet, roster_map: dict[str, str]) -> OverlayText:
    mom_team, mom_share = _team_momentum(packet)
    pres_val = _team_pressure(packet)[1]

    a_headline = f"Momentum swing at minute {packet.moment_minute}"
    a_body = (
        f"Top momentum share: {mom_share:.3f}. "
        f"Pressure index: {pres_val:.3f}."
    )

    f_headline = "The game is swinging!"
    f_body = f"Minute {packet.moment_minute}: momentum is shifting."

    return OverlayText(
        analyst={"en": NarrativeText(headline=a_headline, body=a_body)},
        fan={"en": NarrativeText(headline=f_headline, body=f_body)},
    )


def _pressure_spell_text(packet, roster_map: dict[str, str]) -> OverlayText:
    pres = packet.live_metrics.pressure_index
    pres_teams = sorted(pres.keys())

    a_headline = f"Pressure spell at minute {packet.moment_minute}"
    if len(pres_teams) >= 2:
        a_body = (
            f"Pressure index: {pres.get(pres_teams[0], 0.0):.3f} vs "
            f"{pres.get(pres_teams[1], 0.0):.3f}."
        )
    elif len(pres_teams) == 1:
        a_body = f"Pressure index: {pres.get(pres_teams[0], 0.0):.3f}."
    else:
        a_body = f"High pressure at minute {packet.moment_minute}."

    f_headline = "They cannot get out!"
    f_body = f"Minute {packet.moment_minute}: relentless pressing from the team."

    return OverlayText(
        analyst={"en": NarrativeText(headline=a_headline, body=a_body)},
        fan={"en": NarrativeText(headline=f_headline, body=f_body)},
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_MOMENT_TYPE_BUILDERS = {
    "ghost_pass": _ghost_pass_text,
    "high_pressure_final_third_pass": _ghost_pass_text,
    "goal": _goal_text,
    "turnover": _turnover_text,
    "final_third_turnover": _turnover_text,
    "momentum_swing": _momentum_swing_text,
    "pressure_spell": _pressure_spell_text,
}


def build_narrative(packet, roster: list) -> OverlayText:
    """Build a deterministic OverlayText from an EvidencePacket and roster.

    Parameters
    ----------
    packet:
        EvidencePacket for the moment.
    roster:
        List of Player objects; used to resolve player_ids to names.

    Returns
    -------
    OverlayText
        English analyst and fan text built entirely from packet values.
    """
    roster_map: dict[str, str] = {p.player_id: p.name for p in roster}

    builder = _MOMENT_TYPE_BUILDERS.get(packet.moment_type)
    if builder is None:
        # Fallback: generic summary
        return OverlayText(
            analyst={
                "en": NarrativeText(
                    headline=f"Key moment at minute {packet.moment_minute}",
                    body=f"Match moment at minute {packet.moment_minute}.",
                )
            },
            fan={
                "en": NarrativeText(
                    headline=f"Key moment at minute {packet.moment_minute}!",
                    body=f"Important action at minute {packet.moment_minute}.",
                )
            },
        )

    return builder(packet, roster_map)
