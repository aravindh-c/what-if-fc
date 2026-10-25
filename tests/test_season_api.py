"""Tests for GET /api/season and related helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURE = Path("tests/fixtures/season.json")


def _client() -> TestClient:
    from api.main import app

    return TestClient(app)


def _fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 200 — fixture on disk
# ---------------------------------------------------------------------------


def test_season_200(monkeypatch):
    """Returns 200 when load_season returns data."""
    import json

    import api.season as season_mod

    data = json.loads(_fixture_text())
    monkeypatch.setattr(season_mod, "load_season", lambda: data)

    resp = _client().get("/api/season")
    assert resp.status_code == 200
    assert resp.json()["version"] == 1
    assert len(resp.json()["standings"]) == 4


# ---------------------------------------------------------------------------
# 404 — no file
# ---------------------------------------------------------------------------


def test_season_404(monkeypatch):
    """Returns 404 when load_season returns None."""
    import api.season as season_mod

    monkeypatch.setattr(season_mod, "load_season", lambda: None)

    resp = _client().get("/api/season")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "season not built yet"


# ---------------------------------------------------------------------------
# Enrichment (tests _enrich directly — no Azure path involved)
# ---------------------------------------------------------------------------


def test_season_standings_have_team_names():
    """Each standings row has team_name and team_color after enrichment."""
    import json

    import api.season as season_mod

    raw = json.loads(_fixture_text())
    result = season_mod._enrich(raw)
    for row in result["standings"]:
        assert "team_name" in row, f"missing team_name on {row['team_id']}"
        assert row["team_name"]
        assert "team_color" in row


# ---------------------------------------------------------------------------
# Standings order
# ---------------------------------------------------------------------------


def test_season_standings_order():
    """Standings in the fixture are ordered by points descending."""
    import json

    points = [r["points"] for r in json.loads(_fixture_text())["standings"]]
    assert points == sorted(points, reverse=True)


# ---------------------------------------------------------------------------
# Cache reuse (mocks _raw_season to avoid Azure path)
# ---------------------------------------------------------------------------


def test_season_cache_reuse(monkeypatch):
    """load_season() returns the same object within TTL."""
    import json

    import api.season as season_mod

    raw = json.loads(_fixture_text())
    monkeypatch.setattr(season_mod, "_raw_season", lambda: raw)
    monkeypatch.setattr(season_mod, "_cache", None)
    monkeypatch.setattr(season_mod, "_cache_at", 0.0)

    first = season_mod.load_season()
    second = season_mod.load_season()
    assert first is not None
    assert first is second


# ---------------------------------------------------------------------------
# BlobReplayStore.list_ids skips gold/season.json
# ---------------------------------------------------------------------------


def test_blob_list_ids_skips_path_blobs():
    """BlobReplayStore.list_ids must skip blobs whose name contains '/'."""
    from api.replay_store import BlobReplayStore

    class _FakeBlob:
        def __init__(self, name: str) -> None:
            self.name = name

    fake_blobs = [
        _FakeBlob("match_s7_T01_T02.json"),
        _FakeBlob("gold/season.json"),
        _FakeBlob("live_match_s7.json"),
        _FakeBlob("scenario_forced_pass.json"),
    ]

    store = BlobReplayStore.__new__(BlobReplayStore)
    store._container = "test"

    class _FakeCC:
        def list_blobs(self):
            return fake_blobs

    class _FakeClient:
        def get_container_client(self, _):
            return _FakeCC()

    store._client = _FakeClient()
    ids = store.list_ids()

    assert ids == ["match_s7_T01_T02", "scenario_forced_pass"]
    assert "gold/season" not in ids
