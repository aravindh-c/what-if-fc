"""Two-agent workflow: Investigator → Director → Validator with retry and fallback.

WorkflowBuilder (the agent framework graph API) was considered but ruled out:
the retry sends a structurally different message to the Director on attempt 2
(adds previous text + error list), and the template fallback is a wholly
different code path.  A plain async function is cleaner and easier to test.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agents.overlay import build_overlay
from agents.templates import build_narrative
from analytics.validation import validate_text
from core.schemas import (
    NarrativeSource,
    NarrativeText,
    Overlay,
    OverlayText,
    ValidationStatus,
)

_PROMPTS = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------


class Claim(BaseModel):
    text: str
    evidence_fields: list[str]
    event_ids: list[str]


class Findings(BaseModel):
    claims: list[Claim]


class DirectorText(BaseModel):
    analyst_headline: str
    analyst_body: str
    fan_headline: str
    fan_body: str
    cue: str | None = None


# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------


def make_investigator(client: Any, kql: Any, tool_results: list[dict]) -> Any:
    """Create the Investigator agent with KQL tools that record results.

    Each tool call appends its result to tool_results so the validator
    can check agent-cited numbers against both packet and tool data.
    """
    from agent_framework import Agent

    def match_stats(match_id: str) -> dict:
        """Per-team pass completion, shots, goals and possession."""
        result = kql.match_stats(match_id)
        tool_results.append(result)
        return result

    def momentum_at(match_id: str, minute: int) -> dict:
        """Momentum share per team at the given minute."""
        result = kql.momentum_at(match_id, minute)
        tool_results.append(result)
        return result

    def pressure_at(match_id: str, minute: int) -> dict:
        """Pressure index per team at the given minute."""
        result = kql.pressure_at(match_id, minute)
        tool_results.append(result)
        return result

    def recent_events(match_id: str, minute: int, n: int = 5) -> list[dict]:
        """The n most recent events up to and including the given minute."""
        result = kql.recent_events(match_id, minute, n)
        tool_results.append({"recent_events": result})
        return result

    return Agent(
        client,
        name="Investigator",
        instructions=_load_prompt("investigator.md"),
        tools=[match_stats, momentum_at, pressure_at, recent_events],
    )


def make_director(client: Any) -> Any:
    """Create the Broadcast Director agent."""
    from agent_framework import Agent

    return Agent(
        client,
        name="Director",
        instructions=_load_prompt("director.md"),
    )


# ---------------------------------------------------------------------------
# Input serialisation helpers
# ---------------------------------------------------------------------------


def _packet_summary(packet: Any) -> dict:
    """Compact dict of key numbers and IDs for agent input."""
    return {
        "match_id": packet.match_id,
        "moment_type": packet.moment_type,
        "moment_minute": packet.moment_minute,
        "moment_score": packet.moment_score,
        "event_ids": list(packet.event_ids),
        "passer_id": packet.passer_id,
        "actual_receiver_id": packet.actual_receiver_id,
        "twin_ghost_player_id": packet.twin_ghost_player_id,
        "highlight_defenders": list(packet.highlight_defenders),
        "twin_actual_score": packet.twin_actual_score,
        "twin_ghost_score": packet.twin_ghost_score,
        "twin_delta": packet.twin_delta,
        "pass_difficulty": packet.pass_difficulty,
        "momentum_share": dict(packet.live_metrics.momentum_share),
        "pressure_index": dict(packet.live_metrics.pressure_index),
        "scoreline": dict(packet.live_metrics.scoreline),
        "twin_components_actual": dict(packet.twin_components_actual),
        "twin_components_ghost": dict(packet.twin_components_ghost),
        "ghost_shown": packet.ghost_shown,
        "label": packet.label,
    }


def _players_map(roster: list) -> dict:
    """Build {player_id: {name, role, team_id}} for agent input."""
    return {
        p.player_id: {
            "name": p.name,
            "role": str(p.role),
            "team_id": p.team_id,
        }
        for p in roster
    }


def _moment_players_map(packet: Any, roster: list) -> dict:
    """Return the players map restricted to the moment's relevant players.

    Agents only need names for the passer, receivers and highlighted
    defenders.  Passing the whole roster leaks names the agents must not
    mention (the validator flags mid-sentence capitalised words that are
    not in the roster or stopwords).
    """
    allowed: set[str] = set(filter(None, [
        packet.passer_id,
        packet.actual_receiver_id,
        packet.twin_ghost_player_id,
        *packet.highlight_defenders,
    ]))
    return _players_map([p for p in roster if p.player_id in allowed])


def _director_text_to_overlay_text(dt: DirectorText) -> OverlayText:
    return OverlayText(
        analyst={"en": NarrativeText(headline=dt.analyst_headline, body=dt.analyst_body)},
        fan={"en": NarrativeText(headline=dt.fan_headline, body=dt.fan_body)},
        cue=dt.cue,
    )


# ---------------------------------------------------------------------------
# Template fallback helper
# ---------------------------------------------------------------------------


def _template_fallback(
    packet: Any, twin: Any, roster: list, log: dict
) -> tuple[Overlay, dict]:
    text = build_narrative(packet, roster)
    overlay = build_overlay(packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED)
    log["source"] = "template"
    return overlay, log


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_moment_workflow(
    packet: Any,
    twin: Any,
    roster: list,
    kql: Any,
    client: Any,
    *,
    timeout_s: float = 30.0,
    _agents: tuple | None = None,
) -> tuple[Overlay, dict]:
    """Run the two-agent workflow and return (Overlay, run_log).

    Sequence:
        1. Investigator — call KQL tools, return Findings.
        2. Director attempt 1 — write text, return DirectorText.
        3. Validate — if passed, return agent overlay.
        4. Director attempt 2 — retry with errors.
        5. Validate — if passed, return agent overlay.
        6. Template fallback — always succeeds.

    Each agent call is wrapped in asyncio.wait_for(timeout=timeout_s).
    run_log keys: source, attempts, durations_s, errors_attempt1,
                  errors_attempt2, fallback_reason.

    Parameters
    ----------
    _agents:
        Optional (investigator, director) tuple injected for testing;
        bypasses make_investigator / make_director.
    """
    tool_results: list[dict] = []
    if _agents is not None:
        investigator, director = _agents
    else:
        investigator = make_investigator(client, kql, tool_results)
        director = make_director(client)

    log: dict = {
        "source": "template",
        "attempts": 0,
        "durations_s": [],
        "errors_attempt1": [],
        "errors_attempt2": [],
        "fallback_reason": None,
    }

    psum = _packet_summary(packet)
    # Agents see only moment-relevant players; full roster goes to the validator.
    players = _moment_players_map(packet, roster)

    # ------------------------------------------------------------------
    # Step 1: Investigator
    # ------------------------------------------------------------------
    t0 = time.monotonic()
    try:
        inv_resp = await asyncio.wait_for(
            investigator.run(
                json.dumps({"packet": psum, "players": players}),
                options={"response_format": Findings},
            ),
            timeout=timeout_s,
        )
        findings: Findings | None = inv_resp.value
    except TimeoutError:
        log["durations_s"].append(round(time.monotonic() - t0, 3))
        log["fallback_reason"] = "investigator timed out"
        return _template_fallback(packet, twin, roster, log)
    except Exception as exc:
        log["durations_s"].append(round(time.monotonic() - t0, 3))
        log["fallback_reason"] = f"investigator failed: {type(exc).__name__}"
        return _template_fallback(packet, twin, roster, log)
    log["durations_s"].append(round(time.monotonic() - t0, 3))

    if findings is None:
        log["fallback_reason"] = "investigator returned no structured output"
        return _template_fallback(packet, twin, roster, log)

    # ------------------------------------------------------------------
    # Step 2: Director attempt 1
    # ------------------------------------------------------------------
    dir_msg = json.dumps(
        {"findings": findings.model_dump(), "packet_summary": psum, "players": players}
    )
    t0 = time.monotonic()
    try:
        dir_resp = await asyncio.wait_for(
            director.run(dir_msg, options={"response_format": DirectorText}),
            timeout=timeout_s,
        )
        dt: DirectorText | None = dir_resp.value
    except TimeoutError:
        log["durations_s"].append(round(time.monotonic() - t0, 3))
        log["fallback_reason"] = "director timed out (attempt 1)"
        return _template_fallback(packet, twin, roster, log)
    except Exception as exc:
        log["durations_s"].append(round(time.monotonic() - t0, 3))
        log["fallback_reason"] = f"director attempt 1 failed: {type(exc).__name__}"
        return _template_fallback(packet, twin, roster, log)
    log["durations_s"].append(round(time.monotonic() - t0, 3))
    log["attempts"] = 1

    if dt is None:
        log["fallback_reason"] = "director returned no structured output (attempt 1)"
        return _template_fallback(packet, twin, roster, log)

    try:
        overlay_text1 = _director_text_to_overlay_text(dt)
    except Exception as exc:
        log["fallback_reason"] = f"overlay text schema rejected attempt 1: {exc}"
        return _template_fallback(packet, twin, roster, log)

    errors1 = validate_text(overlay_text1, packet, roster, tool_results)
    log["errors_attempt1"] = errors1

    if not errors1:
        log["source"] = "agent"
        overlay = build_overlay(
            packet, twin, overlay_text1, NarrativeSource.AGENT, ValidationStatus.PASSED
        )
        return overlay, log

    # ------------------------------------------------------------------
    # Step 3: Director attempt 2 (retry with errors)
    # ------------------------------------------------------------------
    dir_msg2 = json.dumps({
        "findings": findings.model_dump(),
        "packet_summary": psum,
        "players": players,
        "validation_errors": errors1,
        "previous_text": dt.model_dump(),
    })
    t0 = time.monotonic()
    try:
        dir_resp2 = await asyncio.wait_for(
            director.run(dir_msg2, options={"response_format": DirectorText}),
            timeout=timeout_s,
        )
        dt2: DirectorText | None = dir_resp2.value
    except TimeoutError:
        log["durations_s"].append(round(time.monotonic() - t0, 3))
        log["fallback_reason"] = "director timed out (attempt 2)"
        return _template_fallback(packet, twin, roster, log)
    except Exception as exc:
        log["durations_s"].append(round(time.monotonic() - t0, 3))
        log["fallback_reason"] = f"director attempt 2 failed: {type(exc).__name__}"
        return _template_fallback(packet, twin, roster, log)
    log["durations_s"].append(round(time.monotonic() - t0, 3))
    log["attempts"] = 2

    if dt2 is None:
        log["fallback_reason"] = "director returned no structured output (attempt 2)"
        return _template_fallback(packet, twin, roster, log)

    try:
        overlay_text2 = _director_text_to_overlay_text(dt2)
    except Exception as exc:
        log["fallback_reason"] = f"overlay text schema rejected attempt 2: {exc}"
        return _template_fallback(packet, twin, roster, log)

    errors2 = validate_text(overlay_text2, packet, roster, tool_results)
    log["errors_attempt2"] = errors2

    if not errors2:
        log["source"] = "agent"
        overlay = build_overlay(
            packet, twin, overlay_text2, NarrativeSource.AGENT, ValidationStatus.PASSED
        )
        return overlay, log

    # ------------------------------------------------------------------
    # Step 4: Template fallback (validation failed twice)
    # ------------------------------------------------------------------
    log["fallback_reason"] = "validation failed after 2 attempts"
    return _template_fallback(packet, twin, roster, log)
