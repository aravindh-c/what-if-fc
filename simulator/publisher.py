"""Day 3B: stream one match's events to a Fabric Eventstream custom endpoint.

Usage:
    python -m simulator.publisher --seed 7 --home T01 --away T02 --speed max
    python -m simulator.publisher --seed 7 --home T01 --away T02 --dry-run

Environment variables (loaded from .env):
    EVENTSTREAM_CONNECTION_STRING  – Event Hub-compatible connection string;
                                     may include EntityPath
    EVENTSTREAM_NAME               – optional override for the Event Hub name
                                     (ignored when EntityPath is already in the
                                     connection string)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Connection-string helpers
# ---------------------------------------------------------------------------

def _parse_cs(cs: str) -> str | None:
    """Return the EntityPath value from *cs*, or None if absent."""
    for part in cs.split(";"):
        key, _, value = part.partition("=")
        if key.strip().lower() == "entitypath":
            return value.strip()
    return None


def _require_env(name: str) -> str:
    import os
    value = os.getenv(name, "").strip()
    if not value:
        print(
            f"ERROR: {name!r} is not set. Copy .env.example to .env and fill it in.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


# ---------------------------------------------------------------------------
# Speed / sleep helpers
# ---------------------------------------------------------------------------

def sleep_duration(event_clock: int, prev_clock: int, speed: float) -> float:
    """Real seconds to sleep before sending this event.

    speed > 0: *speed* match-seconds advance per real second.
    speed == 0: no sleep (max mode).
    """
    if speed <= 0:
        return 0.0
    delta_match = max(0, event_clock - prev_clock)
    return delta_match / speed


# ---------------------------------------------------------------------------
# Engine helper
# ---------------------------------------------------------------------------

def _build_engine(seed: int, home_id: str, away_id: str):  # type: ignore[return]
    from simulator.engine import MatchEngine
    from simulator.reference_data import build_players, build_teams

    teams = {t.team_id: t for t in build_teams()}
    if home_id not in teams:
        print(f"ERROR: unknown home team {home_id!r}", file=sys.stderr)
        sys.exit(1)
    if away_id not in teams:
        print(f"ERROR: unknown away team {away_id!r}", file=sys.stderr)
        sys.exit(1)
    players = build_players(seed)
    return MatchEngine(
        home_team=teams[home_id],
        away_team=teams[away_id],
        players=players,
        seed=seed,
        match_id=f"match_s{seed}_{home_id}_{away_id}",
        scenario_id="live",
    )


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

def _event_time(run_start: datetime, match_clock_s: int, speed: float) -> datetime:
    """Timestamp for one event.

    event_time = run_start + match_clock_s / effective_speed
    where effective_speed = speed if speed > 0 else 1  (max mode maps to 1×).

    Coordinate rule: x,y in the frame of the team IN POSSESSION (attacking
    towards x=105). Defensive events use the possessing team's frame, so
    "opponent half" for the defending team means x < 52.5.
    """
    effective = speed if speed > 0.0 else 1.0
    return run_start + timedelta(seconds=match_clock_s / effective)


def run_publisher(
    seed: int,
    home_id: str,
    away_id: str,
    speed: float,
    dry_run: bool,
) -> None:
    engine = _build_engine(seed, home_id, away_id)
    events, _ = engine.run()
    # events is list[MatchEvent]; snapshots are separate and not sent here

    run_start = datetime.now(UTC)

    if dry_run:
        print("=== DRY RUN – first 3 messages ===")
        for ev in events[:3]:
            payload = ev.model_copy(
                update={"event_time": _event_time(run_start, ev.match_clock_s, speed)}
            )
            print(payload.model_dump_json(indent=2))
        print(f"\nTotal events that would be sent: {len(events)}")
        return

    import os

    cs = _require_env("EVENTSTREAM_CONNECTION_STRING")
    entity_in_cs = _parse_cs(cs)

    hub_name: str | None = entity_in_cs or os.getenv("EVENTSTREAM_NAME", "").strip() or None

    from azure.eventhub import EventData, EventHubProducerClient

    client_kwargs: dict = {"conn_str": cs}
    if hub_name:
        client_kwargs["eventhub_name"] = hub_name

    producer = EventHubProducerClient.from_connection_string(**client_kwargs)

    total_sent = 0
    prev_clock = 0
    t_start = time.monotonic()

    with producer:
        batch = producer.create_batch()
        batch_count = 0

        for i, ev in enumerate(events):
            payload = ev.model_copy(
                update={"event_time": _event_time(run_start, ev.match_clock_s, speed)}
            )
            data = EventData(payload.model_dump_json())

            try:
                batch.add(data)
                batch_count += 1
            except ValueError:
                # Batch full – flush and start a new one
                producer.send_batch(batch)
                total_sent += batch_count
                batch = producer.create_batch()
                batch_count = 0
                batch.add(data)
                batch_count += 1

            if speed > 0:
                delay = sleep_duration(ev.match_clock_s, prev_clock, speed)
                if delay > 0:
                    time.sleep(delay)
            prev_clock = ev.match_clock_s

            if (i + 1) % 200 == 0:
                producer.send_batch(batch)
                total_sent += batch_count
                batch = producer.create_batch()
                batch_count = 0
                print(f"  {i + 1}/{len(events)} events sent …")

        # Flush remainder
        if batch_count:
            producer.send_batch(batch)
            total_sent += batch_count

    elapsed = time.monotonic() - t_start
    print(
        f"\nDone. {total_sent} events sent in {elapsed:.1f}s "
        f"(seed={seed}, {home_id} vs {away_id})"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Stream one match to a Fabric Eventstream custom endpoint."
    )
    p.add_argument("--seed",  type=int, default=7,   help="RNG seed")
    p.add_argument("--home",  default="T01",          help="Home team ID")
    p.add_argument("--away",  default="T02",          help="Away team ID")
    p.add_argument(
        "--speed",
        default="max",
        help="'max' = no sleep; N = match-seconds per real second (e.g. 10)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print first 3 messages; no network")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    speed = 0.0 if args.speed == "max" else float(args.speed)
    run_publisher(
        seed=args.seed,
        home_id=args.home,
        away_id=args.away,
        speed=speed,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
