"""Spec 006 Path A: plan-graph reachability — `any_terminal` + recovery re-entry.

Two real bugs surfaced during T052 reruns:

1. `requires: any_terminal` (used by the `report` node) was treated as a literal
   node name. Since `any_terminal` is not a node, the predicate could never be
   satisfied → `intent_report` was unreachable from any state.

2. Mid-flow re-auth (operator: "the agent should just log back in") was
   architecturally supported by the YAML's `recovery.reauth` declaration but
   the workflow didn't recognize it. The reachability function now exposes
   `recovery_reentry` in its reason so callers can distinguish first-time
   completion from a recovery re-entry pass.

These tests exercise the new logic in isolation. The activity calls into
`is_intent_reachable` as a pure function (no Temporal harness needed because
it's stateless and reads only the module-level plan graph).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from activities.intent_activity import is_intent_reachable
from activities import intent_activity as ia


_CASINO_GRAPH: Dict[str, Any] = {
    "nodes": {
        "parse_session":    {"intent": "intent_parse_session"},
        "authenticate":     {"intent": "intent_authenticate",     "requires": "parse_session.success"},
        "navigate_to_game": {"intent": "intent_navigate_to_game", "requires": "authenticate.success"},
        "play_game":        {"intent": "intent_play_game",         "requires": "navigate_to_game.success"},
        "report":           {"intent": "intent_report",            "requires": "any_terminal"},
    },
    "recovery": {
        "reauth": {"intent": "intent_authenticate", "trigger": "session_lost"},
        "evidence": {"intent": "intent_report", "trigger": "panic"},
    },
}


@pytest.fixture(autouse=True)
def _stub_graph(monkeypatch):
    """Install the casino plan graph as the active one for these tests."""
    monkeypatch.setattr(ia, "get_plan_graph", lambda: _CASINO_GRAPH)
    yield


def _call(active_intent: str, completed: List[str]) -> Dict[str, Any]:
    """Run the reachability activity as a sync helper for parametrize."""
    return asyncio.run(is_intent_reachable({
        "active_intent": active_intent,
        "completed_nodes": completed,
        "current_node": None,
    }))


# ── `any_terminal` semantics ────────────────────────────────────────────


class TestAnyTerminalPredicate:
    def test_unreachable_when_nothing_completed(self) -> None:
        """`any_terminal` with empty completed_nodes ⇒ no terminal has fired yet."""
        result = _call("intent_report", completed=[])
        # NOTE: entry-path tolerance does NOT apply to `report` because its
        # requires chain (`any_terminal`) doesn't terminate in a no-requires
        # node. The empty-completed case correctly stays unreachable.
        assert result["reachable"] is False
        assert "any_terminal" in result["reason"]

    @pytest.mark.parametrize("completed", [
        ["parse_session"],
        ["parse_session", "authenticate"],
        ["parse_session", "authenticate", "navigate_to_game"],
        ["parse_session", "authenticate", "navigate_to_game", "play_game"],
    ])
    def test_reachable_as_soon_as_any_node_completes(self, completed: List[str]) -> None:
        """`report` is reachable from ANY non-empty completion state."""
        result = _call("intent_report", completed=completed)
        assert result["reachable"] is True, (
            f"intent_report should be reachable with completed={completed}, "
            f"got {result}"
        )
        assert result["reason"] == "any_terminal_satisfied"


# ── Recovery re-entry (re-auth mid-flow) ────────────────────────────────


class TestRecoveryReentry:
    """The agent must be able to re-enter `intent_authenticate` mid-flow when
    page-source shows the login screen (declared via `recovery.reauth`)."""

    def test_reauth_allowed_after_authenticate_already_completed(self) -> None:
        """Operator's exact request: 'the agent should log back in if it sees
        the login screen during navigate_to_game'."""
        result = _call(
            "intent_authenticate",
            completed=["parse_session", "authenticate", "navigate_to_game"],
        )
        assert result["reachable"] is True
        # The reason field signals this is a recovery re-entry, not a fresh
        # first-time completion — useful for downstream telemetry.
        assert "recovery_reentry" in result["reason"]

    def test_reauth_allowed_immediately_after_parse_session(self) -> None:
        """First-time auth still works — must not regress."""
        result = _call(
            "intent_authenticate",
            completed=["parse_session"],
        )
        assert result["reachable"] is True
        assert "precondition_met" in result["reason"]

    def test_non_recovery_intent_not_marked_as_reentry(self) -> None:
        """`intent_play_game` is NOT a recovery route — its reason should
        not mention recovery_reentry even if re-emitted."""
        result = _call(
            "intent_play_game",
            completed=["parse_session", "authenticate", "navigate_to_game", "play_game"],
        )
        assert result["reachable"] is True
        assert "recovery_reentry" not in result["reason"]


# ── Regression on the linear flow ───────────────────────────────────────


class TestLinearFlowStillWorks:
    """Sanity guard: the existing forward-progression behaviour is unchanged."""

    @pytest.mark.parametrize("intent, completed, expected_reachable", [
        ("intent_parse_session",     [],                           True),   # entry path
        ("intent_authenticate",      ["parse_session"],            True),
        ("intent_navigate_to_game",  ["parse_session", "authenticate"], True),
        ("intent_play_game",         ["parse_session", "authenticate"], False),  # missing navigate_to_game
        ("intent_play_game",         ["parse_session", "authenticate", "navigate_to_game"], True),
    ])
    def test_linear_progression(
        self, intent: str, completed: List[str], expected_reachable: bool,
    ) -> None:
        result = _call(intent, completed=completed)
        assert result["reachable"] is expected_reachable, (
            f"{intent} with completed={completed}: got {result}"
        )
