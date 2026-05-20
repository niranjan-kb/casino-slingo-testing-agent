"""Spec 006 — DB-driven lobby + app_structure persona layer.

Replaces the magic-string _LOBBY_SCREEN_IDS / _TILE_ID_SUBSTRINGS literals
with rows in the screen-map DB (Constitution: SQLite is the runtime source
of truth). Adding a new lobby variant or tile rid is now a one-row seed,
not a code change.

Schema:
  - logical_screens.role TEXT  -- NULL by default; 'lobby' for lobby/category surfaces
  - NEW table lobby_tile_patterns(pattern PRIMARY KEY, app_context, fallback_kind, source, created_at)

DB API:
  - is_lobby_screen(screen_id) -> bool
  - get_lobby_tile_patterns(app_context='platform') -> List[str]
  - upsert_logical_screen_role(logical_id, role, canonical_name=None, description=None)
  - upsert_lobby_tile_pattern(pattern, fallback_kind=None, source='seed', app_context='platform')

Activity integration:
  - _autorecord_lobby_walk consults DB, not _LOBBY_SCREEN_IDS
  - extract_game_tiles accepts `tile_patterns` parameter (defaults to module constant
    for back-compat in pure-function tests)
"""
from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from observers.screen_identity import extract_game_tiles
from prompts.persona import soul_and_identity
from shared.screen_map_db import ScreenMapDB


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_db() -> ScreenMapDB:
    """A ScreenMapDB pointed at an empty file. Schema init runs in __init__."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield ScreenMapDB(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _tile(rid: str, text: str = "", desc: str = "") -> Dict[str, Any]:
    return {
        "resource-id": rid,
        "text": text,
        "content-desc": desc,
        "class": "android.view.ViewGroup",
        "bounds": "[0,0][100,100]",
        "clickable": True,
        "focusable": True,
        "scrollable": False,
    }


# ── Schema ──────────────────────────────────────────────────────────────────


class TestSchema:
    def test_logical_screens_has_role_column(self, fresh_db: ScreenMapDB) -> None:
        conn = fresh_db._get_conn()
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(logical_screens)").fetchall()}
        assert "role" in cols, f"logical_screens needs a role column; have {sorted(cols)}"

    def test_lobby_tile_patterns_table_exists(self, fresh_db: ScreenMapDB) -> None:
        conn = fresh_db._get_conn()
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(lobby_tile_patterns)").fetchall()}
        assert {"pattern", "app_context", "fallback_kind", "source"} <= cols, (
            f"lobby_tile_patterns missing required columns; have {sorted(cols)}"
        )


# ── Seeds ───────────────────────────────────────────────────────────────────


class TestDefaultSeeds:
    """A fresh DB must come pre-seeded with the legacy + spec-006 defaults
    so callers don't need to run a separate seed script."""

    @pytest.mark.parametrize("screen_id", [
        "home", "home_lobby", "casino_home", "casino_lobby",
        "lobby_home", "lobby_category", "casino_category",
        "all_games", "popular_games", "new_games",
    ])
    def test_lobby_screens_pre_seeded(self, fresh_db: ScreenMapDB, screen_id: str) -> None:
        assert fresh_db.is_lobby_screen(screen_id), (
            f"expected {screen_id!r} pre-seeded as a lobby screen"
        )

    def test_non_lobby_screen_is_not_lobby(self, fresh_db: ScreenMapDB) -> None:
        assert not fresh_db.is_lobby_screen("settings")
        assert not fresh_db.is_lobby_screen("nonsense_xyz")

    @pytest.mark.parametrize("pattern", [
        # Legacy.
        "game_tile", "lobby_tile", "casino_tile", "tile_card",
        # Spec 006: Fanatics' real tile rids from T052 frontier data.
        "casino_game_component_tile", "small_game_component",
        "game_component", "casino_game",
    ])
    def test_tile_patterns_pre_seeded(self, fresh_db: ScreenMapDB, pattern: str) -> None:
        patterns = fresh_db.get_lobby_tile_patterns()
        assert pattern in patterns, (
            f"expected {pattern!r} in pre-seeded tile patterns; got {patterns}"
        )


# ── DB rec #2: anchor logical_screens (destructive / account / daily_bonus) ─


