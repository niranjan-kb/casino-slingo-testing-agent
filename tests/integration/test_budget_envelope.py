"""Integration test (Spec 005 T050 / FR-005): the env stop-loss is a HARD ceiling.

A prompt-supplied `max_loss_usd > env_ceiling` is silently capped to the env
value at parse time, then clamped again by `lower_budget()` if the workflow
re-applies it. The downstream run report must surface BOTH the requested
and the effective value so an auditor can see the cap math.

The test exercises the full pipeline:
    prompt → ParseSessionIntent → lower_budget → CheckBudget → run_report
without spinning up Temporal — `parse_session_intent` and `lower_budget` are
pure functions, and `generate_report` writes JSON to a tmp dir.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict

import pytest

from shared.runtime_facts import (
    BudgetConstraints,
    DeviceFacts,
    RuntimeFacts,
    TargetFacts,
    lower_budget,
)
from tools.casino_qa.check_budget import check_budget
from tools.casino_qa.parse_session_intent import parse_session_intent


def _facts_with_cap(env_cap: float) -> RuntimeFacts:
    """Build a RuntimeFacts with the given env cap, no env-var dependence."""
    return RuntimeFacts(
        session_id="test_session",
        platform="android",
        build_env="cert",
        device=DeviceFacts(
            platform="android", profile="android-1080x1920",
            resolution="1080x1920", dpi=420, locale="en-US", currency="USD",
        ),
        target=TargetFacts(
            app_id="com.betfanatics.casino.cert",
            build_env="cert", app_version="1.0.0",
        ),
        constraints=BudgetConstraints(
            max_loss_usd=env_cap, max_spins=20, max_minutes=10,
            write_allowed=True,
        ),
        jurisdiction="NJ",
    )


# ── ParseSessionIntent layer ──


def test_parse_silently_caps_excess_loss_to_env() -> None:
    """`lose $50` against env_cap=10 → effective_max_loss_usd == 10."""
    envelope = parse_session_intent({
        "prompt": "play slingo until I lose $50",
        "env_max_loss_usd": 10.0,
    })
    assert envelope["budget"]["max_loss_usd"] == 10.0, envelope
    assert envelope["_meta"]["requested_max_loss_usd"] == 50.0
    assert envelope["_meta"]["effective_max_loss_usd"] == 10.0


def test_parse_preserves_loss_below_env() -> None:
    """`lose $1` against env_cap=10 → effective_max_loss_usd == 1."""
    envelope = parse_session_intent({
        "prompt": "play slingo until I lose $1",
        "env_max_loss_usd": 10.0,
    })
    assert envelope["budget"]["max_loss_usd"] == 1.0
    assert envelope["_meta"]["requested_max_loss_usd"] == 1.0
    assert envelope["_meta"]["effective_max_loss_usd"] == 1.0


def test_parse_no_loss_specified_uses_env_cap() -> None:
    """A vague play prompt inherits the env cap as its budget."""
    envelope = parse_session_intent({
        "prompt": "play slingo",
        "env_max_loss_usd": 10.0,
    })
    assert envelope["budget"]["max_loss_usd"] == 10.0


# ── lower_budget layer (post-parse, applied by workflow) ──


def test_lower_budget_silently_caps() -> None:
    """`lower_budget(.., max_loss_usd=50)` against env_cap=10 → caps to 10."""
    facts = _facts_with_cap(10.0)
    capped = lower_budget(facts, max_loss_usd=50.0, max_spins=999, max_minutes=999)
    # All three bounds must be silently clamped to existing limits.
    assert capped.constraints.max_loss_usd == 10.0
    assert capped.constraints.max_spins == 20
    assert capped.constraints.max_minutes == 10


def test_lower_budget_does_lower_when_stricter() -> None:
    """A stricter prompt-side request DOES take effect."""
    facts = _facts_with_cap(10.0)
    tighter = lower_budget(facts, max_loss_usd=2.0, max_spins=5, max_minutes=3)
    assert tighter.constraints.max_loss_usd == 2.0
    assert tighter.constraints.max_spins == 5
    assert tighter.constraints.max_minutes == 3


def test_lower_budget_returns_new_frozen_instance() -> None:
    """RuntimeFacts is frozen; lower_budget returns a fresh instance."""
    facts = _facts_with_cap(10.0)
    other = lower_budget(facts, max_loss_usd=2.0)
    assert other is not facts
    assert facts.constraints.max_loss_usd == 10.0  # original unchanged


# ── CheckBudget terminal selection ──


def test_check_budget_fires_on_exact_loss() -> None:
    """Crossing the loss line triggers `budget_exhausted` at exactly -max_loss."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    decision = check_budget({
        "balance_now": 90.0,
        "balance_session_start": 100.0,
        "spins_played": 1,
        "session_started_at_iso": now,
        "now_iso": now,
        "max_loss_usd": 10.0,
        "max_spins": 20,
        "max_minutes": 10,
    })
    assert decision.get("terminal") == "budget_exhausted", decision
    assert decision.get("should_continue") is False, decision


def test_check_budget_does_not_fire_below_threshold() -> None:
    """A loss below the cap leaves the play loop running."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    decision = check_budget({
        "balance_now": 95.0,
        "balance_session_start": 100.0,
        "spins_played": 1,
        "session_started_at_iso": now,
        "now_iso": now,
        "max_loss_usd": 10.0,
        "max_spins": 20,
        "max_minutes": 10,
    })
    assert decision.get("terminal") is None, decision
    assert decision.get("should_continue") is True, decision


# ── End-to-end audit: report records BOTH requested + effective ──


def test_report_records_requested_and_effective_loss(tmp_path: pytest.TempPathFactory) -> None:
    """The run report's balance block must show both numbers (FR-005 audit trail)."""
    from tools.casino_qa.generate_report import _gather_run_report  # internal helper

    # Pretend the operator asked for $50, env clamped to $10.
    envelope = parse_session_intent({
        "prompt": "play slingo until I lose $50",
        "env_max_loss_usd": 10.0,
    })
    requested = envelope["_meta"]["requested_max_loss_usd"]
    effective = envelope["_meta"]["effective_max_loss_usd"]

    payload = _gather_run_report({
        "workflow_id": "wf_budget_test",
        "session_intent": {k: v for k, v in envelope.items() if k != "_meta"},
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at":   "2026-01-01T00:05:00Z",
        "terminal_reason": "budget_exhausted",
        "balance": {
            "start": 100.0, "end": 90.0, "delta": -10.0,
            "max_loss_requested": requested,
            "max_loss_effective": effective,
        },
        "intents": [],
    })
    assert payload["balance"]["max_loss_requested"] == 50.0, payload["balance"]
    assert payload["balance"]["max_loss_effective"] == 10.0, payload["balance"]
    # Validate against the run-report schema. The schema $refs
    # session_intent.schema.json — load both into a referencing.Registry
    # so the validator can resolve the cross-file reference.
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    contracts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "specs", "005-casino-game-play-suite", "contracts",
    )
    with open(os.path.join(contracts_dir, "run_report.schema.json")) as f:
        run_report_schema = json.load(f)
    with open(os.path.join(contracts_dir, "session_intent.schema.json")) as f:
        session_intent_schema = json.load(f)
    registry = Registry().with_resource(
        "session_intent.schema.json",
        Resource.from_contents(session_intent_schema, default_specification=DRAFT202012),
    )
    jsonschema.Draft202012Validator(run_report_schema, registry=registry).validate(payload)
