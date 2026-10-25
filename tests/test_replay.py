"""Tests for replay builder, store, and API.

AT-10: two builds with --no-agents produce identical bundles (modulo built_at)
AT-06: every overlay's match_clock_s corresponds to an event in the bundle
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixtures: shared replay bundle built with template-only (no agents)
# ---------------------------------------------------------------------------


def _build_scenario_bundle(scenario_id: str) -> dict[str, Any]:
    from scripts.build_replay import _assemble_bundle, _build_scenario_replay

    data = _build_scenario_replay(scenario_id)
    bundle, _ = asyncio.run(
        _assemble_bundle(data, use_agents=False, client=None, timeout_s=5.0)
    )
    return bundle


@pytest.fixture(scope="module")
def missed_overlap_bundle() -> dict[str, Any]:
    return _build_scenario_bundle("missed_overlap_right")


@pytest.fixture(scope="module")
def missed_overlap_bundle2() -> dict[str, Any]:
    """Second independent build — used for AT-10 determinism check."""
    return _build_scenario_bundle("missed_overlap_right")


# ---------------------------------------------------------------------------
# AT-10: determinism — two builds are identical except built_at
# ---------------------------------------------------------------------------


def test_builder_deterministic_no_agents(
    missed_overlap_bundle: dict[str, Any],
    missed_overlap_bundle2: dict[str, Any],
) -> None:
    """AT-10: two template-only builds produce the same events, overlays, metrics."""
    b1 = dict(missed_overlap_bundle)
    b2 = dict(missed_overlap_bundle2)

    # Strip timestamps before comparing
    b1["meta"] = {k: v for k, v in b1["meta"].items() if k != "built_at"}
    b2["meta"] = {k: v for k, v in b2["meta"].items() if k != "built_at"}

    assert json.dumps(b1, sort_keys=True) == json.dumps(b2, sort_keys=True), (
        "AT-10: replay bundles differ between two template-only builds"
    )


# ---------------------------------------------------------------------------
# AT-06: overlay event IDs exist in bundle events
# ---------------------------------------------------------------------------


def test_overlay_event_ids_in_bundle_events(missed_overlap_bundle: dict[str, Any]) -> None:
    """AT-06: every overlay's triggering event_id appears in the bundle's events list."""
    bundle_event_ids = {e["event_id"] for e in missed_overlap_bundle.get("events", [])}
    for overlay in missed_overlap_bundle.get("overlays", []):
        ov_event_ids = overlay.get("evidence", {}).get("event_ids", [])
        for eid in ov_event_ids:
            assert eid in bundle_event_ids, (
                f"AT-06: overlay references event_id {eid!r} not in bundle events"
            )


# ---------------------------------------------------------------------------
# Bundle structure: required top-level keys present
# ---------------------------------------------------------------------------


def test_bundle_has_required_keys(missed_overlap_bundle: dict[str, Any]) -> None:
    for key in ("meta", "events", "snapshots", "metrics", "headline_moments", "overlays"):
        assert key in missed_overlap_bundle, f"bundle missing required key {key!r}"


def test_bundle_meta_fields(missed_overlap_bundle: dict[str, Any]) -> None:
    meta = missed_overlap_bundle["meta"]
    for field in ("replay_id", "kind", "title", "teams", "players", "built_at", "twin_version"):
        assert field in meta, f"meta missing field {field!r}"
    assert meta["kind"] == "scenario"


def test_overlays_have_deterministic_ids(missed_overlap_bundle: dict[str, Any]) -> None:
    """overlay_id must start with 'ov_'."""
    for overlay in missed_overlap_bundle.get("overlays", []):
        assert overlay["overlay_id"].startswith("ov_"), (
            f"overlay_id {overlay['overlay_id']!r} does not start with 'ov_'"
        )


def test_bundle_has_ledgers(missed_overlap_bundle: dict[str, Any]) -> None:
    """Every overlay must have a corresponding ledger with required fields."""
    assert "ledgers" in missed_overlap_bundle, "bundle missing 'ledgers' key"
    ledgers = missed_overlap_bundle["ledgers"]
    required_keys = {"packet", "events", "candidates", "formula", "run"}
    for overlay in missed_overlap_bundle.get("overlays", []):
        ov_id = overlay["overlay_id"]
        assert ov_id in ledgers, f"overlay {ov_id!r} has no ledger"
        ledger = ledgers[ov_id]
        for key in required_keys:
            assert key in ledger, f"ledger for {ov_id!r} missing field {key!r}"
        formula = ledger["formula"]
        for fkey in ("version", "weights", "ghost_rule"):
            assert fkey in formula, f"ledger formula for {ov_id!r} missing {fkey!r}"
        run = ledger["run"]
        for rkey in ("source", "attempts"):
            assert rkey in run, f"ledger run for {ov_id!r} missing {rkey!r}"


def test_ledger_candidate_scores_match_overlay(missed_overlap_bundle: dict[str, Any]) -> None:
    """The actual and ghost candidate S values must match the overlay scores."""
    ledgers = missed_overlap_bundle.get("ledgers", {})
    for overlay in missed_overlap_bundle.get("overlays", []):
        ov_id = overlay["overlay_id"]
        scores = overlay.get("scores")
        if scores is None:
            continue
        ledger = ledgers.get(ov_id)
        if ledger is None:
            continue
        candidates = ledger["candidates"]
        actual_cands = [c for c in candidates if c.get("is_actual")]
        ghost_cands = [c for c in candidates if not c.get("is_actual")]
        if actual_cands:
            ledger_s = actual_cands[0]["S"]
            overlay_s = scores["actual"]
            assert abs(ledger_s - overlay_s) < 0.001, (
                f"{ov_id}: ledger actual S {ledger_s} != overlay actual {overlay_s}"
            )
        if ghost_cands:
            ledger_s = ghost_cands[0]["S"]
            overlay_s = scores["ghost"]
            assert abs(ledger_s - overlay_s) < 0.001, (
                f"{ov_id}: ledger ghost S {ledger_s} != overlay ghost {overlay_s}"
            )


# ---------------------------------------------------------------------------
# LocalReplayStore tests
# ---------------------------------------------------------------------------


def _write_bundle(tmp_dir: Path, replay_id: str, bundle: dict[str, Any]) -> None:
    (tmp_dir / f"{replay_id}.json").write_text(json.dumps(bundle), encoding="utf-8")


def _make_bundle(replay_id: str) -> dict[str, Any]:
    return {
        "meta": {
            "replay_id": replay_id,
            "kind": "scenario",
            "title": "Test",
            "teams": {},
            "players": {},
            "built_at": "2026-10-20T00:00:00+00:00",
            "twin_version": "twin-v1",
        },
        "events": [{"event_id": "ev_001", "match_clock_s": 120}],
        "snapshots": [],
        "metrics": {},
        "headline_moments": [],
        "overlays": [
            {
                "overlay_id": "ov_abc123",
                "match_id": replay_id,
                "match_clock_s": 120,
                "evidence": {"event_ids": ["ev_001"]},
            }
        ],
    }


def test_local_store_list_ids() -> None:
    from api.replay_store import LocalReplayStore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _write_bundle(tmp_dir, "replay_a", _make_bundle("replay_a"))
        _write_bundle(tmp_dir, "replay_b", _make_bundle("replay_b"))
        store = LocalReplayStore(directory=tmp_dir)
        ids = store.list_ids()
        assert ids == ["replay_a", "replay_b"]


def test_local_store_excludes_live_files() -> None:
    """live_*.json files written by the watcher must not appear in the catalog."""
    from api.replay_store import LocalReplayStore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _write_bundle(tmp_dir, "replay_a", _make_bundle("replay_a"))
        _write_bundle(tmp_dir, "live_match_s7_T01_T02", _make_bundle("live_match_s7_T01_T02"))
        store = LocalReplayStore(directory=tmp_dir)
        ids = store.list_ids()
        assert ids == ["replay_a"]
        assert "live_match_s7_T01_T02" not in ids


def test_local_store_load() -> None:
    from api.replay_store import LocalReplayStore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        bundle = _make_bundle("replay_x")
        _write_bundle(tmp_dir, "replay_x", bundle)
        store = LocalReplayStore(directory=tmp_dir)
        loaded = store.load("replay_x")
        assert loaded is not None
        assert loaded["meta"]["replay_id"] == "replay_x"


def test_local_store_missing() -> None:
    from api.replay_store import LocalReplayStore

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalReplayStore(directory=Path(tmp))
        assert store.load("nonexistent") is None


def test_local_store_caches() -> None:
    from api.replay_store import LocalReplayStore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _write_bundle(tmp_dir, "r1", _make_bundle("r1"))
        store = LocalReplayStore(directory=tmp_dir)
        b1 = store.load("r1")
        # Overwrite file with different content
        _write_bundle(tmp_dir, "r1", _make_bundle("r1_modified"))
        b2 = store.load("r1")
        assert b1 is b2  # same object from cache


# ---------------------------------------------------------------------------
# API tests with TestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client():
    import tempfile

    from fastapi.testclient import TestClient

    from api import main as api_module
    from api.replay_store import LocalReplayStore

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _write_bundle(tmp_dir, "scenario_test_a", _make_bundle("scenario_test_a"))
        _write_bundle(tmp_dir, "scenario_test_b", _make_bundle("scenario_test_b"))

        store = LocalReplayStore(directory=tmp_dir)
        # Inject store into the app
        api_module._store = store

        with TestClient(api_module.app) as client:
            yield client

        # Reset global store so other tests start fresh
        api_module._store = None


def test_health(api_client) -> None:
    resp = api_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "store" in data


def test_list_replays(api_client) -> None:
    resp = api_client.get("/api/replays")
    assert resp.status_code == 200
    catalog = resp.json()
    ids = [r["replay_id"] for r in catalog]
    assert "scenario_test_a" in ids
    assert "scenario_test_b" in ids


def test_get_replay(api_client) -> None:
    resp = api_client.get("/api/replays/scenario_test_a")
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["meta"]["replay_id"] == "scenario_test_a"


def test_get_replay_404(api_client) -> None:
    resp = api_client.get("/api/replays/does_not_exist")
    assert resp.status_code == 404


def test_get_overlays(api_client) -> None:
    resp = api_client.get("/api/replays/scenario_test_a/overlays")
    assert resp.status_code == 200
    overlays = resp.json()
    assert len(overlays) == 1
    assert overlays[0]["match_clock_s"] == 120


def test_get_overlays_since(api_client) -> None:
    resp = api_client.get("/api/replays/scenario_test_a/overlays?since_clock_s=120")
    assert resp.status_code == 200
    # clock_s=120 is NOT strictly greater than 120, so result is empty
    assert resp.json() == []


def test_get_overlays_404(api_client) -> None:
    resp = api_client.get("/api/replays/no_such_replay/overlays")
    assert resp.status_code == 404
