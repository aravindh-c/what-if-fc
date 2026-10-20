"""Tests for agents.kql_tools – LocalKql (no Fabric connection required)."""

from __future__ import annotations

import pytest

from agents.kql_tools import (
    LocalKql,
    _validate_match_id,
    _validate_minute,
    _validate_n,
)

# ---------------------------------------------------------------------------
# Helpers: build a small match from the engine
# ---------------------------------------------------------------------------


def _build_events(seed: int = 7):
    from simulator.engine import MatchEngine
    from simulator.reference_data import build_players, build_teams

    teams = {t.team_id: t for t in build_teams()}
    players = build_players(seed)
    engine = MatchEngine(
        home_team=teams["T01"],
        away_team=teams["T02"],
        players=players,
        seed=seed,
        match_id=f"match_s{seed}_T01_T02",
        scenario_id="test",
    )
    events, _ = engine.run()
    return events, f"match_s{seed}_T01_T02"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def test_validate_match_id_rejects_bad_patterns() -> None:
    bad = ["m_001", "matchS7", "match-T01", "match s7", "", "MATCH_s7"]
    for mid in bad:
        with pytest.raises(ValueError, match="match_id"):
            _validate_match_id(mid)


def test_validate_match_id_accepts_valid() -> None:
    _validate_match_id("match_s7_T01_T02")
    _validate_match_id("match_abc123")


def test_validate_minute_rejects_out_of_range() -> None:
    for bad in [-1, 121, "45", 45.0]:
        with pytest.raises(ValueError):
            _validate_minute(bad)  # type: ignore[arg-type]


def test_validate_minute_accepts_bounds() -> None:
    _validate_minute(0)
    _validate_minute(120)


def test_validate_n_rejects_out_of_range() -> None:
    for bad in [0, 11, -1, "5", 5.0]:
        with pytest.raises(ValueError):
            _validate_n(bad)  # type: ignore[arg-type]


def test_validate_n_accepts_bounds() -> None:
    _validate_n(1)
    _validate_n(10)


# ---------------------------------------------------------------------------
# LocalKql – match_stats
# ---------------------------------------------------------------------------


def test_local_kql_match_stats_keys() -> None:
    events, mid = _build_events()
    kql = LocalKql(events)
    result = kql.match_stats(mid)
    assert "T01" in result and "T02" in result
    for row in result.values():
        assert set(row) == {
            "passes", "completed_passes", "completion_pct",
            "shots", "goals", "possession_proxy_pct",
        }


def test_local_kql_match_stats_rounded() -> None:
    events, mid = _build_events()
    result = LocalKql(events).match_stats(mid)
    for row in result.values():
        for k in ("completion_pct", "possession_proxy_pct"):
            v = row[k]
            assert round(v, 3) == v


def test_local_kql_match_stats_completions_lte_passes() -> None:
    events, mid = _build_events()
    result = LocalKql(events).match_stats(mid)
    for row in result.values():
        assert row["completed_passes"] <= row["passes"]


def test_local_kql_match_stats_invalid_id_raises() -> None:
    events, _ = _build_events()
    with pytest.raises(ValueError):
        LocalKql(events).match_stats("bad_id")


# ---------------------------------------------------------------------------
# LocalKql – momentum_at
# ---------------------------------------------------------------------------


def test_local_kql_momentum_at_returns_dict() -> None:
    events, mid = _build_events()
    result = LocalKql(events).momentum_at(mid, 10)
    assert isinstance(result, dict)
    assert all(isinstance(v, float) for v in result.values())


def test_local_kql_momentum_at_shares_sum_to_one() -> None:
    events, mid = _build_events()
    result = LocalKql(events).momentum_at(mid, 10)
    if result:
        total = sum(result.values())
        assert abs(total - 1.0) < 1e-6


def test_local_kql_momentum_at_invalid_minute_raises() -> None:
    events, mid = _build_events()
    with pytest.raises(ValueError):
        LocalKql(events).momentum_at(mid, -1)


# ---------------------------------------------------------------------------
# LocalKql – pressure_at
# ---------------------------------------------------------------------------


def test_local_kql_pressure_at_returns_dict() -> None:
    events, mid = _build_events()
    result = LocalKql(events).pressure_at(mid, 10)
    assert isinstance(result, dict)
    assert all(isinstance(v, float) for v in result.values())


def test_local_kql_pressure_at_values_non_negative() -> None:
    events, mid = _build_events()
    result = LocalKql(events).pressure_at(mid, 10)
    for v in result.values():
        assert v >= 0.0


# ---------------------------------------------------------------------------
# LocalKql – recent_events
# ---------------------------------------------------------------------------


def test_local_kql_recent_events_returns_list() -> None:
    events, mid = _build_events()
    result = LocalKql(events).recent_events(mid, 45, 5)
    assert isinstance(result, list)
    assert len(result) <= 5


def test_local_kql_recent_events_respects_minute_cap() -> None:
    events, mid = _build_events()
    result = LocalKql(events).recent_events(mid, 10, 10)
    for row in result:
        assert row["match_clock_s"] // 60 <= 10


def test_local_kql_recent_events_sorted_descending() -> None:
    events, mid = _build_events()
    result = LocalKql(events).recent_events(mid, 90, 10)
    clocks = [r["match_clock_s"] for r in result]
    assert clocks == sorted(clocks, reverse=True)


def test_local_kql_recent_events_max_n() -> None:
    events, mid = _build_events()
    with pytest.raises(ValueError):
        LocalKql(events).recent_events(mid, 90, 11)


def test_local_kql_recent_events_row_keys() -> None:
    events, mid = _build_events()
    result = LocalKql(events).recent_events(mid, 90, 3)
    for row in result:
        assert "event_id" in row
        assert "match_clock_s" in row
        assert "event_type" in row


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_local_kql_is_kql_backend() -> None:
    from agents.kql_tools import KqlBackend

    events, _ = _build_events()
    assert isinstance(LocalKql(events), KqlBackend)
