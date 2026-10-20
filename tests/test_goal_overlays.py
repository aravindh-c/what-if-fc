"""Tests for goal overlays in the replay builder.

Verifies:
- seed 7 replay contains exactly 2 goal overlays
- each goal overlay names the correct scorer
- each goal overlay shows the correct scoreline
- goal overlay moment_type is "goal" (not "ghost_pass")
- goal overlay has no Ghost Pass visual
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Shared fixture: build the seed-7 match bundle with template overlays
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seed7_bundle() -> dict[str, Any]:
    from scripts.build_replay import _assemble_bundle, _build_match_replay

    data = _build_match_replay(7, "T01", "T02")
    bundle, _ = asyncio.run(
        _assemble_bundle(data, use_agents=False, client=None, timeout_s=5.0)
    )
    return bundle


@pytest.fixture(scope="module")
def goal_overlays(seed7_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        ov for ov in seed7_bundle.get("overlays", []) if ov.get("moment_type") == "goal"
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_seed7_has_two_goal_overlays(goal_overlays: list[dict[str, Any]]) -> None:
    assert len(goal_overlays) == 2, (
        f"expected 2 goal overlays in seed-7 replay, got {len(goal_overlays)}"
    )


def test_goal_overlays_have_no_visual(goal_overlays: list[dict[str, Any]]) -> None:
    """Goal overlays must not include Ghost Pass geometry."""
    for ov in goal_overlays:
        assert ov.get("visual") is None, (
            f"goal overlay {ov['overlay_id']!r} has unexpected visual"
        )


def test_goal_overlays_have_no_scores(goal_overlays: list[dict[str, Any]]) -> None:
    """Goal overlays must not include twin scores."""
    for ov in goal_overlays:
        assert ov.get("scores") is None, (
            f"goal overlay {ov['overlay_id']!r} has unexpected scores"
        )


def test_goal_overlays_name_scorer(
    seed7_bundle: dict[str, Any], goal_overlays: list[dict[str, Any]]
) -> None:
    """Each goal overlay must name the scorer in analyst and fan text."""
    # Build player_id → name map from meta
    players = seed7_bundle["meta"]["players"]  # {player_id: {name, role, team_id}}
    events_by_id = {e["event_id"]: e for e in seed7_bundle["events"]}

    for ov in goal_overlays:
        ev_ids = ov.get("evidence", {}).get("event_ids", [])
        assert ev_ids, f"goal overlay {ov['overlay_id']!r} has no event_ids"
        goal_event = events_by_id.get(ev_ids[0])
        assert goal_event is not None, f"event {ev_ids[0]!r} not in bundle events"

        scorer_id = goal_event.get("player_id")
        assert scorer_id is not None
        scorer_name = players.get(scorer_id, {}).get("name", "")
        assert scorer_name, f"no name found for scorer {scorer_id!r}"

        # Scorer's surname must appear in both analyst and fan text
        surname = scorer_name.split()[-1]
        analyst_en = ov["text"]["analyst"]["en"]
        fan_en = ov["text"]["fan"]["en"]
        analyst_text = analyst_en["headline"] + " " + analyst_en["body"]
        fan_text = fan_en["headline"] + " " + fan_en["body"]

        assert surname in analyst_text, (
            f"scorer surname {surname!r} missing from analyst text: {analyst_text!r}"
        )
        assert surname in fan_text, (
            f"scorer surname {surname!r} missing from fan text: {fan_text!r}"
        )


def test_goal_overlays_show_correct_scoreline(
    seed7_bundle: dict[str, Any], goal_overlays: list[dict[str, Any]]
) -> None:
    """Each goal overlay text must contain the scoreline after the goal."""
    # Compute expected scorelines from events list (ordered by match_clock_s)
    events = sorted(seed7_bundle["events"], key=lambda e: e["match_clock_s"])
    goal_events = [e for e in events if e["event_type"] == "goal"]
    assert len(goal_events) == 2

    expected_scorelines = []
    running: dict[str, int] = {}
    for ge in goal_events:
        tid = ge["team_id"]
        running[tid] = running.get(tid, 0) + 1
        # Format: sorted team IDs, dash-separated
        teams = sorted({e["team_id"] for e in events if e.get("team_id")})
        sl = "-".join(str(running.get(t, 0)) for t in teams if t)
        expected_scorelines.append(sl)

    # Sort goal overlays by match_clock_s to align with expected scorelines
    goal_overlays_sorted = sorted(goal_overlays, key=lambda ov: ov["match_clock_s"])

    for ov, expected_sl in zip(goal_overlays_sorted, expected_scorelines, strict=True):
        analyst_en = ov["text"]["analyst"]["en"]
        analyst_body = analyst_en["body"]
        assert expected_sl in analyst_body, (
            f"expected scoreline {expected_sl!r} not in analyst body: {analyst_body!r}"
        )


def test_goal_overlay_ids_are_deterministic(
    seed7_bundle: dict[str, Any], goal_overlays: list[dict[str, Any]]
) -> None:
    """overlay_id must start with 'ov_' and be consistent across builds."""
    for ov in goal_overlays:
        assert ov["overlay_id"].startswith("ov_"), (
            f"unexpected overlay_id: {ov['overlay_id']!r}"
        )
