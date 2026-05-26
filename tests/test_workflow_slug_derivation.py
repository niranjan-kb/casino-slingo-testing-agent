"""Spec 006 T301 — page-source slug derivation heuristic.

Live test 2026-05-21 surfaced that the v1 heuristic (longest text matching the
kind hint) picked up an in-game banner ("PLAYER HAS BLACKJACK, DEALER HAS ACE
FACE UP") rather than the game title ("Sweet 16 Blackjack"). v2 filters out
ALL-CAPS phrases, sentence punctuation, and out-of-range token counts so
game-state banners no longer outrank game titles.

These tests pin the heuristic against the real-world failure case + a small
set of synthetic adversarial inputs. They are pure-function tests over the
workflow method — no Temporal harness required because tool_results is a
plain list mutable in-place.
"""
from __future__ import annotations

import pytest

from workflows.agent_goal_workflow import AgentGoalWorkflow


def _make_wf_with_page_source(text_attrs: list[str]) -> AgentGoalWorkflow:
    """Build a workflow with one synthetic appium_get_page_source tool_result.

    The page_source string is shaped like real Appium dumps: a length-padded
    leader (so the >100-char guard in _latest_page_source_text accepts it) plus
    `<TextView text="..." />` elements for each entry in `text_attrs`.
    """
    leader = "Page source retrieved successfully: " + ("x" * 200)
    body = "".join(f'<TextView text="{t}" />' for t in text_attrs)
    wf = AgentGoalWorkflow()
    wf.tool_results.append({"tool": "appium_get_page_source", "content": [leader + body]})
    return wf


def test_picks_title_case_game_name_over_all_caps_banner() -> None:
    """The 2026-05-21 live failure: banner outranked the title under v1."""
    wf = _make_wf_with_page_source([
        "PLAYER HAS BLACKJACK, DEALER HAS ACE FACE UP",  # status banner, ALL-CAPS + comma
        "Sweet 16 Blackjack",                            # the actual game title
        "Hit",
        "Stand",
    ])
    result = wf._derive_slug_from_recent_page_source(kind_hint="blackjack")
    assert result == ("sweet-16-blackjack", "Sweet 16 Blackjack")


def test_picks_isolated_title_case_game_name() -> None:
    wf = _make_wf_with_page_source(["Sweet 16 Blackjack"])
    assert wf._derive_slug_from_recent_page_source("blackjack") == (
        "sweet-16-blackjack", "Sweet 16 Blackjack",
    )


def test_rejects_bare_kind_word() -> None:
    """Just 'Blackjack' is a button label or category pill — not a title."""
    wf = _make_wf_with_page_source(["Blackjack"])
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


def test_accepts_all_caps_game_title() -> None:
    """Fanatics WebView emits game titles in ALL CAPS in production
    (live 2026-05-22: text="SWEET 16 BLACKJACK"). Pre-v3 versions filtered
    these out; v3 relies on token-count + kind-at-tail to discriminate
    titles from banners instead.
    """
    wf = _make_wf_with_page_source(["SWEET 16 BLACKJACK"])
    assert wf._derive_slug_from_recent_page_source("blackjack") == (
        "sweet-16-blackjack", "SWEET 16 BLACKJACK",
    )


def test_rejects_marketing_text_with_kind_buried_in_middle() -> None:
    """Marketing/banner text like 'WIN A BLACKJACK BONUS' buries the kind
    word away from the title tail; v3 rejects by kind-not-in-last-2-tokens."""
    wf = _make_wf_with_page_source(["WIN A BLACKJACK BONUS"])
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


def test_rejects_instruction_text_with_kind_in_middle() -> None:
    wf = _make_wf_with_page_source(["PLAY BLACKJACK NOW"])
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


def test_rejects_sentence_with_punctuation() -> None:
    wf = _make_wf_with_page_source(["This is a Blackjack game, with side bets"])
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


def test_rejects_out_of_range_token_count() -> None:
    """6+ tokens are usually marketing sentences, not titles."""
    wf = _make_wf_with_page_source(["Play Sweet 16 Blackjack Now For Free"])
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


def test_returns_none_when_kind_hint_missing() -> None:
    wf = _make_wf_with_page_source(["Sweet 16 Blackjack"])
    assert wf._derive_slug_from_recent_page_source(None) is None


def test_returns_none_when_no_page_source_in_tool_results() -> None:
    wf = AgentGoalWorkflow()
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


def test_returns_none_when_no_text_matches_kind() -> None:
    wf = _make_wf_with_page_source(["Lightning Roulette", "Place Your Bets"])
    assert wf._derive_slug_from_recent_page_source("blackjack") is None


@pytest.mark.parametrize("title,expected_slug", [
    ("Sweet 16 Blackjack",   "sweet-16-blackjack"),
    ("Fanatics Blackjack",   "fanatics-blackjack"),
    ("Blackjack MH",         "blackjack-mh"),
    ("Single Hand Blackjack", "single-hand-blackjack"),
])
def test_slugifies_known_blackjack_titles(title: str, expected_slug: str) -> None:
    wf = _make_wf_with_page_source([title])
    assert wf._derive_slug_from_recent_page_source("blackjack") == (expected_slug, title)


def test_strips_provider_prefix_from_webview_title() -> None:
    """Fanatics WebView titles for HTML5 games carry a platform/vendor tag
    in front of the real title, separated by ' - '. Live 2026-05-22:
    text=\"LnW Spark - SWEET 16 BLACKJACK\" (Light & Wonder's HTML5
    platform). The slug should be derived from the title proper, not
    from the prefix-laden raw string.
    """
    wf = _make_wf_with_page_source(["LnW Spark - SWEET 16 BLACKJACK"])
    assert wf._derive_slug_from_recent_page_source("blackjack") == (
        "sweet-16-blackjack", "SWEET 16 BLACKJACK",
    )


def test_strips_provider_prefix_html_encoded() -> None:
    """Same as above but with HTML-encoded delimiters (the actual live form
    inside a WebView)."""
    leader = "Page source retrieved successfully: " + ("x" * 200)
    page_source = (
        leader
        + '<view text=&quot;LnW Spark - SWEET 16 BLACKJACK&quot; />'
    )
    from workflows.agent_goal_workflow import AgentGoalWorkflow
    wf = AgentGoalWorkflow()
    wf.tool_results.append({"tool": "appium_get_page_source", "content": [page_source]})
    assert wf._derive_slug_from_recent_page_source("blackjack") == (
        "sweet-16-blackjack", "SWEET 16 BLACKJACK",
    )


def test_html_encoded_webview_title_extracted() -> None:
    """Fanatics casino games render inside an Android WebView, and the
    page-source serializer emits WebView elements with HTML-encoded
    attribute delimiters (`text=&quot;...&quot;`). v4 regex captures
    both literal and encoded forms. Live 2026-05-22: SWEET 16 BLACKJACK
    was inside the WebView; the auto-seed fell back to skip until the
    regex covered this form.
    """
    page_source = (
        "Page source retrieved successfully: " + ("x" * 200)
        + '<android.widget.TextView text="Lobby Title" />'
        + '<webview><android.view.View text=&quot;SWEET 16 BLACKJACK&quot; /></webview>'
    )
    from workflows.agent_goal_workflow import AgentGoalWorkflow
    wf = AgentGoalWorkflow()
    wf.tool_results.append({"tool": "appium_get_page_source", "content": [page_source]})
    assert wf._derive_slug_from_recent_page_source("blackjack") == (
        "sweet-16-blackjack", "SWEET 16 BLACKJACK",
    )
