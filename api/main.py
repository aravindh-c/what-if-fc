"""FastAPI replay API for What If FC.

Endpoints:
  GET /health
  GET /api/replays
  GET /api/replays/{replay_id}
  GET /api/replays/{replay_id}/overlays?since_clock_s=N

Run with:
  uvicorn api.main:app --reload
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

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
    allow_methods=["GET"],
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
