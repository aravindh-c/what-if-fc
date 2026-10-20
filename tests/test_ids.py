"""Tests for unified match-id format.

Verifies:
- make_match_id produces the canonical f"match_s{seed}_{home}_{away}" format
- run_match returns make_match_id's result as its match_id
- run_match and publisher._build_engine use the same match_id and scenario_id,
  so their events are identical for the same seed
- the canonical id passes the KQL tools regex
"""

from __future__ import annotations

from simulator.ids import make_match_id


def test_make_match_id_format() -> None:
    assert make_match_id(7, "T01", "T02") == "match_s7_T01_T02"
    assert make_match_id(1, "T03", "T04") == "match_s1_T03_T04"


def test_make_match_id_passes_kql_regex() -> None:
    from agents.kql_tools import _validate_match_id  # noqa: PLC2701

    _validate_match_id(make_match_id(7, "T01", "T02"))


def test_run_match_returns_canonical_id() -> None:
    from simulator.run import run_match

    match_id, _, _ = run_match(7, "T01", "T02")
    assert match_id == make_match_id(7, "T01", "T02")
    assert match_id == "match_s7_T01_T02"


def test_run_match_events_equal_publisher_events() -> None:
    """run_match and publisher._build_engine must produce identical events for seed 7."""
    from simulator.publisher import _build_engine
    from simulator.run import run_match

    match_id, run_events, _ = run_match(7, "T01", "T02")
    pub_events, _ = _build_engine(7, "T01", "T02").run()

    assert len(run_events) == len(pub_events), (
        f"event count differs: run_match={len(run_events)}, publisher={len(pub_events)}"
    )
    for i, (re, pe) in enumerate(zip(run_events, pub_events, strict=True)):
        re_dict = re.model_dump(mode="json")
        pe_dict = pe.model_dump(mode="json")
        assert re_dict == pe_dict, f"event {i} differs:\nrun_match: {re_dict}\npublisher: {pe_dict}"
