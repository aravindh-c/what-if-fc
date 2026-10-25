"""Tests for live API endpoints: /meta shape, CORS headers, async watch_match."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

CLIENT = TestClient(app, raise_server_exceptions=False)
ORIGIN = "http://localhost:5173"


# ---------------------------------------------------------------------------
# /meta shape
# ---------------------------------------------------------------------------


def _fake_meta(match_id: str) -> dict:
    return {
        "replay_id": match_id,
        "kind": "match",
        "title": "Home FC vs Away FC",
        "teams": {
            "T01": {
                "name": "Home FC", "short_name": "HOM",
                "formation": "4-3-3", "style": "possession",
            },
            "T02": {
                "name": "Away FC", "short_name": "AWY",
                "formation": "4-4-2", "style": "counter",
            },
        },
        "players": {
            f"T01-P{i:02d}": {
                "name": f"P{i}", "role": "midfielder",
                "team_id": "T01", "shirt_number": i,
            }
            for i in range(1, 23)
        },
        "built_at": "2026-01-01T00:00:00Z",
        "twin_version": "twin-v1",
    }


def test_live_meta_shape():
    with patch("agents.moments.build_live_meta", side_effect=_fake_meta):
        resp = CLIENT.get("/api/live/match_s7_T01_T02/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert data["replay_id"] == "match_s7_T01_T02"
    assert len(data["teams"]) == 2
    assert len(data["players"]) == 22
    assert "twin_version" in data
    assert "built_at" in data


def test_live_meta_includes_team_fields():
    with patch("agents.moments.build_live_meta", side_effect=_fake_meta):
        resp = CLIENT.get("/api/live/match_s7_T01_T02/meta")
    data = resp.json()
    team = data["teams"]["T01"]
    assert "name" in team
    assert "short_name" in team
    assert "formation" in team


# ---------------------------------------------------------------------------
# CORS headers on live endpoints
# ---------------------------------------------------------------------------


def test_cors_header_on_state_404():
    """A 404 from /state must still include Access-Control-Allow-Origin."""
    resp = CLIENT.get(
        "/api/live/nonexistent_match/state",
        headers={"Origin": ORIGIN},
    )
    assert resp.status_code == 404
    assert resp.headers.get("access-control-allow-origin") == ORIGIN


def test_cors_header_on_meta_404():
    """A 404 from /meta must still include Access-Control-Allow-Origin."""
    with patch("agents.moments.build_live_meta", side_effect=Exception("not found")):
        resp = CLIENT.get(
            "/api/live/bad_match/meta",
            headers={"Origin": ORIGIN},
        )
    assert resp.status_code == 404
    assert resp.headers.get("access-control-allow-origin") == ORIGIN


# ---------------------------------------------------------------------------
# POST /watch returns 202 and watcher task is running
# ---------------------------------------------------------------------------


def _fake_kql():
    kql = MagicMock()
    kql.live_matches.return_value = []
    kql.events_since.return_value = []
    return kql


def test_watch_returns_202_and_task_running():
    """POST /watch must return 202 and start a background watcher task."""
    match_id = "match_s7_T01_T02"

    with (
        patch("api.main._make_kql", return_value=_fake_kql()),
        patch("api.live._make_agent_client", return_value=None),
    ):
        resp = CLIENT.post(f"/api/live/{match_id}/watch")

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "watching"
    assert data["match_id"] == match_id

    # Watcher task should be registered
    from api.live import get_state

    state = get_state(match_id)
    assert state is not None
    assert state.task is not None
    # Clean up
    state.task.cancel()
