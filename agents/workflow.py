"""Two-agent workflow: Investigator → Director → Validator with retry and fallback.

Implemented as a WorkflowBuilder graph with five Executor subclasses:
InvestigatorExecutor, DirectorExecutor, ValidatorExecutor, OverlayExecutor, TemplateExecutor.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel, ConfigDict, Field

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


def _packet_summary(packet: Any, players: dict | None = None) -> dict:
    """Compact dict of key numbers and IDs for agent input.

    Scores are rounded to 2 dp and distances to 1 dp so agents write values
    at the expected precision.  Player names are resolved from `players` when
    provided so the Director does not need to look them up.
    """
    def _r1(v: float | None) -> float | None:
        return round(v, 1) if v is not None else None

    def _name(pid: str | None) -> str | None:
        if not pid or not players:
            return None
        return players.get(pid, {}).get("name")

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
        "passer_name": _name(packet.passer_id),
        "actual_receiver_name": _name(packet.actual_receiver_id),
        "ghost_receiver_name": _name(packet.twin_ghost_player_id),
        "twin_actual_score": round(packet.twin_actual_score, 2),
        "twin_ghost_score": round(packet.twin_ghost_score, 2),
        "twin_delta": round(packet.twin_delta, 2),
        "pass_difficulty": _r1(packet.pass_difficulty),
        "actual_pass_length_m": _r1(packet.actual_pass_length_m),
        "ghost_pass_length_m": _r1(packet.ghost_pass_length_m),
        "actual_nearest_defender_m": _r1(packet.actual_nearest_defender_m),
        "ghost_nearest_defender_m": _r1(packet.ghost_nearest_defender_m),
        "actual_progress_m": _r1(packet.actual_progress_m),
        "ghost_progress_m": _r1(packet.ghost_progress_m),
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


def _check_schema_lengths(dt: DirectorText) -> list[str]:
    """Return human-readable error messages for DirectorText fields exceeding OverlayText limits."""
    errors: list[str] = []
    checks: list[tuple[str, str, int]] = [
        ("analyst headline", dt.analyst_headline, 80),
        ("analyst body", dt.analyst_body, 280),
        ("fan headline", dt.fan_headline, 80),
        ("fan body", dt.fan_body, 280),
    ]
    if dt.cue is not None:
        checks.append(("cue", dt.cue, 280))
    for label, value, limit in checks:
        if len(value) > limit:
            errors.append(f"{label} is {len(value)} characters, max {limit}")
    return errors


# ---------------------------------------------------------------------------
# Graph message types (small Pydantic models)
# ---------------------------------------------------------------------------


class _Start(BaseModel):
    """Initial message to InvestigatorExecutor."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    packet: Any
    twin: Any
    roster: list


class _AfterInv(BaseModel):
    """Investigator → Director (ok=True) or Template (ok=False)."""
    ok: bool
    findings: Findings | None = None
    log: dict


class _AfterDir(BaseModel):
    """Director → Validator (ok=True) or Template (ok=False)."""
    ok: bool
    director_text: DirectorText | None = None
    attempt: int = 1
    findings: Findings | None = None
    log: dict


class _AfterVal(BaseModel):
    """Validator → Overlay (passed=True) / Director retry (attempt=1) / Template (else)."""
    passed: bool
    overlay_text: Any = None
    errors: list[str] = Field(default_factory=list)
    attempt: int = 1
    director_text: DirectorText | None = None
    findings: Findings | None = None
    log: dict


