"""FastAPI replay API for What If FC.

Endpoints:
  GET  /health
  GET  /api/replays
  GET  /api/replays/{replay_id}
  GET  /api/replays/{replay_id}/overlays?since_clock_s=N
  GET  /api/season
  GET  /api/live/matches
  POST /api/live/{match_id}/watch
  GET  /api/live/{match_id}/state?since_clock_s=N
  GET  /api/live/{match_id}/overlays?since_clock_s=N
  POST /api/live/{match_id}/simulate-outage

Run with:
  uvicorn api.main:app --reload
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.replay_store import ReplayStore, make_store

load_dotenv()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="What If FC – Replay API",
    description="Serves pre-built replay bundles for the What If FC frontend.",
    version="0.1.0",
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Dependency: store
# ---------------------------------------------------------------------------

_store: ReplayStore | None = None


def _get_store() -> ReplayStore:
    global _store  # noqa: PLW0603
    if _store is None:
        _store = make_store()
    return _store


def get_store(store: ReplayStore = Depends(_get_store)) -> ReplayStore:  # noqa: B008
    return store


# ---------------------------------------------------------------------------
# Helper: detect store mode
# ---------------------------------------------------------------------------


def _store_mode() -> str:
    return "blob" if os.environ.get("REPLAY_STORAGE_ACCOUNT_URL", "").strip() else "local"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "mode": "replay", "store": _store_mode()}


@app.get("/api/replays")
def list_replays(store: ReplayStore = Depends(get_store)) -> list[dict[str, Any]]:  # noqa: B008
    """Return a catalog of available replays.

    Each entry contains replay_id, kind, title, and the count of overlays.
    """
    catalog: list[dict[str, Any]] = []
    for rid in store.list_ids():
        bundle = store.load(rid)
        if bundle is None:
            continue
        meta = bundle.get("meta", {})
        overlays = bundle.get("overlays", [])
        catalog.append(
            {
                "replay_id": meta.get("replay_id", rid),
                "kind": meta.get("kind", "unknown"),
                "title": meta.get("title", rid),
                "overlays": len(overlays),
                "description": meta.get("scenario_description") or "",
            }
        )
    return catalog


@app.get("/api/replays/{replay_id}")
def get_replay(
    replay_id: str, store: ReplayStore = Depends(get_store)  # noqa: B008
) -> dict[str, Any]:
    """Return the full replay bundle for *replay_id*."""
    bundle = store.load(replay_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"replay {replay_id!r} not found")
    return bundle


@app.get("/api/replays/{replay_id}/overlays")
def get_overlays(
    replay_id: str,
    since_clock_s: int = 0,
    store: ReplayStore = Depends(get_store),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return overlays with match_clock_s > since_clock_s (AT-11 live-update shape).

    Parameters
    ----------
    replay_id:
        The replay bundle identifier.
    since_clock_s:
        Return only overlays whose match_clock_s is strictly greater than this
        value. Defaults to 0 (returns all overlays).
    """
    bundle = store.load(replay_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"replay {replay_id!r} not found")
    overlays: list[dict[str, Any]] = bundle.get("overlays", [])
    return [ov for ov in overlays if ov.get("match_clock_s", 0) > since_clock_s]


# ---------------------------------------------------------------------------
# Season endpoint
# ---------------------------------------------------------------------------


@app.get("/api/season")
def get_season() -> dict[str, Any]:
    """Return the enriched season summary built from the Fabric gold layer.

    Returns 404 when the gold-layer season.json has not been generated yet.
    """
    from api.season import load_season

    data = load_season()
    if data is None:
        raise HTTPException(status_code=404, detail="season not built yet")
    return data


# ---------------------------------------------------------------------------
# Live endpoints
# ---------------------------------------------------------------------------


def _make_kql() -> Any:
    """Build a FabricKql from environment variables, or raise if not configured."""
    cluster_uri = os.environ.get("KQL_CLUSTER_URI", "").strip()
    database = os.environ.get("KQL_DATABASE", "").strip()
    if not cluster_uri or not database:
        raise HTTPException(
            status_code=503,
            detail="Live mode not configured: set KQL_CLUSTER_URI and KQL_DATABASE",
        )
    from agents.kql_tools import FabricKql

    return FabricKql(cluster_uri, database)


@app.get("/api/live/matches")
def live_matches() -> list[dict[str, Any]]:
    """Return matches that received Fabric events in the last 30 minutes."""
    kql = _make_kql()
    return kql.live_matches()


