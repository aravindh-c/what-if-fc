"""Hand-designed demo scenarios for Ghost Pass demos.

Each Scenario pairs a PositionSnapshot and a MatchEvent (a pass) with the
expected ghost-receiver ID and a one-sentence explanation.

Coordinates are in the T01 attacking frame (x towards goal at x=105).
All four scenarios use T01 (4-3-3 possession) vs T02 (4-2-3-1 high-press).

Usage:
    python -m simulator.scenarios --out data/scenarios
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from core.schemas import EventType, MatchEvent, Outcome, PlayerPosition, PositionSnapshot

# Fixed reference time for hand-designed events (not a real wall-clock timestamp)
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Scenario model
# ---------------------------------------------------------------------------


class Scenario(BaseModel):
    """A hand-designed scenario for Ghost Pass demos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    title: str
    description: str
    period: Literal[1, 2]
    match_clock_s: int
    home: str = "T01"
    away: str = "T02"
    in_possession: str
    snapshot: PositionSnapshot
    actual_pass: MatchEvent
    expected_ghost_receiver_id: str
    why: str


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _build_scenarios() -> list[Scenario]:
    from core.formations import base_shape, starting_xi
    from simulator.reference_data import build_players, build_teams

    teams = {t.team_id: t for t in build_teams()}
    players = build_players(7)

    t01, t02 = teams["T01"], teams["T02"]
    xi1 = starting_xi([p for p in players if p.team_id == "T01"], t01.formation)
    xi2 = starting_xi([p for p in players if p.team_id == "T02"], t02.formation)

    slots1 = base_shape(t01.formation, mirrored=False)
    slots2 = base_shape(t02.formation, mirrored=True)

    # {player_id: (role, base_x, base_y)}
    base1 = {xi1[i].player_id: (r, x, y) for i, (r, x, y) in enumerate(slots1)}
    base2 = {xi2[i].player_id: (r, x, y) for i, (r, x, y) in enumerate(slots2)}

    def snapshot(
        sid: str,
        clock: int,
        ov1: dict[str, tuple[float, float]],
        ov2: dict[str, tuple[float, float]],
    ) -> PositionSnapshot:
        pos = []
        for p in xi1:
            r, bx, by = base1[p.player_id]
            x, y = ov1.get(p.player_id, (bx, by))
            pos.append(PlayerPosition(player_id=p.player_id, team_id="T01", role=r, x=x, y=y))
        for p in xi2:
            r, bx, by = base2[p.player_id]
            x, y = ov2.get(p.player_id, (bx, by))
            pos.append(PlayerPosition(player_id=p.player_id, team_id="T02", role=r, x=x, y=y))
        return PositionSnapshot(
            snapshot_id=sid, match_id="demo", match_clock_s=clock, positions=pos
        )

    def pass_event(
        eid: str,
        scen_id: str,
        clock: int,
        period: Literal[1, 2],
        player_id: str,
        x: float, y: float,
        end_x: float, end_y: float,
        outcome: Outcome,
        receiver_id: str,
        pressure: float,
        snapshot_id: str,
    ) -> MatchEvent:
        return MatchEvent(
            event_id=eid,
            match_id="demo",
            scenario_id=scen_id,
            seed=0,
            event_time=_EPOCH,
            match_clock_s=clock,
            period=period,
            event_type=EventType.PASS,
            team_id="T01",
            player_id=player_id,
            possession_id=0,
            x=x, y=y,
            end_x=end_x, end_y=end_y,
            outcome=outcome,
            receiver_id=receiver_id,
            pressure_level=pressure,
            snapshot_id=snapshot_id,
        )

    # ------------------------------------------------------------------
    # (a) missed_overlap_right  period=2  ~62'  clock=3720
    #
    # T01-P12 CM on ball at (62,30) passes back to T01-P10 DM at (48,32).
    # T01-P08 FB is overlapping free at (82,60); nearest T02 ≥ 18 m away.
    # T02 CBs pushed to x=83 so T01-P08 at x=82 is onside.
    # ------------------------------------------------------------------
    sn_a = snapshot(
        "sn_a", 3720,
        ov1={
            "T01-P08": (82.0, 60.0),   # left FB overlapping (ghost)
            "T01-P10": (48.0, 32.0),   # DM (actual receiver, pass backwards)
            "T01-P12": (62.0, 30.0),   # CM (passer)
        },
        ov2={
            "T02-P03": (83.0, 42.0),   # CB behind the FB → T01-P08 onside
            "T02-P04": (83.0, 26.0),   # CB
            "T02-P07": (73.0, 56.0),   # FB on the flank, off the overlap lane
            "T02-P11": (57.0, 22.0),   # DM dropped back, off the overlap lane
        },
    )
    pass_a = pass_event(
        "ev_a_001", "missed_overlap_right",
        clock=3720, period=2,
        player_id="T01-P12",
        x=62.0, y=30.0, end_x=48.0, end_y=32.0,
        outcome=Outcome.COMPLETE,
        receiver_id="T01-P10",
        pressure=0.20,
        snapshot_id="sn_a",
    )

    # ------------------------------------------------------------------
    # (b) forced_pass_into_traffic  period=1  ~38'  clock=2280
    #
    # T01-P12 CM at (75,34) plays to T01-P17 ST at (88,36) where
    # T02-P03, T02-P04, T02-P08 are all within 4 m.
    # T01-P15 W is free at (86,12) with no T02 within 24 m.
    # ------------------------------------------------------------------
    sn_b = snapshot(
        "sn_b", 2280,
        ov1={
            "T01-P12": (75.0, 34.0),   # CM (passer)
            "T01-P15": (86.0, 12.0),   # W right (ghost, far side)
            "T01-P17": (88.0, 36.0),   # ST (actual receiver)
        },
        ov2={
            "T02-P03": (91.0, 36.0),   # CB 3 m from ST
            "T02-P04": (88.0, 32.0),   # CB 4 m from ST
            "T02-P08": (86.0, 38.0),   # FB 2.8 m from ST
        },
    )
    pass_b = pass_event(
        "ev_b_001", "forced_pass_into_traffic",
        clock=2280, period=1,
        player_id="T01-P12",
        x=75.0, y=34.0, end_x=88.0, end_y=36.0,
        outcome=Outcome.COMPLETE,
        receiver_id="T01-P17",
        pressure=0.15,
        snapshot_id="sn_b",
    )

    # ------------------------------------------------------------------
    # (c) late_counter  period=2  ~85'  clock=5100
    #
    # T01-P13 CM at (52,40) passes sideways to T01-P04 CB at (48,26).
    # T01-P17 ST at (78,28) is free and onside: x=78 < second-last T02 at x=82.
    # ------------------------------------------------------------------
    sn_c = snapshot(
        "sn_c", 5100,
        ov1={
            "T01-P04": (48.0, 26.0),   # CB (actual receiver, pushed up)
            "T01-P13": (52.0, 40.0),   # CM (passer)
            "T01-P17": (78.0, 28.0),   # ST (ghost, onside)
        },
        ov2={
            "T02-P03": (82.0, 44.0),   # CB at x=82 (second-last defender)
            "T02-P04": (84.0, 18.0),   # CB at x=84 (last outfield)
        },
    )
    pass_c = pass_event(
        "ev_c_001", "late_counter",
        clock=5100, period=2,
        player_id="T01-P13",
        x=52.0, y=40.0, end_x=48.0, end_y=26.0,
        outcome=Outcome.COMPLETE,
        receiver_id="T01-P04",
        pressure=0.10,
        snapshot_id="sn_c",
    )

    # ------------------------------------------------------------------
    # (d) high_press_escape  period=1  ~14'  clock=840
    #
    # T02 presses high. T01-P03 CB at (20,30) passes to T01-P07 FB at (16,8).
    # T02-P14 AM at (15,9) is 1.4 m from the FB → intercept (INCOMPLETE).
    # Pass end at (16.2, 9.1) is on the line to the receiver at t=0.95.
    # T01-P10 DM is open at (34,36); nearest T02 is T02-P10 at (50,41) ≈ 16.8 m.
    # ------------------------------------------------------------------
    sn_d = snapshot(
        "sn_d", 840,
        ov1={
            "T01-P03": (20.0, 30.0),   # CB (passer)
            "T01-P07": (16.0, 8.0),    # FB (actual receiver, intercept)
            "T01-P10": (34.0, 36.0),   # DM (ghost, open)
        },
        ov2={
            "T02-P10": (50.0, 41.0),   # DM pushed forward (high press)
            "T02-P11": (50.0, 27.0),   # DM pushed forward
            "T02-P14": (15.0, 9.0),    # AM intercepting FB pass
            "T02-P15": (24.0, 54.0),   # W wide press
            "T02-P16": (25.0, 14.0),   # W right press
            "T02-P17": (22.0, 25.0),   # ST pressing CB, off the escape lane
        },
    )
    pass_d = pass_event(
        "ev_d_001", "high_press_escape",
        clock=840, period=1,
        player_id="T01-P03",
        x=20.0, y=30.0, end_x=16.2, end_y=9.1,
        outcome=Outcome.INCOMPLETE,
        receiver_id="T01-P07",
        pressure=0.72,
        snapshot_id="sn_d",
    )

    return [
        Scenario(
            scenario_id="missed_overlap_right",
            title="Missed Overlap on the Right",
            description=(
                "T01's CM plays the ball back to the DM instead of finding the"
                " overlapping full-back who has run into space on the flank."
            ),
            period=2, match_clock_s=3720,
            in_possession="T01",
            snapshot=sn_a,
            actual_pass=pass_a,
            expected_ghost_receiver_id="T01-P08",
            why=(
                "T01-P08 is 10 m clear of the nearest defender in advanced space"
                " with the overlap already made, while the DM receives possession"
                " backwards with no defensive pressure."
            ),
        ),
        Scenario(
            scenario_id="forced_pass_into_traffic",
            title="Forced Pass into Traffic",
            description=(
                "T01's CM plays directly to the striker who is surrounded by three"
                " defenders, while the far-side winger is completely unmarked."
            ),
            period=1, match_clock_s=2280,
            in_possession="T01",
            snapshot=sn_b,
            actual_pass=pass_b,
            expected_ghost_receiver_id="T01-P15",
            why=(
                "T01-P15 is over 24 m from the nearest defender with an open lane"
                " from the CM, whereas T01-P17 receives into a three-defender trap"
                " with no room to turn."
            ),
        ),
        Scenario(
            scenario_id="late_counter",
            title="Late Counter-Attack Missed",
            description=(
                "T01's CM chooses a sideways pass to the centre-back instead of"
                " threading the ball to the onside striker free in the final third."
            ),
            period=2, match_clock_s=5100,
            in_possession="T01",
            snapshot=sn_c,
            actual_pass=pass_c,
            expected_ghost_receiver_id="T01-P17",
            why=(
                "T01-P17 is onside and over 11 m behind the nearest defender with a"
                " clear lane to goal, while the pass to the CB surrenders all"
                " forward momentum."
            ),
        ),
        Scenario(
            scenario_id="high_press_escape",
            title="High Press Escape Route Missed",
            description=(
                "T01's centre-back plays into the T02 high press instead of finding"
                " the DM who has dropped into space between the press lines."
            ),
            period=1, match_clock_s=840,
            in_possession="T01",
            snapshot=sn_d,
            actual_pass=pass_d,
            expected_ghost_receiver_id="T01-P10",
            why=(
                "T01-P10 is open at (34,36) with the nearest T02 player 16 m away,"
                " while the pass to T01-P07 runs directly into T02-P14 who is"
                " 1.4 m from the target."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description="Write hand-designed demo scenarios to JSON.")
    p.add_argument("--out", type=Path, default=Path("data/scenarios"))
    args = p.parse_args()
    scenarios = _build_scenarios()
    args.out.mkdir(parents=True, exist_ok=True)
    for s in scenarios:
        path = args.out / f"{s.scenario_id}.json"
        path.write_text(s.model_dump_json(indent=2) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
