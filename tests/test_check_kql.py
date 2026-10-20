"""Unit tests for scripts.check_kql comparison helpers (no network required)."""

from __future__ import annotations

from core.schemas import PlayerPosition, PositionSnapshot, Role
from scripts.check_kql import _check_snapshots


def _make_positions() -> list[PlayerPosition]:
    return [
        PlayerPosition(
            player_id=f"P{i:02d}",
            team_id="T01" if i < 11 else "T02",
            role=Role.GK if i in (0, 11) else Role.CB,
            x=float(i * 4),
            y=34.0,
        )
        for i in range(22)
    ]


def _pos_to_dicts(positions: list[PlayerPosition]) -> list[dict]:
    return [
        {"player_id": p.player_id, "team_id": p.team_id, "x": p.x, "y": p.y}
        for p in positions
    ]


def test_check_snapshots_uses_first_row_not_last() -> None:
    """Sample comparison must use kql_rows[0] (first row), not the leftover loop variable.

    If the loop variable `row` (last row) were used instead, the test would report a
    positions mismatch even though the first row matches Python exactly.
    """
    positions = _make_positions()
    py_snap = PositionSnapshot(
        snapshot_id="sn_first", match_id="m1", match_clock_s=60, positions=positions
    )

    first_row = {"snapshot_id": "sn_first", "positions": _pos_to_dicts(positions)}
    # Last row has positions that differ from Python; it must NOT be used for comparison.
    # Build dicts directly (bypasses PlayerPosition field validation) so x can be out-of-range.
    last_row = {
        "snapshot_id": "sn_last",
        "positions": [
            {"player_id": p.player_id, "team_id": p.team_id, "x": -1.0, "y": -1.0}
            for p in positions
        ],
    }

    failures = _check_snapshots([first_row, last_row], [py_snap])

    # Count mismatch (2 KQL rows vs 1 Python) is expected; positions mismatch is not.
    position_failures = [f for f in failures if "positions mismatch" in f]
    assert not position_failures, (
        f"positions mismatch was reported even though first row matches Python: "
        f"{position_failures}"
    )
