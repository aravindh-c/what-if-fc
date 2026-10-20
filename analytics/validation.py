"""Deterministic validator for overlay text.

Acceptance-test references
--------------------------
AT-06 – every event_id cited in text must be in packet.event_ids
AT-07 – every number must match a packet value at the same decimal precision
AT-09 – fan numbers must be a strict subset of analyst numbers
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Banned terms as whole-word regex patterns (case-insensitive).
# \b prevents "xt" matching inside "next", "text", "extra", etc.
_BANNED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bxg\b", re.IGNORECASE),
    re.compile(r"\bxa\b", re.IGNORECASE),
    re.compile(r"\bxt\b", re.IGNORECASE),
    re.compile(r"\bexpected\s+goals\b", re.IGNORECASE),
    re.compile(r"\bexpected\s+assists\b", re.IGNORECASE),
    re.compile(r"\bprobability\b", re.IGNORECASE),
    re.compile(r"%\s*chance\b", re.IGNORECASE),
]

_BANNED_LABELS: tuple[str, ...] = (
    "xg", "xa", "xt",
    "expected goals", "expected assists",
    "probability", "% chance",
)

_EVENT_ID_RE = re.compile(r"\bev_[A-Za-z0-9_]+\b")

# Captures an optional leading minus, a number, and an optional trailing % sign.
# Negative lookbehind prevents matching digits inside identifiers like "T01-P08"
# (where the minus is preceded by an alphanumeric character).
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])(-?\d+(?:\.\d+)?)(%)?")

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
        "watch", "level", "ahead", "behind", "equal",
        # fictional team names (split into tokens)
        "kestrel", "vale", "thornfield", "rovers", "saltmere",
        "mariners", "copperhill", "athletic",
        # extra sentence-starters that are not player names
        "meanwhile", "brilliant", "relentless",
    }
)


# ---------------------------------------------------------------------------
# Internal helpers – numbers
# ---------------------------------------------------------------------------


def _num_dp(s: str) -> int:
    """Return the number of decimal places in a numeric string."""
    return len(s.split(".")[1]) if "." in s else 0


def _extract_numbers_with_meta(text: str) -> list[tuple[float, int, bool]]:
    """Extract (value, decimal_places, is_percentage) triples from text."""
    results: list[tuple[float, int, bool]] = []
    for m in _NUMBER_RE.finditer(text):
        num_str = m.group(1)
        is_pct = bool(m.group(2))
        results.append((float(num_str), _num_dp(num_str), is_pct))
    return results


def _packet_number_sets(
    packet,
) -> tuple[dict[int, set[float]], set[float]]:
    """Return per-precision allowed sets and a percentage set.

    Returns (sets, pct_s0) where sets maps dp -> set of packet values rounded
    to dp decimal places (dp in 0..3), and pct_s0 holds momentum/pressure
    share values × 100 rounded to 0 dp (for "55%" style text).
    """
    sets: dict[int, set[float]] = {0: set(), 1: set(), 2: set(), 3: set()}
    pct_s0: set[float] = set()

    def _add(v: float | int | None) -> None:
        if v is None:
            return
        f = float(v)
        for dp in range(4):
            sets[dp].add(round(f, dp))

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
    _add(getattr(packet, "actual_progress_m", None))
    _add(getattr(packet, "ghost_progress_m", None))

    for v in packet.live_metrics.scoreline.values():
        _add(v)
    for v in packet.live_metrics.momentum_share.values():
        _add(v)
        pct_s0.add(round(float(v) * 100, 0))
    for v in packet.live_metrics.pressure_index.values():
        _add(v)
        pct_s0.add(round(float(v) * 100, 0))
    for v in packet.twin_components_actual.values():
        _add(v)
    for v in packet.twin_components_ghost.values():
        _add(v)

    return sets, pct_s0


def _is_allowed_precise(
    num: float,
    dp: int,
    is_pct: bool,
    sets: dict[int, set[float]],
    pct_s0: set[float],
) -> bool:
    """Return True if num is a valid packet-derived value at its own precision.

    Integers (dp==0) compare at 0 dp; decimals compare ONLY at their own
    precision (1 dp, 2 dp, …); never fall back to 0 dp for decimals.
    Percentages compare against momentum/pressure share × 100 at 0 dp.
    """
    if is_pct:
        return round(num, 0) in pct_s0
    key = min(dp, 3)
    return round(num, key) in sets[key]


def _add_tool_results(
    sets: dict[int, set[float]],
    pct_s0: set[float],
    tool_results: list[dict],
) -> None:
    for result in tool_results:
        for v in result.values():
            if isinstance(v, (int, float)):
                f = float(v)
                for dp in range(4):
                    sets[dp].add(round(f, dp))


# ---------------------------------------------------------------------------
# Internal helpers – player names
# ---------------------------------------------------------------------------


def _build_roster_name_tokens(roster: Sequence) -> set[str]:
    tokens: set[str] = set()
    for player in roster:
        for part in player.name.lower().split():
            for subpart in re.split(r"[-]", part):
                if subpart:
                    tokens.add(subpart)
    return tokens


def _build_allowed_player_ids(packet) -> set[str]:
    """IDs of players whose names may appear in overlay text for this moment."""
    ids: set[str] = set()
    for field in ("passer_id", "actual_receiver_id", "twin_ghost_player_id"):
        v = getattr(packet, field, None)
        if v:
            ids.add(v)
    ids.update(packet.highlight_defenders)
    return ids


def _non_sentence_initial_caps(text: str) -> list[str]:
    """Capitalised words (≥3 alpha chars) that are NOT at sentence/headline start.

    The first word of the text, and the first word after a sentence-ending
    token (one that contains . ! or ?), are treated as sentence-initial and
    excluded.  This prevents false positives on words like "Score:",
    "Meanwhile", or "Brilliant" when they open a sentence.
    """
    results: list[str] = []
    sentence_start = True
    for token in text.split():
        # Strip leading/trailing non-alpha to get the bare word
        word = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", token)
        if re.match(r"^[A-Z][a-z]{2,}$", word):
            if not sentence_start:
                results.append(word)
        # If the original token contains . ! ? it ends a sentence
        sentence_start = bool(re.search(r"[.!?]", token))
    return results


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
    AT-07: every number must match a packet value at the same decimal precision
    AT-09: fan numbers must be a subset of analyst numbers

    Parameters
    ----------
    output:
        An OverlayText instance (or duck-typed equivalent with .analyst and .fan
        dicts mapping language code to NarrativeText).
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

    # Length checks (redundant with schema but defensive against model_construct bypass)
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

    # Banned terms (whole-word regex, case-insensitive)
    for piece in all_pieces:
        for pattern, label in zip(_BANNED_PATTERNS, _BANNED_LABELS, strict=True):
            if pattern.search(piece):
                errors.append(f"banned term {label!r} found in text")

    # Build allowed number sets
    sets, pct_s0 = _packet_number_sets(packet)
    if tool_results:
        _add_tool_results(sets, pct_s0, tool_results)

    # Number validation (AT-07) – precision-aware, no 0-dp fallback for decimals
    analyst_nums_meta = _extract_numbers_with_meta(
        en_analyst.headline + " " + en_analyst.body
    )
    fan_nums_meta = _extract_numbers_with_meta(
        en_fan.headline + " " + en_fan.body
    )

    for num, dp, is_pct in analyst_nums_meta:
        if not _is_allowed_precise(num, dp, is_pct, sets, pct_s0):
            errors.append(
                f"analyst text contains number {num} not matched in evidence packet (AT-07)"
            )

    for num, dp, is_pct in fan_nums_meta:
        if not _is_allowed_precise(num, dp, is_pct, sets, pct_s0):
            errors.append(
                f"fan text contains number {num} not matched in evidence packet (AT-07)"
            )

    # Fan numbers ⊆ analyst numbers (AT-09) – compared at fan number's precision
    for f_val, f_dp, f_is_pct in fan_nums_meta:
        if f_is_pct:
            f_target = round(f_val, 0)
            matched = any(
                a_is_pct and round(a_val, 0) == f_target
                for a_val, _, a_is_pct in analyst_nums_meta
            )
        else:
            key = min(f_dp, 3)
            f_target = round(f_val, key)
            matched = any(
                not a_is_pct and round(a_val, key) == f_target
                for a_val, _, a_is_pct in analyst_nums_meta
            )
        if not matched:
            errors.append(
                f"fan text number {f_val} is not in analyst text (AT-09)"
            )

    # Event ID integrity (AT-06)
    valid_eids = set(packet.event_ids)
    for piece in all_pieces:
        for eid in _EVENT_ID_RE.findall(piece):
            if eid not in valid_eids:
                errors.append(
                    f"event_id {eid!r} cited in text not found in packet.event_ids (AT-06)"
                )

    # Player name check (two rules)
    if roster:
        all_roster_name_tokens = _build_roster_name_tokens(roster)
        allowed_ids = _build_allowed_player_ids(packet)

        # Rule A: a forbidden roster player's full name appears in text
        forbidden_players = [p for p in roster if p.player_id not in allowed_ids]
        combined_lower = " ".join(all_pieces).lower()
        for fp in forbidden_players:
            pattern = r"\b" + re.escape(fp.name.lower()) + r"\b"
            if re.search(pattern, combined_lower):
                errors.append(
                    f"player {fp.name!r} appears in text but is not in this moment"
                )

        # Rule B: mid-sentence capitalised word not in roster or stopwords
        for piece in all_pieces:
            for word in _non_sentence_initial_caps(piece):
                wl = word.lower()
                if wl not in all_roster_name_tokens and wl not in _FOOTBALL_STOPWORDS:
                    errors.append(
                        f"capitalised word {word!r} not found in roster or stopwords"
                    )

    return errors
