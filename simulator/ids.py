"""Canonical match-id format for all What If FC systems."""

from __future__ import annotations


def make_match_id(seed: int, home: str, away: str) -> str:
    """Return the canonical match identifier used across simulator, publisher, and Fabric."""
    return f"match_s{seed}_{home}_{away}"