@app.get("/api/live/{match_id}/meta")
def live_meta(match_id: str) -> dict[str, Any]:
    """Return match metadata (teams, players) in the same shape as replay bundles."""
    from agents.moments import build_live_meta

    try:
        return build_live_meta(match_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/live/{match_id}/watch", status_code=202)
async def watch_match(match_id: str) -> dict[str, str]:
    """Start the background watcher for *match_id*."""
    from agents.kql_tools import _validate_match_id  # noqa: PLC2701

    try:
        _validate_match_id(match_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    kql = _make_kql()
    from api.live import start_watcher

    start_watcher(match_id, kql)
    return {"status": "watching", "match_id": match_id}


@app.get("/api/live/{match_id}/state")
def live_state(match_id: str, since_clock_s: int = 0) -> dict[str, Any]:
    """Current live state: clock, score, latest snapshot, events since since_clock_s."""
    from api.live import get_state

    state = get_state(match_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"match {match_id!r} not watched")

    # Latest snapshot from watcher's cache; possession team from referencing event
    latest_snapshot: dict[str, Any] | None = None
    possession_team_id: str | None = None
    if state.snap_cache:
        best = max(state.snap_cache.values(), key=lambda s: s.match_clock_s)
        latest_snapshot = {
            "snapshot_id": best.snapshot_id,
            "match_id": best.match_id,
            "match_clock_s": best.match_clock_s,
            "positions": [p.model_dump() for p in best.positions],
        }
        for ev in reversed(state.events):
            if ev.snapshot_id == best.snapshot_id and ev.team_id:
                possession_team_id = ev.team_id
                break

    # Events accumulated since since_clock_s
    events_out = [
        {
            "event_id": e.event_id,
            "match_clock_s": e.match_clock_s,
            "event_type": e.event_type.value,
            "team_id": e.team_id,
            "player_id": e.player_id,
        }
        for e in state.events
        if e.match_clock_s > since_clock_s
    ]

    return {
        "match_id": match_id,
        "clock_s": state.clock_s,
        "score": state.score,
        "latest_snapshot": latest_snapshot,
        "possession_team_id": possession_team_id,
        "events": events_out,
        "skipped_rows": state.skipped_rows,
        "overlay_count": len(state.overlays),
        "simulate_outage": state.simulate_outage,
    }


@app.get("/api/live/{match_id}/overlays")
def live_overlays(match_id: str, since_clock_s: int = 0) -> list[dict[str, Any]]:
    """Return overlays with match_clock_s > since_clock_s, each with its ledger and frame team."""
    from api.live import get_state

    state = get_state(match_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"match {match_id!r} not watched")

    events_by_id = {e.event_id: e for e in state.events}
    result: list[dict[str, Any]] = []
    for ov in state.overlays:
        if ov.get("match_clock_s", 0) <= since_clock_s:
            continue
        ov_id = ov["overlay_id"]
        frame_team_id: str | None = None
        ev_ids = ov.get("evidence", {}).get("event_ids", [])
        if ev_ids:
            src_ev = events_by_id.get(ev_ids[0])
            if src_ev and src_ev.team_id:
                frame_team_id = src_ev.team_id
        result.append({**ov, "ledger": state.ledgers.get(ov_id), "frame_team_id": frame_team_id})
    return result


@app.post("/api/live/{match_id}/simulate-outage", status_code=200)
def simulate_outage(match_id: str, enabled: bool = True) -> dict[str, Any]:
    """Toggle the simulate-outage flag for *match_id*.

    When enabled the next overlay uses the template fallback path instead of
    calling the agents, mimicking a model service interruption.
    """
    from api.live import get_state, set_simulate_outage

    if get_state(match_id) is None:
        raise HTTPException(status_code=404, detail=f"match {match_id!r} not watched")
    set_simulate_outage(match_id, enabled)
    return {"match_id": match_id, "simulate_outage": enabled}


# ---------------------------------------------------------------------------
# Static files + SPA fallback (must come after all API routes)
# ---------------------------------------------------------------------------

_DIST = Path(__file__).parent.parent / "web" / "dist"

if _DIST.is_dir():
    # Serve Vite asset bundles (JS/CSS) at /assets
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="static_assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:  # noqa: ARG001
    """Return index.html for every non-API path (SPA client-side routing)."""
    if _DIST.is_dir():
        return FileResponse(_DIST / "index.html")
    raise HTTPException(status_code=404, detail="Frontend not built — run 'npm run build' in web/")
