"""Replay bundle store: protocol + Local and Blob implementations.

Factory function `make_store()` returns the right implementation based on
environment variables:
  REPLAY_STORAGE_ACCOUNT_URL  → BlobReplayStore
  (not set)                   → LocalReplayStore (reads data/replay/)

Both implementations cache loaded bundles in memory.

No secrets are ever logged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_LOCAL_DIR = Path(__file__).parent.parent / "data" / "replay"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ReplayStore(Protocol):
    def list_ids(self) -> list[str]: ...
    def load(self, replay_id: str) -> dict[str, Any] | None: ...


# ---------------------------------------------------------------------------
# Local implementation
# ---------------------------------------------------------------------------


class LocalReplayStore:
    """Reads bundles from *data/replay/*.json* (git-ignored)."""

    def __init__(self, directory: Path = _LOCAL_DIR) -> None:
        self._dir = directory
        self._cache: dict[str, dict[str, Any]] = {}

    def list_ids(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(
            p.stem
            for p in self._dir.glob("*.json")
            if not p.stem.startswith("live_")
        )

    def load(self, replay_id: str) -> dict[str, Any] | None:
        if replay_id in self._cache:
            return self._cache[replay_id]
        path = self._dir / f"{replay_id}.json"
        if not path.exists():
            return None
        bundle: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self._cache[replay_id] = bundle
        return bundle


# ---------------------------------------------------------------------------
# Blob implementation
# ---------------------------------------------------------------------------


class BlobReplayStore:
    """Reads bundles from Azure Blob Storage using DefaultAzureCredential.

    Required env vars:
      REPLAY_STORAGE_ACCOUNT_URL  e.g. https://<account>.blob.core.windows.net
      REPLAY_CONTAINER            container name (default: replays)
    """

    def __init__(
        self,
        account_url: str,
        container: str = "replays",
    ) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        credential = DefaultAzureCredential()
        self._client = BlobServiceClient(account_url=account_url, credential=credential)
        self._container = container
        self._cache: dict[str, dict[str, Any]] = {}

    def list_ids(self) -> list[str]:
        container_client = self._client.get_container_client(self._container)
        return sorted(
            b.name[:-5]  # strip .json
            for b in container_client.list_blobs()
            if b.name.endswith(".json") and not b.name.startswith("live_")
        )

    def load(self, replay_id: str) -> dict[str, Any] | None:
        if replay_id in self._cache:
            return self._cache[replay_id]
        blob_client = self._client.get_blob_client(
            container=self._container, blob=f"{replay_id}.json"
        )
        try:
            data = blob_client.download_blob().readall()
        except Exception:
            return None
        bundle: dict[str, Any] = json.loads(data)
        self._cache[replay_id] = bundle
        return bundle


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_store() -> ReplayStore:
    """Return the appropriate store based on environment configuration."""
    account_url = os.environ.get("REPLAY_STORAGE_ACCOUNT_URL", "").strip()
    if account_url:
        container = os.environ.get("REPLAY_CONTAINER", "replays")
        return BlobReplayStore(account_url=account_url, container=container)
    return LocalReplayStore()
