"""Integration test (Spec 005 T051 / gaps §D1): resolver eval-set.

A canonical 50+-row eval-set of (query, expected_slug) pairs that the
ResolveDirectory tool must resolve correctly. Run on every PR; a single
miss fails the suite.

The directory is seeded into an in-memory SQLite at fixture-setup time
with ~30 representative game rows that span the four kinds we ship with
(slingo, slots, blackjack, roulette). The eval-set then exercises:

  - exact slug match
  - kind filter + LIKE
  - alias substring match
  - token-set fallback (e.g. typos, word reorder)
  - 'unresolved' branch for queries that should NOT match anything
"""

from __future__ import annotations

from typing import List, Tuple

import pytest

from shared.screen_map_db import ScreenMapDB
from tools.casino_qa import _deps
from tools.casino_qa.resolve_directory import resolve_directory


# ── Directory fixture ─────────────────────────────────────────────────


# (slug, display_name, kind, aliases, popularity)
_DIRECTORY_ROWS: List[Tuple[str, str, str, List[str], int]] = [
    # Slingo (flagship line)
    ("slingo_classic",         "Slingo Classic",          "slingo",   ["classic slingo", "og slingo"],     8),
    ("slingo_cash_eruption",   "Slingo Cash Eruption",    "slingo",   ["cash eruption", "eruption"],       7),
    ("slingo_riches",          "Slingo Riches",           "slingo",   ["riches"],                          5),
    ("slingo_rainbow_riches",  "Slingo Rainbow Riches",   "slingo",   ["rainbow riches", "rainbow"],       6),
    ("slingo_starburst",       "Slingo Starburst",        "slingo",   ["starburst slingo"],                4),
    ("slingo_x",               "Slingo X",                "slingo",   ["x"],                               2),
    # Slots
    ("fanatics_spin_to_win",   "Fanatics Spin to Win",    "slots",    ["spin to win", "stw"],              9),
    ("starburst",              "Starburst",               "slots",    ["star burst"],                      8),
    ("gonzo_quest",            "Gonzo's Quest",           "slots",    ["gonzo", "gonzos quest"],           6),
    ("book_of_dead",           "Book of Dead",            "slots",    ["book", "dead"],                    7),
    ("dead_or_alive",          "Dead or Alive",           "slots",    ["doa"],                             5),
    ("buffalo_blitz",          "Buffalo Blitz",           "slots",    ["buffalo"],                         5),
    ("megaways_bonanza",       "Megaways Bonanza",        "slots",    ["bonanza", "megaways"],             6),
    # Blackjack
    ("fanatics_blackjack",     "Fanatics Blackjack",      "blackjack", ["fanatics bj", "blackjack"],       9),
    ("classic_blackjack",      "Classic Blackjack",       "blackjack", ["classic bj"],                     7),
    ("blackjack_pro",          "Blackjack Pro",           "blackjack", ["bj pro"],                         5),
    ("multi_hand_blackjack",   "Multi-Hand Blackjack",    "blackjack", ["multi hand bj", "multihand"],     4),
    # Roulette
    ("american_roulette",      "American Roulette",       "roulette", ["us roulette", "double zero"],     8),
    ("european_roulette",      "European Roulette",       "roulette", ["eu roulette", "single zero"],     8),
    ("french_roulette",        "French Roulette",         "roulette", ["en prison"],                      5),
    ("lightning_roulette",     "Lightning Roulette",      "roulette", ["lightning"],                      6),
    # Live dealer (kind=live_dealer for spec 005 schema, but our directory
    # uses 'roulette' / 'blackjack' for live tables — see real game_kinds).
    ("live_blackjack_a",       "Live Blackjack Table A",  "blackjack", ["live blackjack", "live bj"],      7),
    ("live_roulette_studio_3", "Live Roulette Studio 3",  "roulette", ["live roulette"],                   7),
]


@pytest.fixture
def db() -> ScreenMapDB:
    db = ScreenMapDB(":memory:")
    for slug, display, kind, aliases, popularity in _DIRECTORY_ROWS:
        db.upsert_game_directory(
            slug, display, kind,
            aliases=aliases, popularity=popularity,
            loaded_signature=f"{slug}_loaded",
        )
    _deps.set_screen_db(db)
    yield db
    db.close()
    _deps.set_screen_db(None)


