"""Tests for simulator.publisher (no network required).

Covers:
- --dry-run: produces valid JSON messages, correct count, no network calls
- sleep_duration: correct real-second delay for given speed settings
- _parse_cs: EntityPath extraction from connection string variants
"""

from __future__ import annotations

import json

import pytest

from simulator.publisher import (
    _event_time,
    _interleave,
    _parse_cs,
    run_publisher,
    sleep_duration,
)

# ---------------------------------------------------------------------------
# sleep_duration
# ---------------------------------------------------------------------------

def test_sleep_max_mode_returns_zero() -> None:
    assert sleep_duration(event_clock=100, prev_clock=50, speed=0.0) == 0.0


def test_sleep_at_speed_10() -> None:
    # 30 match-seconds at speed=10 => 3.0 real seconds
    result = sleep_duration(event_clock=80, prev_clock=50, speed=10.0)
    assert result == pytest.approx(3.0)


def test_sleep_no_negative_for_backward_clock() -> None:
    # Clock never goes backward, but guard anyway
    assert sleep_duration(event_clock=40, prev_clock=50, speed=5.0) == 0.0


def test_sleep_at_speed_1() -> None:
    # 1:1 real time
    assert sleep_duration(event_clock=2700, prev_clock=0, speed=1.0) == pytest.approx(2700.0)


# ---------------------------------------------------------------------------
# _parse_cs
# ---------------------------------------------------------------------------

def test_parse_cs_with_entity_path() -> None:
    cs = "Endpoint=sb://ns.servicebus.windows.net/;SharedAccessKeyName=k;SharedAccessKey=v;EntityPath=my-hub"
    assert _parse_cs(cs) == "my-hub"


def test_parse_cs_without_entity_path() -> None:
    cs = "Endpoint=sb://ns.servicebus.windows.net/;SharedAccessKeyName=k;SharedAccessKey=v"
    assert _parse_cs(cs) is None


def test_parse_cs_entity_path_case_insensitive() -> None:
    cs = "Endpoint=sb://ns.servicebus.windows.net/;entitypath=hub2"
    assert _parse_cs(cs) == "hub2"


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

def test_dry_run_prints_three_messages(capsys: pytest.CaptureFixture) -> None:
    run_publisher(
        seed=7, home_id="T01", away_id="T02", speed=0.0, dry_run=True, send_snapshots=False
    )
    out = capsys.readouterr().out

    assert "DRY RUN" in out

    # Extract the three JSON objects from the output
    lines = out.splitlines()
    json_lines: list[str] = []
    in_block = False
    block: list[str] = []
    for line in lines:
        if line.strip() == "{":
            in_block = True
            block = [line]
        elif in_block:
            block.append(line)
            if line.strip() == "}":
                json_lines.append("\n".join(block))
                in_block = False

    assert len(json_lines) == 3, f"expected 3 JSON objects, got {len(json_lines)}"

    for raw in json_lines:
        obj = json.loads(raw)
        assert "event_id" in obj
        assert "event_type" in obj
        assert "event_time" in obj
        # event_time must be a valid ISO datetime string
        from datetime import datetime
        datetime.fromisoformat(obj["event_time"].replace("Z", "+00:00"))


def test_dry_run_reports_total_count(capsys: pytest.CaptureFixture) -> None:
    run_publisher(
        seed=7, home_id="T01", away_id="T02", speed=0.0, dry_run=True, send_snapshots=False
    )
    out = capsys.readouterr().out
    assert "Total events that would be sent:" in out
    # Extract the count and confirm it's a plausible match length
    for line in out.splitlines():
        if "Total events" in line:
            count = int(line.split(":")[-1].strip())
            assert count > 100, f"suspiciously low event count: {count}"
            break


def test_event_time_max_speed_uses_clock_as_seconds() -> None:
    """For max speed (speed=0), effective speed=1, so offset = match_clock_s seconds."""
    from datetime import UTC, datetime, timedelta

    run_start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t = _event_time(run_start, match_clock_s=600, speed=0.0)
    assert t == run_start + timedelta(seconds=600)


def test_event_time_speed_10_scales_offset() -> None:
    """For speed=10, offset = match_clock_s / 10 real seconds."""
    from datetime import UTC, datetime, timedelta

    run_start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t = _event_time(run_start, match_clock_s=600, speed=10.0)
    assert t == run_start + timedelta(seconds=60)


