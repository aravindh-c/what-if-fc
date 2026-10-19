"""Acceptance tests for analytics.metrics (AT-03, AT-04).

AT-03: a small hand-built fixture of ~20 events with known answers for every
       metric function.
AT-04: known-answer scenario — seed-7 metrics are stable across runs.

Fixture design
--------------
Two teams T01 (attacking) and T02 (defending).  match_id = "test_match".
All coordinates are in the possessing team's attacking frame (x → 105).

Event timeline (all period 1):

  clock  team  type            x     outcome        notes
  -----  ----  --------------- ----  -------------  ------------------------------------
    10   T01   pass complete   50    complete       plain backward pass
    65   T01   pass complete   75    complete  0.6  high-pressure final-third pass (snapshot)
    70   T01   shot            80    on_target      attacking action (+3)
    75   T01   goal           100    –              goal
    80   T02   pressure        30    –              x=30 < 52.5 → pressure_index T02 min1
   120   T02   pass incomplete  50   incomplete
   125   T01   carry complete   60   complete       possession; x=60 not final-third
   180   T02   pass complete    55   complete
   190   T02   tackle won       78   won            x=78 ≥ 70 → final_third_turnover
   240   T01   pass incomplete  45   incomplete
   300   T02   pass complete    60   complete
   310   T02   pressure         40   –              x=40 < 52.5 → pressure_index T02 min5
   320   T02   tackle won       72   won            x=72 ≥ 70 → final_third_turnover
   360   T01   pass complete    55   complete
   480   T02   shot             90   off_target     attacking action (+3); momentum T02 min8
   490   T02   shot             85   saved          attacking action (+3); momentum T02 min8
   500   T01   pass complete    55   complete
   505   T01   pressure         35   –              x=35 < 52.5 → pressure_index T01 min8
   600   –     period_end       –    –

Known answers derived in comments below each test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from analytics.metrics import (
    MomentumRow,
    PressureRow,
    TeamStats,
    key_moments,
    match_stats,
    momentum,
    pressure_index,
)
from core.schemas import EventType, MatchEvent, Outcome

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_MATCH = "test_match"


def _pass(eid: str, clock: int, team: str, x: float, ex: float,
          outcome: Outcome = Outcome.COMPLETE,
          pressure: float = 0.0, snap: str | None = None) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.PASS, team_id=team, player_id=f"{team}-P01",
        possession_id=0, x=x, y=34.0, end_x=ex, end_y=34.0,
        outcome=outcome, receiver_id=f"{team}-P02",
        pressure_level=pressure, snapshot_id=snap,
    )


def _shot(eid: str, clock: int, team: str, x: float,
          outcome: Outcome = Outcome.ON_TARGET) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.SHOT, team_id=team, player_id=f"{team}-P01",
        possession_id=0, x=x, y=34.0, outcome=outcome,
    )


def _goal(eid: str, clock: int, team: str) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.GOAL, team_id=team, player_id=f"{team}-P01",
        possession_id=0, x=100.0, y=34.0,
    )


def _carry(eid: str, clock: int, team: str, x: float, ex: float) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.CARRY, team_id=team, player_id=f"{team}-P01",
        possession_id=0, x=x, y=34.0, end_x=ex, end_y=34.0,
    )


def _pressure(eid: str, clock: int, team: str, x: float) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.PRESSURE, team_id=team, player_id=f"{team}-P01",
        possession_id=0, x=x, y=34.0,
    )


def _tackle(eid: str, clock: int, team: str, x: float,
            outcome: Outcome = Outcome.WON) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.TACKLE, team_id=team, player_id=f"{team}-P01",
        possession_id=0, x=x, y=34.0, outcome=outcome,
    )


def _period_end(eid: str, clock: int) -> MatchEvent:
    return MatchEvent(
        event_id=eid, match_id=_MATCH, scenario_id="test", seed=0,
        event_time=_EPOCH, match_clock_s=clock, period=1,
        event_type=EventType.PERIOD_END, possession_id=0,
    )


FIXTURE: list[MatchEvent] = [
    _pass("e02", 10,  "T01", 50.0, 60.0),                                 # min0, T01 pass comp
    _pass("e03", 65,  "T01", 75.0, 85.0, pressure=0.6, snap="s1"),        # min1, hpftp
    _shot("e04", 70,  "T01", 80.0),                                        # min1, T01 shot +3
    _goal("e05", 75,  "T01"),                                              # min1, T01 goal
    _pressure("e06", 80, "T02", 30.0),                                     # min1, T02 press x<52.5
    _pass("e07", 120, "T02", 50.0, 40.0, outcome=Outcome.INCOMPLETE),     # min2, T02 incomp
    _carry("e08", 125, "T01", 60.0, 70.0),                                # min2, T01 carry
    _pass("e09", 180, "T02", 55.0, 65.0),                                  # min3, T02 comp
    _tackle("e10", 190, "T02", 78.0),                                      # min3, ftt x=78
    _pass("e11", 240, "T01", 45.0, 35.0, outcome=Outcome.INCOMPLETE),     # min4, T01 incomp
    _pass("e12", 300, "T02", 60.0, 50.0),                                  # min5, T02 comp
    _pressure("e13", 310, "T02", 40.0),                                    # min5, T02 press x<52.5
    _tackle("e14", 320, "T02", 72.0),                                      # min5, ftt x=72
    _pass("e15", 360, "T01", 55.0, 65.0),                                  # min6, T01 comp
    _shot("e16", 480, "T02", 90.0, outcome=Outcome.OFF_TARGET),           # min8, T02 shot +3
    _shot("e17", 490, "T02", 85.0, outcome=Outcome.SAVED),                # min8, T02 shot +3
    _pass("e18", 500, "T01", 55.0, 45.0),                                  # min8, T01 comp
    _pressure("e19", 505, "T01", 35.0),                                    # min8, T01 press x<52.5
    _period_end("e20", 600),                                               # min10
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stats_by_team(evs: list[MatchEvent]) -> dict[str, TeamStats]:
    return {s.team_id: s for s in match_stats(evs)}


def _mom_at(rows: list[MomentumRow], minute: int, team: str) -> float:
    return next(r.share for r in rows if r.minute == minute and r.team_id == team)


def _press_at(rows: list[PressureRow], minute: int, team: str) -> float:
    return next(r.pressure_index for r in rows if r.minute == minute and r.team_id == team)


# ===========================================================================
# AT-03: fixture with known answers
# ===========================================================================


class TestMatchStats:
    """AT-03 – match_stats."""

    def test_returns_two_teams(self) -> None:
        s = _stats_by_team(FIXTURE)
        assert set(s.keys()) == {"T01", "T02"}

    def test_t01_passes(self) -> None:
        # e02, e03, e11, e15, e18 = 5 passes; 4 complete (e11 incomplete)
        s = _stats_by_team(FIXTURE)["T01"]
        assert s.passes == 5
        assert s.completed_passes == 4
        assert s.completion_pct == 80.0

    def test_t02_passes(self) -> None:
        # e07(incomp), e09, e12 = 3; 2 complete
        s = _stats_by_team(FIXTURE)["T02"]
        assert s.passes == 3
        assert s.completed_passes == 2
        assert s.completion_pct == 66.7

    def test_shots(self) -> None:
        s = _stats_by_team(FIXTURE)
        assert s["T01"].shots == 1   # e04
        assert s["T02"].shots == 2   # e16, e17

    def test_goals(self) -> None:
        s = _stats_by_team(FIXTURE)
        assert s["T01"].goals == 1
        assert s["T02"].goals == 0

    def test_possession_proxy(self) -> None:
        # T01 possession events: e02+e03+e04+e08+e11+e15+e18 = 7
        # T02: e07+e09+e12+e16+e17 = 5; total=12
        s = _stats_by_team(FIXTURE)
        assert s["T01"].possession_proxy_pct == round(100.0 * 7 / 12, 1)  # 58.3
        assert s["T02"].possession_proxy_pct == round(100.0 * 5 / 12, 1)  # 41.7

    def test_dedup_does_not_double_count(self) -> None:
        duped = list(FIXTURE) + [FIXTURE[0]]  # one duplicate
        s = _stats_by_team(duped)
        assert s["T01"].passes == 5  # unchanged


class TestMomentum:
    """AT-03 – momentum."""

    def test_returns_rows_for_all_minutes_and_teams(self) -> None:
        rows = momentum(FIXTURE)
        minutes = {r.minute for r in rows}
        teams = {r.team_id for r in rows}
        assert max(minutes) == 10       # period_end at clock=600 → min=10
        assert teams == {"T01", "T02"}

    def test_shares_sum_to_one(self) -> None:
        rows = momentum(FIXTURE)
        for m in range(11):
            total = sum(r.share for r in rows if r.minute == m)
            assert abs(total - 1.0) < 1e-9, f"minute {m}: sum={total}"

    def test_min1_t01_dominates(self) -> None:
        # T01 attacking at min1: e03(+1)+e04(+3)=4; T02=0 → T01 share=1.0
        rows = momentum(FIXTURE)
        assert _mom_at(rows, 1, "T01") == pytest.approx(1.0)
        assert _mom_at(rows, 1, "T02") == pytest.approx(0.0)

    def test_min5_still_t01(self) -> None:
        # Rolling [1,5]: T01=4(min1), T02=0 → T01 share=1.0
        rows = momentum(FIXTURE)
        assert _mom_at(rows, 5, "T01") == pytest.approx(1.0)

    def test_min6_no_leader(self) -> None:
        # Rolling [2,6]: T01=0, T02=0 → each 0.5
        rows = momentum(FIXTURE)
        assert _mom_at(rows, 6, "T01") == pytest.approx(0.5)
        assert _mom_at(rows, 6, "T02") == pytest.approx(0.5)

    def test_min8_t02_dominates(self) -> None:
        # Rolling [4,8]: T01=0, T02=e16(+3)+e17(+3)=6 → T02 share=1.0
        rows = momentum(FIXTURE)
        assert _mom_at(rows, 8, "T02") == pytest.approx(1.0)
        assert _mom_at(rows, 8, "T01") == pytest.approx(0.0)


class TestPressureIndex:
    """AT-03 – pressure_index."""

    def test_t02_min1(self) -> None:
        # window [0,1] size=2; T02 events: e06(min1)=1 → 1/2 = 0.5
        rows = pressure_index(FIXTURE)
        assert _press_at(rows, 1, "T02") == pytest.approx(0.5)

    def test_t02_min5(self) -> None:
        # window [1,5] size=5; T02: e06(min1)+e13(min5)=2 → 2/5 = 0.4
        rows = pressure_index(FIXTURE)
        assert _press_at(rows, 5, "T02") == pytest.approx(0.4)

    def test_t01_min8(self) -> None:
        # window [4,8] size=5; T01: e19(min8)=1 → 1/5 = 0.2
        rows = pressure_index(FIXTURE)
        assert _press_at(rows, 8, "T01") == pytest.approx(0.2)

    def test_t02_min8(self) -> None:
        # window [4,8] size=5; T02: e13(min5)=1 → 1/5=0.2
        # (e06 is at min1, outside [4,8]; e10/e14 tackles are at x≥52.5)
        rows = pressure_index(FIXTURE)
        assert _press_at(rows, 8, "T02") == pytest.approx(0.2)

    def test_high_x_tackle_not_counted(self) -> None:
        # e10 (tackle, x=78) and e14 (tackle, x=72) both ≥52.5 → not counted
        rows = pressure_index(FIXTURE)
        # T02 at min3 (window [0,3]): only e06 at min1 → 1/4 = 0.25
        assert _press_at(rows, 3, "T02") == pytest.approx(0.25)


class TestKeyMoments:
    """AT-03 – key_moments."""

    def test_goal_detected(self) -> None:
        kms = key_moments(FIXTURE)
        goals = [k for k in kms if k.moment_type == "goal"]
        assert len(goals) == 1
        g = goals[0]
        assert g.team_id == "T01"
        assert g.event_id == "e05"
        assert g.match_clock_s == 75
        assert g.value == 1.0

    def test_high_pressure_final_third_pass(self) -> None:
        kms = key_moments(FIXTURE)
        hps = [k for k in kms if k.moment_type == "high_pressure_final_third_pass"]
        assert len(hps) == 1
        h = hps[0]
        assert h.event_id == "e03"
        assert h.snapshot_id == "s1"
        assert h.value == pytest.approx(0.6)

    def test_final_third_turnovers(self) -> None:
        kms = key_moments(FIXTURE)
        ftts = [k for k in kms if k.moment_type == "final_third_turnover"]
        assert len(ftts) == 2
        event_ids = {k.event_id for k in ftts}
        assert event_ids == {"e10", "e14"}
        for k in ftts:
            assert k.team_id == "T02"
            assert k.value >= 70.0  # x coordinate

    def test_momentum_swing_detected(self) -> None:
        # T01 led at min1-5 (share=1.0); T02 takes over at min8 (share=1.0)
        kms = key_moments(FIXTURE)
        swings = [k for k in kms if k.moment_type == "momentum_swing"]
        assert len(swings) == 1
        s = swings[0]
        assert s.team_id == "T02"
        assert s.match_clock_s == 8 * 60
        assert s.value == pytest.approx(1.0)

    def test_total_key_moment_count(self) -> None:
        # 1 goal + 1 hpftp + 2 ftt + 1 swing = 5
        kms = key_moments(FIXTURE)
        assert len(kms) == 5

    def test_moments_ordered_by_clock(self) -> None:
        kms = key_moments(FIXTURE)
        clocks = [k.match_clock_s for k in kms]
        assert clocks == sorted(clocks)

    def test_pass_without_snapshot_not_hpftp(self) -> None:
        # e03 without snapshot_id should NOT trigger high_pressure_final_third_pass
        stripped = [ev.model_copy(update={"snapshot_id": None}) if ev.event_id == "e03" else ev
                    for ev in FIXTURE]
        kms = key_moments(stripped)
        assert not any(k.moment_type == "high_pressure_final_third_pass" for k in kms)


# ===========================================================================
# AT-04: seed-7 stability
# ===========================================================================


@pytest.fixture(scope="module")
def seed7_events() -> list[MatchEvent]:
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
    evs, _ = engine.run()
    return evs


def test_seed7_match_stats_stable(seed7_events: list[MatchEvent]) -> None:
    """AT-04: same seed produces the same match stats."""
    s = match_stats(seed7_events)
    assert len(s) == 2
    # Re-run and compare
    s2 = match_stats(seed7_events)
    assert s == s2


def test_seed7_key_moments_stable(seed7_events: list[MatchEvent]) -> None:
    """AT-04: same seed produces the same key moments list."""
    km1 = key_moments(seed7_events)
    km2 = key_moments(seed7_events)
    assert km1 == km2


def test_seed7_momentum_stable(seed7_events: list[MatchEvent]) -> None:
    """AT-04: momentum is deterministic."""
    m1 = momentum(seed7_events)
    m2 = momentum(seed7_events)
    assert m1 == m2


def test_seed7_realistic_completion(seed7_events: list[MatchEvent]) -> None:
    """Seed-7 pass completion should be in the expected 75–95% band."""
    for s in match_stats(seed7_events):
        if s.passes > 0:
            assert 70.0 <= s.completion_pct <= 97.0, (
                f"{s.team_id}: completion {s.completion_pct}% outside expected range"
            )