# ── Eval-set ──────────────────────────────────────────────────────────


# Each row: (query, kind_filter, expected_slug, expected_reason_set)
# `expected_reason_set` accepts any of multiple reasons since several
# strategies can find the right hit (alias/like/token).
_RESOLVED: List[Tuple[str, str, str, set]] = [
    # exact display name → name_like (LIKE matches the full string)
    ("Slingo Classic",          "",         "slingo_classic",        {"name_like"}),
    ("Slingo Cash Eruption",    "",         "slingo_cash_eruption",  {"name_like"}),
    ("Fanatics Spin to Win",    "",         "fanatics_spin_to_win",  {"name_like"}),
    ("Fanatics Blackjack",      "",         "fanatics_blackjack",    {"name_like"}),
    ("American Roulette",       "",         "american_roulette",     {"name_like"}),
    # case-insensitive
    ("slingo classic",          "",         "slingo_classic",        {"name_like"}),
    ("FANATICS BLACKJACK",      "",         "fanatics_blackjack",    {"name_like"}),
    # substring of display name
    ("classic",                 "slingo",   "slingo_classic",        {"name_like"}),
    ("eruption",                "",         "slingo_cash_eruption",  {"name_like", "alias_match"}),
    ("riches",                  "slingo",   "slingo_rainbow_riches", {"name_like"}),  # popularity 6 > 5
    ("starburst",               "slots",    "starburst",             {"name_like"}),  # within slots filter
    # alias match
    ("og slingo",               "",         "slingo_classic",        {"alias_match"}),
    ("rainbow",                 "",         "slingo_rainbow_riches", {"alias_match", "name_like"}),
    ("stw",                     "",         "fanatics_spin_to_win",  {"alias_match"}),
    ("doa",                     "",         "dead_or_alive",         {"alias_match"}),
    ("buffalo",                 "",         "buffalo_blitz",         {"alias_match", "name_like"}),
    ("bonanza",                 "",         "megaways_bonanza",      {"name_like", "alias_match"}),
    ("us roulette",             "",         "american_roulette",     {"alias_match"}),
    ("eu roulette",             "",         "european_roulette",     {"alias_match"}),
    ("en prison",               "",         "french_roulette",       {"alias_match"}),
    ("lightning",               "",         "lightning_roulette",    {"alias_match", "name_like"}),
    ("classic bj",              "",         "classic_blackjack",     {"alias_match"}),
    ("multihand",               "",         "multi_hand_blackjack",  {"alias_match"}),
    ("live bj",                 "",         "live_blackjack_a",      {"alias_match"}),
    # kind filter narrowing
    ("classic",                 "blackjack", "classic_blackjack",    {"name_like", "alias_match"}),
    # token-set fallback (word-order independent)
    ("quest gonzo",             "",         "gonzo_quest",           {"token_set"}),
    ("dead book",               "",         "book_of_dead",          {"token_set"}),
    ("blitz buffalo",           "",         "buffalo_blitz",         {"token_set", "name_like"}),
    ("studio live roulette",    "",         "live_roulette_studio_3", {"token_set", "alias_match"}),
    # popularity tie-break (multiple slingo names contain "slingo"; popularity wins)
    ("slingo",                  "",         "slingo_classic",        {"name_like"}),  # popularity 8 = top
    # numeric/short slug
    ("slingo x",                "",         "slingo_x",              {"name_like", "token_set"}),
    # Additional substring + alias coverage to clear the 50-row floor.
    ("rainbow riches",          "",         "slingo_rainbow_riches", {"name_like", "alias_match"}),
    ("cash eruption",           "",         "slingo_cash_eruption",  {"name_like", "alias_match"}),
    ("Spin to Win",             "",         "fanatics_spin_to_win",  {"name_like", "alias_match"}),
    ("gonzo",                   "",         "gonzo_quest",           {"alias_match", "name_like"}),
    ("gonzos quest",            "",         "gonzo_quest",           {"alias_match", "name_like"}),
    ("dead",                    "",         "book_of_dead",          {"alias_match", "name_like"}),  # popularity 7 > 5
    ("multi hand bj",           "",         "multi_hand_blackjack",  {"alias_match"}),
    ("live blackjack",          "",         "live_blackjack_a",      {"alias_match", "name_like"}),
    ("live roulette",           "",         "live_roulette_studio_3", {"alias_match", "name_like"}),
    ("blackjack",               "blackjack", "fanatics_blackjack",   {"alias_match", "name_like"}),  # popularity 9 = top
    ("roulette",                "roulette", "american_roulette",     {"name_like"}),  # popularity 8 tie, last_played NULL → first by ORDER
    ("slingo",                  "slingo",   "slingo_classic",        {"name_like"}),  # popularity 8 = top
    # Token-set: typo-tolerant (single-token substring already matches via LIKE)
    ("classic blackjack table", "blackjack", "classic_blackjack",    {"name_like", "token_set"}),
]


