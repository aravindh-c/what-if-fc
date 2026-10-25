"""Season summary loader: reads the gold-layer season.json and enriches it."""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from typing import Any

from simulator.reference_data import build_players, build_teams

_LOCAL_PATH = Path(__file__).parent.parent / "data" / "gold" / "season.json"
_BLOB_PATH = "gold/season.json"
_TTL = 60.0

_cache: dict[str, Any] | None = None
_cache_at: float = 0.0


def _raw_season() -> dict[str, Any] | None:
    """Load raw season JSON from blob storage or local file."""
    account_url = os.environ.get("REPLAY_STORAGE_ACCOUNT_URL", "").strip()
    if account_url:
        container = os.environ.get("REPLAY_CONTAINER", "replays")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient

            credential = DefaultAzureCredential()
            client = BlobServiceClient(account_url=account_url, credential=credential)
            blob = client.get_blob_client(container=container, blob=_BLOB_PATH)
            data = blob.download_blob().readall()
            return json.loads(data)
        except Exception:
            return None
    if not _LOCAL_PATH.exists():
        return None
    return json.loads(_LOCAL_PATH.read_text(encoding="utf-8"))


def _enrich(season: dict[str, Any]) -> dict[str, Any]:
    """Add team_name, team_color and player name/shirt_number from reference data."""
    season = copy.deepcopy(season)
    team_map = {t.team_id: t for t in build_teams()}

    for row in season.get("standings", []):
        t = team_map.get(row["team_id"])
        if t:
            row["team_name"] = t.name
            row["team_color"] = t.primary_color

    for row in season.get("team_totals", []):
        t = team_map.get(row["team_id"])
        if t:
            row["team_name"] = t.name
            row["team_color"] = t.primary_color

    for match in season.get("matches", []):
        seed = match.get("seed")
        player_map = (
            {p.player_id: p for p in build_players(seed)} if seed is not None else {}
        )
        for team_id, stats in match.get("teams", {}).items():
            t = team_map.get(team_id)
            if t:
                stats["team_name"] = t.name
                stats["team_color"] = t.primary_color
        for p_row in match.get("top_players", []):
            p = player_map.get(p_row["player_id"])
            if p:
                p_row["name"] = p.name
                p_row["shirt_number"] = p.shirt_number

    return season


def load_season() -> dict[str, Any] | None:
    """Return enriched season data. Results are cached for 60 seconds."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _TTL:
        return _cache
    raw = _raw_season()
    if raw is None:
        _cache = None
        return None
    enriched = _enrich(raw)
    _cache = enriched
    _cache_at = now
    return enriched
