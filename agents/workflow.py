"""Two-agent workflow: Investigator and Broadcast Director.

Pydantic output models and agent factory functions.  Orchestration
(retry loop, validator, template fallback) is in run_moment_workflow().
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

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