# Canonical UNRESOLVED queries — the resolver must NOT pretend to match.
_UNRESOLVED: List[str] = [
    "poker",            # no poker in directory
    "baccarat",
    "keno",
    "scratchcards",
    "qwertyuiop",
    "this is not a game",
    "🎰",
    "play me anything",  # too vague to disambiguate (?? actually may match — see below)
]


# Eval-set total assertion (gaps §D1 says "50+"). Combine the two lists
# plus the implicit count contributions and assert the total.
_TOTAL_EXPECTED_PAIRS = len(_RESOLVED) + len(_UNRESOLVED)


def test_eval_set_size() -> None:
    """The eval-set must remain ≥ 50 rows. Drop additions that shrink it below."""
    assert _TOTAL_EXPECTED_PAIRS >= 50, _TOTAL_EXPECTED_PAIRS


@pytest.mark.parametrize("query,kind,expected_slug,reasons", _RESOLVED)
def test_resolver_resolved_cases(
    db: ScreenMapDB,
    query: str,
    kind: str,
    expected_slug: str,
    reasons: set,
) -> None:
    out = resolve_directory({"query": query, "kind": kind, "limit": 5})
    assert out["resolved"] is True, out
    assert out["slug"] == expected_slug, (
        f"query={query!r} kind={kind!r} expected slug={expected_slug!r} "
        f"got slug={out['slug']!r} reason={out['reason']!r}"
    )
    assert out["reason"] in reasons, (
        f"query={query!r} reason={out['reason']!r} not in expected={reasons}"
    )


@pytest.mark.parametrize("query", _UNRESOLVED)
def test_resolver_unresolved_cases(db: ScreenMapDB, query: str) -> None:
    """For queries that don't correspond to any catalog entry, the resolver
    must report unresolved rather than picking a low-confidence match."""
    out = resolve_directory({"query": query, "limit": 5})
    # Reasonable: either fully unresolved, or a token_set/name_like fallback
    # with a popularity > 0 alternative, but the schema says falling open is
    # caller's burden — we assert resolved == False for these explicit gaps.
    if out["resolved"]:
        # Allow if reason is token_set with very low overlap and popularity
        # tie-broke into a default slug — but log it. Today, none of the
        # directory's display names overlap meaningfully with the unresolved
        # queries, so we strictly assert.
        pytest.fail(
            f"unresolved-by-design query {query!r} matched slug={out['slug']!r} "
            f"reason={out['reason']!r}; tighten resolver or trim eval-set"
        )
    assert out["reason"] in {"unresolved", "no_query"}, out
    assert out["slug"] is None, out


# ── Exact-slug shortcut ────────────────────────────────────────────────


def test_explicit_slug_skips_fuzzy_path(db: ScreenMapDB) -> None:
    out = resolve_directory({"slug": "fanatics_spin_to_win"})
    assert out["resolved"] is True
    assert out["reason"] == "exact_slug"
    assert out["slug"] == "fanatics_spin_to_win"


def test_explicit_slug_unknown_falls_through(db: ScreenMapDB) -> None:
    """Bad explicit slug + no query → unresolved, not crash."""
    out = resolve_directory({"slug": "nonexistent_game"})
    assert out["resolved"] is False
    # Falls through to no_query branch since no fuzzy text supplied.
    assert out["reason"] in {"no_query", "unresolved"}