class TestAnchorScreenSeeds:
    """Spec 006 added four more logical_screens entries beyond the lobby set —
    revealed by the operator walkthrough. These are anchors the agent will
    encounter but must treat specially:

      - debug_menu          (destructive — only on debug builds; NEVER enter)
      - quick_deposit_sheet (destructive — real-money bottom sheet; NEVER confirm)
      - profile             (account — legitimate nav target, read-only)
      - fancash_spins_daily (daily_bonus — bottom-nav reserved slot)
    """

    @pytest.mark.parametrize("logical_id, expected_role", [
        ("debug_menu",          "capability"),    # available, but only when explicitly invoked
        ("quick_deposit_sheet", "destructive"),
        ("profile",             "account"),
        ("fancash_spins_daily", "daily_bonus"),
    ])
    def test_anchor_seeded_with_correct_role(
        self, fresh_db: ScreenMapDB, logical_id: str, expected_role: str,
    ) -> None:
        assert fresh_db.get_logical_screen_role(logical_id) == expected_role

    def test_anchor_non_lobby_roles_are_not_lobbies(self, fresh_db: ScreenMapDB) -> None:
        """Sanity guard: roles other than 'lobby' must not bleed into the lobby set
        — otherwise lobby-walk auto-discovery would harvest tiles from
        Quick Deposit / Debug Menu surfaces."""
        assert not fresh_db.is_lobby_screen("debug_menu")
        assert not fresh_db.is_lobby_screen("quick_deposit_sheet")

    def test_get_logical_screen_role_unknown_returns_none(self, fresh_db: ScreenMapDB) -> None:
        assert fresh_db.get_logical_screen_role("never_heard_of_it") is None

    def test_get_logical_screen_role_lobby_seed(self, fresh_db: ScreenMapDB) -> None:
        """The existing lobby seeds should still report role='lobby' via the
        new accessor — proving is_lobby_screen and get_logical_screen_role
        agree on the same row."""
        assert fresh_db.get_logical_screen_role("home") == "lobby"


# ── DB API: writers ─────────────────────────────────────────────────────────


class TestWriters:
    def test_upsert_logical_screen_role_makes_it_a_lobby(self, fresh_db: ScreenMapDB) -> None:
        assert not fresh_db.is_lobby_screen("custom_lobby_xyz")
        fresh_db.upsert_logical_screen_role(
            "custom_lobby_xyz", role="lobby", canonical_name="Custom Lobby",
        )
        assert fresh_db.is_lobby_screen("custom_lobby_xyz")

    def test_upsert_logical_screen_role_can_clear(self, fresh_db: ScreenMapDB) -> None:
        """Setting role=None on an existing row removes it from the lobby set."""
        fresh_db.upsert_logical_screen_role("temp", role="lobby", canonical_name="Temp")
        assert fresh_db.is_lobby_screen("temp")
        fresh_db.upsert_logical_screen_role("temp", role=None, canonical_name="Temp")
        assert not fresh_db.is_lobby_screen("temp")

    def test_upsert_lobby_tile_pattern_added(self, fresh_db: ScreenMapDB) -> None:
        fresh_db.upsert_lobby_tile_pattern("brand_new_tile_id", fallback_kind="slots")
        assert "brand_new_tile_id" in fresh_db.get_lobby_tile_patterns()

    def test_upsert_lobby_tile_pattern_idempotent(self, fresh_db: ScreenMapDB) -> None:
        before = len(fresh_db.get_lobby_tile_patterns())
        fresh_db.upsert_lobby_tile_pattern("game_tile")  # already seeded
        fresh_db.upsert_lobby_tile_pattern("game_tile")
        after = len(fresh_db.get_lobby_tile_patterns())
        assert before == after, "re-upserting a seeded pattern must not duplicate"


# ── extract_game_tiles: pattern parameter ──────────────────────────────────


class TestExtractGameTilesAcceptsPatterns:
    """The pure function now takes its tile-pattern list as an arg so callers
    can feed DB-fetched patterns. Default arg preserves legacy behaviour."""

    def test_explicit_patterns_recognize_new_rid(self) -> None:
        elements = [
            _tile("com.fanatics.casino:id/casino_game_component_tile",
                  text="Fanatics Blackjack"),
        ]
        tiles = extract_game_tiles(
            elements,
            fallback_kind="blackjack",
            tile_patterns=("casino_game_component_tile",),
        )
        assert len(tiles) == 1, f"expected 1 tile, got {tiles}"

    def test_default_patterns_match_legacy_set(self) -> None:
        """No `tile_patterns` arg ⇒ falls back to module default (game_tile etc.)."""
        elements = [
            _tile("com.fanatics.casino:id/lobby_game_tile", text="Legacy Game"),
        ]
        tiles = extract_game_tiles(elements, fallback_kind="slots")
        assert len(tiles) == 1, f"default patterns should still match legacy rids: {tiles}"


# ── T006-03: slug-collision fix on generic rids ─────────────────────────