class _Done(BaseModel):
    """Final workflow output yielded to the caller."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    overlay: Any  # Overlay
    log: dict


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------


def _fresh_log() -> dict:
    return {
        "source": "template",
        "attempts": 0,
        "durations_s": [],
        "errors_attempt1": [],
        "errors_attempt2": [],
        "fallback_reason": None,
    }


def _append_dur(log: dict, dur: float) -> dict:
    return {**log, "durations_s": [*log["durations_s"], dur]}


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


class InvestigatorExecutor(Executor):
    def __init__(self, *, client: Any, kql: Any, timeout_s: float, _agent: Any = None) -> None:
        super().__init__(id="investigator")
        self._client = client
        self._kql = kql
        self._timeout_s = timeout_s
        self._agent = _agent

    @handler
    async def run(self, msg: _Start, ctx: WorkflowContext[_AfterInv]) -> None:
        tool_results: list[dict] = []
        log = _fresh_log()

        ctx.set_state("packet", msg.packet)
        ctx.set_state("twin", msg.twin)
        ctx.set_state("roster", msg.roster)
        players = _moment_players_map(msg.packet, msg.roster)
        psum = _packet_summary(msg.packet, players)
        ctx.set_state("psum", psum)
        ctx.set_state("players", players)

        agent = self._agent or make_investigator(self._client, self._kql, tool_results)
        t0 = time.monotonic()
        try:
            inv_resp = await asyncio.wait_for(
                agent.run(
                    json.dumps({"packet": psum, "players": players}),
                    options={
                        "response_format": Findings,
                        "reasoning": {"effort": "low"},
                        "verbosity": "low",
                    },
                ),
                timeout=self._timeout_s,
            )
            findings: Findings | None = inv_resp.value
        except TimeoutError:
            log = _append_dur(log, round(time.monotonic() - t0, 3))
            log = {**log, "fallback_reason": "investigator timed out"}
            ctx.set_state("tool_results", tool_results)
            await ctx.send_message(_AfterInv(ok=False, log=log))
            return
        except Exception as exc:
            log = _append_dur(log, round(time.monotonic() - t0, 3))
            log = {**log, "fallback_reason": f"investigator failed: {type(exc).__name__}"}
            ctx.set_state("tool_results", tool_results)
            await ctx.send_message(_AfterInv(ok=False, log=log))
            return

        log = _append_dur(log, round(time.monotonic() - t0, 3))
        ctx.set_state("tool_results", tool_results)

        if findings is None:
            log = {**log, "fallback_reason": "investigator returned no structured output"}
            await ctx.send_message(_AfterInv(ok=False, log=log))
            return

        await ctx.send_message(_AfterInv(ok=True, findings=findings, log=log))


class DirectorExecutor(Executor):
    def __init__(self, *, client: Any, timeout_s: float, _agent: Any = None) -> None:
        super().__init__(id="director")
        self._client = client
        self._timeout_s = timeout_s
        self._agent = _agent

    @handler
    async def run_attempt1(self, msg: _AfterInv, ctx: WorkflowContext[_AfterDir]) -> None:
        psum = ctx.get_state("psum")
        players = ctx.get_state("players")
        dir_msg = json.dumps({
            "findings": msg.findings.model_dump(),
            "packet_summary": psum,
            "players": players,
        })
        await self._call_director(
            dir_msg,
            attempt=1,
            findings=msg.findings,
            incoming_log=msg.log,
            ctx=ctx,
        )

    @handler
    async def run_retry(self, msg: _AfterVal, ctx: WorkflowContext[_AfterDir]) -> None:
        psum = ctx.get_state("psum")
        players = ctx.get_state("players")
        dir_msg = json.dumps({
            "findings": msg.findings.model_dump(),
            "packet_summary": psum,
            "players": players,
            "validation_errors": msg.errors,
            "previous_text": msg.director_text.model_dump(),
        })
        await self._call_director(
            dir_msg,
            attempt=2,
            findings=msg.findings,
            incoming_log=msg.log,
            ctx=ctx,
        )

    async def _call_director(
        self,
        dir_msg: str,
        attempt: int,
        findings: Findings | None,
        incoming_log: dict,
        ctx: WorkflowContext[_AfterDir],
    ) -> None:
        log = {**incoming_log, "durations_s": list(incoming_log["durations_s"])}
        agent = self._agent or make_director(self._client)
        t0 = time.monotonic()
        try:
            dir_resp = await asyncio.wait_for(
                agent.run(
                    dir_msg,
                    options={
                        "response_format": DirectorText,
                        "reasoning": {"effort": "low"},
                        "verbosity": "low",
                    },
                ),
                timeout=self._timeout_s,
            )
            dt: DirectorText | None = dir_resp.value
        except TimeoutError:
            log = _append_dur(log, round(time.monotonic() - t0, 3))
            log = {**log, "fallback_reason": f"director timed out (attempt {attempt})"}
            await ctx.send_message(_AfterDir(ok=False, attempt=attempt, log=log))
            return
        except Exception as exc:
            log = _append_dur(log, round(time.monotonic() - t0, 3))
            reason = f"director attempt {attempt} failed: {type(exc).__name__}"
            log = {**log, "fallback_reason": reason}
            await ctx.send_message(_AfterDir(ok=False, attempt=attempt, log=log))
            return

        log = _append_dur(log, round(time.monotonic() - t0, 3))
        log = {**log, "attempts": attempt}

        if dt is None:
            reason = f"director returned no structured output (attempt {attempt})"
            log = {**log, "fallback_reason": reason}
            await ctx.send_message(_AfterDir(ok=False, attempt=attempt, log=log))
            return

        await ctx.send_message(
            _AfterDir(ok=True, director_text=dt, attempt=attempt, findings=findings, log=log)
        )


class ValidatorExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="validator")

    @handler
    async def run(self, msg: _AfterDir, ctx: WorkflowContext[_AfterVal]) -> None:
        packet = ctx.get_state("packet")
        roster = ctx.get_state("roster")
        tool_results: list[dict] = ctx.get_state("tool_results") or []

        log = {**msg.log, "durations_s": list(msg.log["durations_s"])}
        dt = msg.director_text

        schema_errs = _check_schema_lengths(dt)
        if schema_errs:
            errors = schema_errs
            overlay_text = None
        else:
            overlay_text = _director_text_to_overlay_text(dt)
            errors = validate_text(overlay_text, packet, roster, tool_results)

        attempt = msg.attempt
        errors_key = f"errors_attempt{attempt}"
        log = {**log, errors_key: errors}

        await ctx.send_message(
            _AfterVal(
                passed=not errors and overlay_text is not None,
                overlay_text=overlay_text,
                errors=errors,
                attempt=attempt,
                director_text=dt,
                findings=msg.findings,
                log=log,
            )
        )


class OverlayExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="overlay")

    @handler
    async def run(self, msg: _AfterVal, ctx: WorkflowContext[Never, _Done]) -> None:
        packet = ctx.get_state("packet")
        twin = ctx.get_state("twin")
        log = {**msg.log, "source": "agent"}
        overlay = build_overlay(
            packet, twin, msg.overlay_text, NarrativeSource.AGENT, ValidationStatus.PASSED
        )
        await ctx.yield_output(_Done(overlay=overlay, log=log))


class TemplateExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="template")

    @handler
    async def handle_inv(self, msg: _AfterInv, ctx: WorkflowContext[Never, _Done]) -> None:
        await self._yield_template(msg.log, ctx)

    @handler
    async def handle_dir(self, msg: _AfterDir, ctx: WorkflowContext[Never, _Done]) -> None:
        await self._yield_template(msg.log, ctx)

    @handler
    async def handle_val(self, msg: _AfterVal, ctx: WorkflowContext[Never, _Done]) -> None:
        reason = msg.log.get("fallback_reason") or "validation failed after 2 attempts"
        log = {**msg.log, "fallback_reason": reason}
        await self._yield_template(log, ctx)

    async def _yield_template(self, log: dict, ctx: WorkflowContext[Never, _Done]) -> None:
        packet = ctx.get_state("packet")
        twin = ctx.get_state("twin")
        roster = ctx.get_state("roster")
        text = build_narrative(packet, roster)
        overlay = build_overlay(
            packet, twin, text, NarrativeSource.TEMPLATE, ValidationStatus.PASSED
        )
        log = {**log, "source": "template"}
        await ctx.yield_output(_Done(overlay=overlay, log=log))


# ---------------------------------------------------------------------------
# Workflow construction
# ---------------------------------------------------------------------------


def _build_workflow(
    client: Any,
    kql: Any,
    timeout_s: float,
    *,
    inv_agent: Any = None,
    dir_agent: Any = None,
) -> Any:
    """Build and return the moment workflow graph."""
    inv_exec = InvestigatorExecutor(client=client, kql=kql, timeout_s=timeout_s, _agent=inv_agent)
    dir_exec = DirectorExecutor(client=client, timeout_s=timeout_s, _agent=dir_agent)
    val_exec = ValidatorExecutor()
    ovl_exec = OverlayExecutor()
    tpl_exec = TemplateExecutor()

    return (
        WorkflowBuilder(start_executor=inv_exec, max_iterations=10)
        .add_switch_case_edge_group(
            inv_exec,
            [Case(condition=lambda m: m.ok, target=dir_exec), Default(target=tpl_exec)],
        )
        .add_switch_case_edge_group(
            dir_exec,
            [Case(condition=lambda m: m.ok, target=val_exec), Default(target=tpl_exec)],
        )
        .add_switch_case_edge_group(
            val_exec,
            [
                Case(condition=lambda m: m.passed, target=ovl_exec),
                Case(condition=lambda m: not m.passed and m.attempt == 1, target=dir_exec),
                Default(target=tpl_exec),
            ],
        )
        .build()
    )


# ---------------------------------------------------------------------------
# Public entry point
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
    inv_agent: Any = None
    dir_agent: Any = None
    if _agents is not None:
        inv_agent, dir_agent = _agents

    workflow = _build_workflow(client, kql, timeout_s, inv_agent=inv_agent, dir_agent=dir_agent)
    result = await workflow.run(_Start(packet=packet, twin=twin, roster=roster))
    outputs = result.get_outputs()
    done: _Done = outputs[0]
    return done.overlay, done.log
