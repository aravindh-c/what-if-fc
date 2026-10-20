"""Deterministic validator for overlay text.

Acceptance-test references
--------------------------
AT-06 – every event_id cited in text must be in packet.event_ids
AT-07 – every number must match a packet value after rounding to 0 or 1 dp
AT-09 – fan numbers must be a strict subset of analyst numbers
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_BANNED_TERMS: tuple[str, ...] = (
    "xg", "xa", "xt",
    "expected goals", "expected assists",
    "probability",
    "% chance",
)

_EVENT_ID_RE = re.compile(r"\bev_[A-Za-z0-9_]+\b")

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

# Lowercase words that may appear capitalised in English text but are NOT
# player names from the fictional roster.
_FOOTBALL_STOPWORDS: frozenset[str] = frozenset(
    {
        # articles / conjunctions / prepositions
        "the", "a", "an", "and", "but", "or", "for", "nor", "so", "yet",
        "in", "on", "at", "by", "to", "of", "up", "as", "if", "with",
        "from", "into", "onto", "upon", "over", "under", "through",
        "after", "before", "during", "since", "until", "about",
        # pronouns
        "it", "its", "he", "she", "they", "we", "you", "who", "what",
        "how", "why", "when", "where", "this", "that", "these", "those",
        # common verbs / auxiliaries
        "was", "were", "has", "have", "had", "will", "would", "could",
        "should", "is", "are", "be", "been", "being", "play", "played",
        "score", "scored", "scores", "shoot", "shot", "win", "wins",
        "won", "lost", "lead", "leads", "led",
        # quantity / degree words
        "all", "some", "most", "much", "many", "more", "less", "few",
        "very", "just", "now", "then", "here", "there", "no", "not",
        "never", "always", "still", "already", "each", "both",
        "either", "neither", "such", "other", "another",
        # adjectives
        "big", "good", "better", "best", "new", "old", "next",
        "last", "same", "early", "late", "open", "free", "clear",
        "close", "long", "short", "quick", "slow", "high", "low",
        "top", "bottom", "deep", "wide", "right", "left", "far",
        # football / match terms
        "ghost", "pass", "tactical", "twin", "evidence", "ledger",
        "analyst", "fan", "goal", "goals", "tackle", "pressure",
        "momentum", "swing", "turnover", "spell", "match", "game",
        "team", "player", "minute", "half", "period", "final",
        "third", "scoreline", "option", "actual", "wing", "forward",
        "back", "keeper", "defender", "midfielder", "striker", "winger",
        "league", "cup", "stadium", "home", "away", "formation",
        "first", "second", "centre", "center", "space", "lane", "ball",
        "move", "chance", "attack", "defense", "defence", "result",
        "counter", "press", "pressing", "possession", "overlap",
        "offside", "penalty", "corner", "foul", "cross", "dribble",
        # overlay / narrative specific
        "delta", "index", "metric", "great", "run",
        "watch", "level", "ahead", "behind", "equal", # fictional team names (split into tokens)
        "kestrel", "vale", "thornfield", "rovers", "saltmere",
        "mariners", "copperhill", "athletic",
    }
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_numbers(text: str) -> list[float]:
    return [float(m) for m in _NUMBER_RE.findall(text)]


def _extract_event_ids(text: str) -> list[str]:
    return _EVENT_ID_RE.findall(text)


def _extract_potential_names(text: str) -> list[str]:
    """Return capitalised alpha words (≥3 chars) that are not football stopwords."""
    words = re.findall(r"\b[A-Z][a-z]{2,}\b", text)
    return [w for w in words if w.lower() not in _FOOTBALL_STOPWORDS]


def _build_roster_name_tokens(roster: Sequence) -> set[str]:
    tokens: set[str] = set()
    for player in roster:
        for part in player.name.lower().split():
            for subpart in re.split(r"[-]", part):
                if subpart:
                    tokens.add(subpart)
    return tokens


def _packet_number_sets(packet) -> tuple[set[float], set[float]]:
    """Return (values_rounded_to_0dp, values_rounded_to_1dp)."""
    s0: set[float] = set()
    s1: set[float] = set()

    def _add(v: float | int | None) -> None:
        if v is None:
            return
        f = float(v)
        s0.add(round(f, 0))
        s1.add(round(f, 1))

    _add(packet.moment_minute)
    _add(packet.moment_score)
    _add(packet.twin_delta)
    _add(packet.twin_actual_score)
    _add(packet.twin_ghost_score)
    _add(packet.pass_difficulty)
    _add(packet.actual_pass_length_m)
    _add(packet.ghost_pass_length_m)
    _add(packet.actual_nearest_defender_m)
    _add(packet.ghost_nearest_defender_m)

    for v in packet.live_metrics.scoreline.values():
        _add(v)
    for v in packet.live_metrics.momentum_share.values():
        _add(v)
    for v in packet.live_metrics.pressure_index.values():
        _add(v)
    for v in packet.twin_components_actual.values():
        _add(v)
    for v in packet.twin_components_ghost.values():
        _add(v)

    return s0, s1


def _is_allowed(num: float, s0: set[float], s1: set[float]) -> bool:
    return round(num, 0) in s0 or round(num, 1) in s1


def _add_tool_results(
    s0: set[float], s1: set[float], tool_results: list[dict]
) -> None:
    for result in tool_results:
        for v in result.values():
            if isinstance(v, (int, float)):
                s0.add(round(float(v), 0))
                s1.add(round(float(v), 1))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_text(
    output,
    packet,
    roster: Sequence,
    tool_results: list[dict] | None = None,
) -> list[str]:
    """Validate overlay text against the evidence packet.

    AT-06: every event_id cited must be in packet.event_ids
    AT-07: every number must match a packet value after rounding to 0 or 1 dp
    AT-09: fan numbers must be a subset of analyst numbers

    Parameters
    ----------
    output:
        An OverlayText instance (or duck-typed equivalent with .analyst and .fan dicts
        mapping language code to NarrativeText with .headline and .body attributes).
    packet:
        An EvidencePacket instance.
    roster:
        Sequence of Player instances used to validate player name mentions.
    tool_results:
        Optional list of dicts returned by KQL tool calls; their numeric values
        are added to the allowed number set.

    Returns
    -------
    list[str]
        Empty list when all checks pass; one error string per violation.
    """
    errors: list[str] = []

    en_analyst = output.analyst.get("en")
    en_fan = output.fan.get("en")

    # English required
    if en_analyst is None:
        errors.append("analyst English text ('en') is missing")
        return errors
    if en_fan is None:
        errors.append("fan English text ('en') is missing")
        return errors

    # Length checks (redundant with schema but defensive)
    for label, nt in (("analyst", en_analyst), ("fan", en_fan)):
        if len(nt.headline) > 80:
            errors.append(
                f"{label} headline too long ({len(nt.headline)} chars, max 80)"
            )
        if len(nt.body) > 280:
            errors.append(
                f"{label} body too long ({len(nt.body)} chars, max 280)"
            )

    # Collect all text pieces
    all_pieces = [
        en_analyst.headline,
        en_analyst.body,
        en_fan.headline,
        en_fan.body,
    ]
    if getattr(output, "cue", None):
        all_pieces.append(output.cue)

    # Banned terms
    for piece in all_pieces:
        piece_lower = piece.lower()
        for term in _BANNED_TERMS:
            if term in piece_lower:
                errors.append(f"banned term {term!r} found in text")

    # Build allowed number sets
    s0, s1 = _packet_number_sets(packet)
    if tool_results:
        _add_tool_results(s0, s1, tool_results)

    # Number validation (AT-07)
    analyst_nums = _extract_numbers(en_analyst.headline + " " + en_analyst.body)
    fan_nums = _extract_numbers(en_fan.headline + " " + en_fan.body)

    for num in analyst_nums:
        if not _is_allowed(num, s0, s1):
            errors.append(
                f"analyst text contains number {num} not matched in evidence packet (AT-07)"
            )

    for num in fan_nums:
        if not _is_allowed(num, s0, s1):
            errors.append(
                f"fan text contains number {num} not matched in evidence packet (AT-07)"
            )

    # Fan numbers ⊆ analyst numbers (AT-09)
    for fan_num in fan_nums:
        matched = any(
            round(fan_num, 0) == round(a_num, 0)
            or round(fan_num, 1) == round(a_num, 1)
            for a_num in analyst_nums
        )
        if not matched:
            errors.append(
                f"fan text number {fan_num} is not in analyst text (AT-09)"
            )

    # Event ID integrity (AT-06)
    valid_eids = set(packet.event_ids)
    for piece in all_pieces:
        for eid in _extract_event_ids(piece):
            if eid not in valid_eids:
                errors.append(
                    f"event_id {eid!r} cited in text not found in packet.event_ids (AT-06)"
                )

    # Player name check
    if roster:
        name_tokens = _build_roster_name_tokens(roster)
        for piece in all_pieces:
            for word in _extract_potential_names(piece):
                if word.lower() not in name_tokens:
                    errors.append(
                        f"player name {word!r} not found in roster"
                    )

    return errors