class TestSlugCollisionFix:
    """When every tile on the page shares one generic rid (Fanatics' case:
    `casino_game_component_tile`), rid.split('/')[-1] produces the same slug
    for all of them. Fix: when the slug-candidate is one of the known generic
    patterns, derive the slug from _slugify(display_name) instead."""

    def test_generic_rid_falls_back_to_display_slug(self) -> None:
        elements = [
            _tile("com.fanatics.casino:id/casino_game_component_tile",
                  text="Fanatics Blackjack"),
            _tile("com.fanatics.casino:id/casino_game_component_tile",
                  text="Wild Cherry Slots"),
            _tile("com.fanatics.casino:id/casino_game_component_tile",
                  text="Roulette Royale"),
        ]
        tiles = extract_game_tiles(
            elements,
            tile_patterns=("casino_game_component_tile",),
            fallback_kind="slots",
        )
        slugs = sorted(t["slug"] for t in tiles)
        assert len(tiles) == 3, (
            f"expected 3 tiles (one per distinct display), got {len(tiles)}: {tiles}"
        )
        assert slugs == ["fanatics-blackjack", "roulette-royale", "wild-cherry-slots"], (
            f"expected display-derived slugs, got {slugs}"
        )

    def test_specific_rid_tail_keeps_rid_slug(self) -> None:
        """Sanity guard: when the substring matches but the rid tail is more
        specific than the pattern, keep the rid-derived slug. Otherwise we'd
        rename seeded games on every observation pass."""
        elements = [
            # Pattern `game_tile` is a substring; tail `slingo_cash_eruption_game_tile`
            # is per-game specific → should NOT fall back to display slug.
            _tile("com.fanatics.casino:id/slingo_cash_eruption_game_tile",
                  text="Slingo Cash Eruption"),
        ]
        tiles = extract_game_tiles(
            elements,
            tile_patterns=("game_tile",),
            fallback_kind="slingo",
        )
        assert len(tiles) == 1
        assert tiles[0]["slug"] == "slingo_cash_eruption_game_tile", (
            f"specific rids should keep rid-derived slugs, got {tiles[0]['slug']!r}"
        )


# ── Persona layer: app_structure.md wired into soul_and_identity ──────


class TestAppStructurePersona:
    """The L0 cacheable prefix (soul + identity + app_structure) must include
    the new app-structure block so every turn sees Danny's mental map."""

    def test_persona_block_includes_app_structure_header(self) -> None:
        block = soul_and_identity()
        assert "App Structure" in block, (
            "soul_and_identity() must include the app_structure.md header"
        )

    def test_persona_block_includes_walkthrough_anchors(self) -> None:
        block = soul_and_identity()
        # Operator-confirmed terminology — these are gold and must survive
        # any future edit of app_structure.md.
        for term in (
            "Fanatics Spin to Win",       # the always-reserved bottom-nav slot
            "Cat Nav",                     # the top category navbar
            "Casino Search",               # the lobby search widget
            "sushi menu",                  # game-tile action menu
            "Quick Deposit",               # destructive bottom sheet
            "Playmaker",                   # CMS that drives lobby composition
        ):
            assert term in block, f"app_structure missing operator-gold term {term!r}"

    def test_persona_block_includes_safety_rules(self) -> None:
        block = soul_and_identity()
        # Cross-cutting nav-safety rules that the navigate intents inherit.
        assert "Back-to-home" in block or "back-to-home" in block.lower(), (
            "app_structure must include the back-to-home recovery anchor"
        )
        assert "NEVER" in block and "Deposit" in block, (
            "app_structure must include the deposit/destructive-avoidance rule"
        )


# ── Activity integration ──────────────────────────────────────────────────


class TestAutorecordLobbyWalkUsesDB:
    def test_home_screen_triggers_upsert_via_db(self) -> None:
        from activities import observer_activity as oa

        spy = MagicMock()
        spy.is_lobby_screen.return_value = True
        spy.get_lobby_tile_patterns.return_value = ["casino_game_component_tile"]
        spy.upsert_game_directory = MagicMock()
        oa.set_screen_db(spy)

        parsed = [
            _tile("com.fanatics.casino:id/casino_game_component_tile",
                  text="Fanatics Blackjack"),
        ]
        try:
            oa._autorecord_lobby_walk(screen_id="home", parsed_elements=parsed)
        finally:
            oa.set_screen_db(None)

        spy.is_lobby_screen.assert_called_once_with("home")
        assert spy.upsert_game_directory.called, (
            "DB said 'home' is a lobby — upsert_game_directory should fire"
        )

    def test_non_lobby_screen_via_db_does_not_upsert(self) -> None:
        from activities import observer_activity as oa

        spy = MagicMock()
        spy.is_lobby_screen.return_value = False
        spy.upsert_game_directory = MagicMock()
        oa.set_screen_db(spy)

        parsed = [
            _tile("com.fanatics.casino:id/casino_game_component_tile",
                  text="Fanatics Blackjack"),
        ]
        try:
            oa._autorecord_lobby_walk(screen_id="settings", parsed_elements=parsed)
        finally:
            oa.set_screen_db(None)

        assert not spy.upsert_game_directory.called

    def test_extract_uses_db_patterns_when_screen_is_lobby(self) -> None:
        """When DB says 'home' is a lobby, the activity should feed DB tile-patterns
        into extract_game_tiles — otherwise the spec-006 rids would be missed."""
        from activities import observer_activity as oa

        spy = MagicMock()
        spy.is_lobby_screen.return_value = True
        spy.get_lobby_tile_patterns.return_value = [
            "casino_game_component_tile", "small_game_component",
        ]
        spy.upsert_game_directory = MagicMock()
        oa.set_screen_db(spy)

        parsed = [
            _tile("com.fanatics.casino:id/small_game_component",
                  text="Wild Cherry Slots"),
        ]
        try:
            oa._autorecord_lobby_walk(screen_id="home", parsed_elements=parsed)
        finally:
            oa.set_screen_db(None)

        spy.get_lobby_tile_patterns.assert_called()
        assert spy.upsert_game_directory.called, (
            "DB-supplied tile pattern should have matched the small_game_component rid"
        )