def test_dry_run_event_time_offsets_grow_with_clock(capsys: pytest.CaptureFixture) -> None:
    """Events' timestamps grow with match_clock_s (first 3 events)."""
    from datetime import UTC, datetime

    t_before = datetime.now(UTC)
    run_publisher(
        seed=7, home_id="T01", away_id="T02", speed=0.0, dry_run=True, send_snapshots=False
    )
    out = capsys.readouterr().out

    lines = out.splitlines()
    blocks: list[str] = []
    block: list[str] = []
    in_block = False
    for line in lines:
        if line.strip() == "{":
            in_block = True
            block = [line]
        elif in_block:
            block.append(line)
            if line.strip() == "}":
                blocks.append("\n".join(block))
                in_block = False

    assert len(blocks) == 3
    import json

    parsed = [json.loads(b) for b in blocks]
    clocks = [p["match_clock_s"] for p in parsed]
    times = [datetime.fromisoformat(p["event_time"].replace("Z", "+00:00")) for p in parsed]

    # Offsets must be non-decreasing
    for i in range(1, len(times)):
        assert times[i] >= times[i - 1]

    # Clock delta and time delta must agree: dt = dc seconds (speed=max → effective=1)
    for i in range(1, len(times)):
        expected_delta = clocks[i] - clocks[i - 1]
        actual_delta = (times[i] - times[i - 1]).total_seconds()
        assert abs(actual_delta - expected_delta) < 0.5

    # run_start is set inside run_publisher after engine.run(), so it falls between
    # t_before and t_after; times[0] = run_start + clock[0] which may be nonzero.
    assert times[0] >= t_before


# ---------------------------------------------------------------------------
# _interleave: snapshot ordering and count
# ---------------------------------------------------------------------------


def _seed7_events_and_snaps():
    from simulator.engine import MatchEngine
    from simulator.reference_data import build_players, build_teams

    teams = {t.team_id: t for t in build_teams()}
    players = build_players(7)
    engine = MatchEngine(
        home_team=teams["T01"],
        away_team=teams["T02"],
        players=players,
        seed=7,
        match_id="match_s7_T01_T02",
        scenario_id="live",
    )
    events, snapshots = engine.run()
    return events, snapshots


def test_snapshot_ordering_seed7() -> None:
    """Every snapshot in the interleaved sequence precedes all events that reference it."""
    events, snapshots = _seed7_events_and_snaps()
    snap_by_id = {s.snapshot_id: s for s in snapshots}
    seq = _interleave(events, snap_by_id)

    snap_position: dict[str, int] = {}
    for i, (kind, obj) in enumerate(seq):
        if kind == "snapshot":
            assert isinstance(obj, type(snapshots[0]))
            snap_position[obj.snapshot_id] = i  # type: ignore[union-attr]

    for i, (kind, obj) in enumerate(seq):
        if kind == "event" and obj.snapshot_id:  # type: ignore[union-attr]
            sp = snap_position.get(obj.snapshot_id)  # type: ignore[union-attr]
            assert sp is not None, f"snapshot {obj.snapshot_id!r} missing from sequence"  # type: ignore[union-attr]
            assert sp < i, (
                f"snapshot {obj.snapshot_id!r} at position {sp} "  # type: ignore[union-attr]
                f"is after event at position {i}"
            )


def test_snapshot_count_seed7() -> None:
    """Seed-7 engine produces 611 snapshots; all appear in the interleaved sequence."""
    events, snapshots = _seed7_events_and_snaps()
    assert len(snapshots) == 611
    snap_by_id = {s.snapshot_id: s for s in snapshots}
    seq = _interleave(events, snap_by_id)
    n_snaps = sum(1 for kind, _ in seq if kind == "snapshot")
    assert n_snaps == 611


def test_no_snapshots_flag_dry_run(capsys: pytest.CaptureFixture) -> None:
    """--no-snapshots (send_snapshots=False) omits the snapshot section from dry-run output."""
    run_publisher(
        seed=7, home_id="T01", away_id="T02", speed=0.0,
        dry_run=True, send_snapshots=False,
    )
    out = capsys.readouterr().out
    assert "--- Snapshot" not in out
    assert "Total snapshots" not in out


def test_dry_run_shows_first_snapshot(capsys: pytest.CaptureFixture) -> None:
    """Dry-run with send_snapshots=True prints the first snapshot header and count."""
    run_publisher(
        seed=7, home_id="T01", away_id="T02", speed=0.0,
        dry_run=True, send_snapshots=True,
    )
    out = capsys.readouterr().out
    assert "--- Snapshot" in out
    assert "Total snapshots that would be sent: 611" in out


def test_dry_run_does_not_import_eventhub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry run must never touch azure.eventhub (no network, no credentials)."""
    import sys
    original = sys.modules.get("azure.eventhub")
    # Block the import so it would raise if attempted
    monkeypatch.setitem(sys.modules, "azure.eventhub", None)  # type: ignore[arg-type]
    try:
        run_publisher(seed=7, home_id="T01", away_id="T02", speed=0.0, dry_run=True)
    finally:
        if original is not None:
            monkeypatch.setitem(sys.modules, "azure.eventhub", original)
        else:
            monkeypatch.delitem(sys.modules, "azure.eventhub", raising=False)
