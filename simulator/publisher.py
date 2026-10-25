"""Day 3B / Day 6A: stream one match's events (and position snapshots) to
Fabric Eventstream custom endpoints.

Usage:
    python -m simulator.publisher --seed 7 --home T01 --away T02 --speed max
    python -m simulator.publisher --seed 7 --home T01 --away T02 --dry-run
    python -m simulator.publisher --seed 7 --home T01 --away T02 --no-snapshots

Environment variables (loaded from .env):
    EVENTSTREAM_CONNECTION_STRING           – Event Hub-compatible connection
                                              string for match events;
                                              may include EntityPath
    EVENTSTREAM_NAME                        – optional override for the Event
                                              Hub name (ignored when EntityPath
                                              is already in the connection
                                              string)
    SNAPSHOT_EVENTSTREAM_CONNECTION_STRING  – connection string for position
                                              snapshots; if absent a warning is
                                              printed and snapshots are skipped
    SNAPSHOT_EVENTSTREAM_NAME               – optional override for the snapshot
                                              Event Hub name
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

from core.schemas import MatchEvent, PositionSnapshot

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
    from simulator.ids import make_match_id
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
        match_id=make_match_id(seed, home_id, away_id),
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


def _interleave(
    events: list[MatchEvent],
    snaps: dict[str, PositionSnapshot],
) -> list[tuple[str, MatchEvent | PositionSnapshot]]:
    """Return (kind, obj) pairs in send order.

    Each snapshot precedes the first event that references its snapshot_id,
    so a snapshot always arrives at the Eventstream no later than its event.
    Snapshots whose snapshot_id is never referenced by an event are omitted.
    """
    result: list[tuple[str, MatchEvent | PositionSnapshot]] = []
    sent: set[str] = set()
    for ev in events:
        if ev.snapshot_id and ev.snapshot_id not in sent and ev.snapshot_id in snaps:
            result.append(("snapshot", snaps[ev.snapshot_id]))
            sent.add(ev.snapshot_id)
        result.append(("event", ev))
    return result


def run_publisher(
    seed: int,
    home_id: str,
    away_id: str,
    speed: float,
    dry_run: bool,
    send_snapshots: bool = True,
) -> None:
    engine = _build_engine(seed, home_id, away_id)
    events, snapshots = engine.run()
    snap_by_id: dict[str, PositionSnapshot] = {s.snapshot_id: s for s in snapshots}

    run_start = datetime.now(UTC)

    if dry_run:
        print("=== DRY RUN – first 3 messages ===")
        if send_snapshots and snapshots:
            print("--- Snapshot (first) ---")
            print(snapshots[0].model_dump_json(indent=2))
        for ev in events[:3]:
            payload = ev.model_copy(
                update={"event_time": _event_time(run_start, ev.match_clock_s, speed)}
            )
            print(payload.model_dump_json(indent=2))
        print(f"\nTotal events that would be sent: {len(events)}")
        if send_snapshots:
            print(f"Total snapshots that would be sent: {len(snapshots)}")
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

    snap_producer: EventHubProducerClient | None = None
    if send_snapshots:
        snap_cs = os.getenv("SNAPSHOT_EVENTSTREAM_CONNECTION_STRING", "").strip()
        if not snap_cs:
            print(
                "WARNING: SNAPSHOT_EVENTSTREAM_CONNECTION_STRING not set; "
                "snapshots will not be sent.",
                file=sys.stderr,
            )
            send_snapshots = False
        else:
            snap_entity = _parse_cs(snap_cs)
            snap_hub = (
                snap_entity or os.getenv("SNAPSHOT_EVENTSTREAM_NAME", "").strip() or None
            )
            snap_kw: dict = {"conn_str": snap_cs}
            if snap_hub:
                snap_kw["eventhub_name"] = snap_hub
            snap_producer = EventHubProducerClient.from_connection_string(**snap_kw)

    total_sent = 0
    total_snaps_sent = 0
    prev_clock = 0
    t_start = time.monotonic()
    last_flush_t = t_start
    snaps_sent: set[str] = set()

    with contextlib.ExitStack() as stack:
        stack.enter_context(producer)
        if snap_producer is not None:
            stack.enter_context(snap_producer)

        batch = producer.create_batch()
        batch_count = 0
        snap_batch = snap_producer.create_batch() if snap_producer else None
        snap_batch_count = 0

        for i, ev in enumerate(events):
            # Send the snapshot just before the first event that references it.
            if (
                send_snapshots
                and snap_producer is not None
                and snap_batch is not None
                and ev.snapshot_id
                and ev.snapshot_id not in snaps_sent
            ):
                snap = snap_by_id.get(ev.snapshot_id)
                if snap:
                    snap_data = EventData(snap.model_dump_json())
                    try:
                        snap_batch.add(snap_data)
                        snap_batch_count += 1
                    except ValueError:
                        snap_producer.send_batch(snap_batch)
                        total_snaps_sent += snap_batch_count
                        snap_batch = snap_producer.create_batch()
                        snap_batch_count = 0
                        snap_batch.add(snap_data)
                        snap_batch_count += 1
                    # Flush immediately to guarantee the snapshot arrives before its event.
                    snap_producer.send_batch(snap_batch)
                    total_snaps_sent += snap_batch_count
                    snap_batch = snap_producer.create_batch()
                    snap_batch_count = 0
                    snaps_sent.add(ev.snapshot_id)

            payload = ev.model_copy(
                update={"event_time": _event_time(run_start, ev.match_clock_s, speed)}
            )
            data = EventData(payload.model_dump_json())

            try:
                batch.add(data)
                batch_count += 1
            except ValueError:
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

            # Time-based flush: at least once per real second when speed > 0
            if speed > 0 and batch_count > 0:
                now_t = time.monotonic()
                if now_t - last_flush_t >= 1.0:
                    producer.send_batch(batch)
                    total_sent += batch_count
                    batch = producer.create_batch()
                    batch_count = 0
                    last_flush_t = now_t

            if (i + 1) % 200 == 0 and batch_count > 0:
                producer.send_batch(batch)
                total_sent += batch_count
                batch = producer.create_batch()
                batch_count = 0
                last_flush_t = time.monotonic()
                print(f"  {i + 1}/{len(events)} events sent …")

        # Flush remainder
        if batch_count:
            producer.send_batch(batch)
            total_sent += batch_count

    elapsed = time.monotonic() - t_start
    print(
        f"\nDone. {total_sent} events, {total_snaps_sent} snapshots sent "
        f"in {elapsed:.1f}s (seed={seed}, {home_id} vs {away_id})"
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
    p.add_argument(
        "--no-snapshots",
        action="store_true",
        help="Send events only; skip position snapshot streaming",
    )
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
        send_snapshots=not args.no_snapshots,
    )


if __name__ == "__main__":
    main()
