"""Contract test (Spec 005 T048): ParseSessionIntent output validates against
session_intent.schema.json.

The parser emits a private `_meta` field for audit reporting (env cap vs
requested vs effective loss); per the schema it MUST be stripped before
validating against the wire contract. The fixtures below cover every
flow, every kind, the budget cap behaviour, and the terminal selector.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

import jsonschema
import pytest

from tools.casino_qa.parse_session_intent import parse_session_intent


_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "specs", "005-casino-game-play-suite", "contracts",
    "session_intent.schema.json",
)


@pytest.fixture(scope="module")
def schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def _strip_meta(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the parser's _meta audit field — it is not part of the wire contract."""
    return {k: v for k, v in envelope.items() if k != "_meta"}


# Each row: (prompt, env_cap, expected_flow, expected_kind, expected_terminal)
# `None` means "do not assert this dimension".
PROMPT_CASES = [
    # vague + no kind ⇒ play / kind absent / budget_exhausted
    ("play",                          10.0, "play",     None,        "budget_exhausted"),
    # explicit slingo with default budget
    ("play any slingo game",          10.0, "play",     "slingo",    "budget_exhausted"),
    # spin-to-win (slots)
    ("play fanatics spin to win",     10.0, "play",     "slots",     "budget_exhausted"),
    # "live blackjack" beats "blackjack" because keyword match is longest
    ("play live blackjack",           10.0, "play",     "live_dealer", "budget_exhausted"),
    # spins terminal selected from explicit numeric bound
    ("play slingo for 5 spins",       10.0, "play",     "slingo",    "n_spins"),
    # minutes terminal
    ("play roulette for 10 minutes",  10.0, "play",     "roulette",  "max_minutes"),
    # audit flow — no betting, terminal=report
    ("look around the casino lobby",  10.0, "audit",    None,        "report"),
    # observe one game — terminal=report (no betting)
    ("watch fanatics blackjack",      10.0, "observe",  "blackjack", "report"),
    # report-only
    ("summarise yesterday's session", 10.0, "report_only", None,     "report"),
    # navigate — keyword "go to"
    ("go to fanatics blackjack",      10.0, "navigate", "blackjack", "budget_exhausted"),
    # empty prompt → report_only / report
    ("",                              10.0, "report_only", None,     "report"),
]


@pytest.mark.parametrize("prompt,env_cap,want_flow,want_kind,want_term", PROMPT_CASES)
def test_session_intent_validates_against_schema(
    schema: Dict[str, Any],
    prompt: str,
    env_cap: float,
    want_flow: str,
    want_kind: str,
    want_term: str,
) -> None:
    envelope = parse_session_intent({"prompt": prompt, "env_max_loss_usd": env_cap})
    payload = _strip_meta(envelope)

    # 1. Schema validation — the wire shape must match the contract.
    jsonschema.validate(payload, schema)

    # 2. Behavioural assertions per the case.
    assert payload["flow"] == want_flow, payload
    assert payload["terminal"] == want_term, payload
    if want_kind is None:
        assert "target" not in payload or "kind" not in payload.get("target", {})
    else:
        assert payload.get("target", {}).get("kind") == want_kind, payload


def test_loss_budget_silently_capped_to_env(schema: Dict[str, Any]) -> None:
    """Operator asked for $50, env cap is $10 → budget.max_loss_usd = 10."""
    envelope = parse_session_intent({
        "prompt": "play slingo until I lose $50",
        "env_max_loss_usd": 10.0,
    })
    jsonschema.validate(_strip_meta(envelope), schema)
    assert envelope["budget"]["max_loss_usd"] == 10.0
    assert envelope["_meta"]["requested_max_loss_usd"] == 50.0
    assert envelope["_meta"]["effective_max_loss_usd"] == 10.0


def test_loss_budget_lower_than_env_preserved(schema: Dict[str, Any]) -> None:
    """Operator asked for $1, env cap is $10 → budget.max_loss_usd = 1."""
    envelope = parse_session_intent({
        "prompt": "play slingo until I lose $1",
        "env_max_loss_usd": 10.0,
    })
    jsonschema.validate(_strip_meta(envelope), schema)
    assert envelope["budget"]["max_loss_usd"] == 1.0


def test_default_bounds_attached_to_play(schema: Dict[str, Any]) -> None:
    """Vague play prompts get default max_spins=20 AND max_minutes=10 (FR-004)."""
    envelope = parse_session_intent({"prompt": "play slingo", "env_max_loss_usd": 10.0})
    payload = _strip_meta(envelope)
    jsonschema.validate(payload, schema)
    assert payload["budget"]["max_spins"] >= 1
    assert payload["budget"]["max_minutes"] >= 1
