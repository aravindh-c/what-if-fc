"""Tests for the frames possession-frame index in replay bundles."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


@pytest.fixture(scope="module")
def seed7_bundle() -> dict[str, Any]:
    from scripts.build_replay import _assemble_bundle, _build_match_replay

    data = _build_match_replay(7, "T01", "T02")
    bundle, _ = asyncio.run(
        _assemble_bundle(data, use_agents=False, client=None, timeout_s=5.0)
    )
    return bundle


def test_frames_key_present(seed7_bundle: dict[str, Any]) -> None:
    assert "frames" in seed7_bundle
    assert "snapshots" in seed7_bundle["frames"]
    assert "overlays" in seed7_bundle["frames"]


def test_frames_snapshots_nonempty(seed7_bundle: dict[str, Any]) -> None:
    assert len(seed7_bundle["frames"]["snapshots"]) > 0


def test_frames_overlays_nonempty(seed7_bundle: dict[str, Any]) -> None:
    assert len(seed7_bundle["frames"]["overlays"]) > 0


def test_frames_snapshot_ids_exist_in_bundle(seed7_bundle: dict[str, Any]) -> None:
    snap_ids = {s["snapshot_id"] for s in seed7_bundle["snapshots"]}
    for sid in seed7_bundle["frames"]["snapshots"]:
        assert sid in snap_ids, f"snapshot_id {sid!r} in frames but not in bundle snapshots"


def test_frames_snapshot_team_ids_valid(seed7_bundle: dict[str, Any]) -> None:
    valid = set(seed7_bundle["meta"]["teams"])
    for tid in seed7_bundle["frames"]["snapshots"].values():
        assert tid in valid, f"frames.snapshots team_id {tid!r} not in {valid}"


def test_frames_all_overlays_covered(seed7_bundle: dict[str, Any]) -> None:
    """Every overlay in the bundle must have a frames.overlays entry."""
    ov_frame_ids = set(seed7_bundle["frames"]["overlays"])
    for ov in seed7_bundle["overlays"]:
        assert ov["overlay_id"] in ov_frame_ids, (
            f"overlay {ov['overlay_id']!r} missing from frames.overlays"
        )


def test_frames_overlay_team_ids_valid(seed7_bundle: dict[str, Any]) -> None:
    valid = set(seed7_bundle["meta"]["teams"])
    for tid in seed7_bundle["frames"]["overlays"].values():
        assert tid in valid, f"frames.overlays team_id {tid!r} not in {valid}"


def test_frames_deterministic(seed7_bundle: dict[str, Any]) -> None:
    """frames must be identical on a second build of the same seed."""
    from scripts.build_replay import _assemble_bundle, _build_match_replay

    data2 = _build_match_replay(7, "T01", "T02")
    bundle2, _ = asyncio.run(
        _assemble_bundle(data2, use_agents=False, client=None, timeout_s=5.0)
    )
    assert seed7_bundle["frames"] == bundle2["frames"]


def test_scenario_bundle_has_frames() -> None:
    from scripts.build_replay import _assemble_bundle, _build_scenario_replay

    data = _build_scenario_replay("missed_overlap_right")
    bundle, _ = asyncio.run(
        _assemble_bundle(data, use_agents=False, client=None, timeout_s=5.0)
    )
    assert "frames" in bundle
    assert isinstance(bundle["frames"]["snapshots"], dict)
    assert isinstance(bundle["frames"]["overlays"], dict)
