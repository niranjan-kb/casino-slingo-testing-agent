"""Contract test (Spec 005 T049): the active_intent field on plan_next_action
is constrained to the closed-set intent enum.

Two layers of assertion:
1. Every intent the registry exposes must be in plan_next_action.schema.json's
   `active_intent` enum — no registry drift, no foreign intents.
2. Sample planner outputs (one per registered intent) round-trip through
   jsonschema.validate without complaint, plus a deliberate counter-example
   (`intent_drift_test`) is REJECTED.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import jsonschema
import pytest

from intents import load_registry


_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "specs", "005-casino-game-play-suite", "contracts",
    "plan_next_action.schema.json",
)


@pytest.fixture(scope="module")
def schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def schema_intent_enum(schema: Dict[str, Any]) -> List[str]:
    return list(schema["properties"]["active_intent"]["enum"])


@pytest.fixture(scope="module")
def registered_intent_ids() -> List[str]:
    return sorted(load_registry().keys())


def test_every_registered_intent_is_in_schema_enum(
    schema_intent_enum: List[str],
    registered_intent_ids: List[str],
) -> None:
    """No registry drift: every loaded intent must be a known enum value."""
    missing = [i for i in registered_intent_ids if i not in schema_intent_enum]
    assert not missing, (
        f"Registry has intents not in plan_next_action schema enum: {missing}. "
        f"Schema enum: {schema_intent_enum}"
    )


# ── Spec 006 T106: closed-set guard at exactly 6 intents ──────────────────


_CANONICAL_SIX = {
    "intent_parse_session",
    "intent_authenticate",
    "intent_navigate_to_screen",
    "intent_navigate_to_game",
    "intent_play_game",
    "intent_report",
}


def test_registry_has_exactly_six_canonical_intents(
    registered_intent_ids: List[str],
) -> None:
    """Spec 006 US-03 AC: the closed-set is exactly these 6 intents.

    Adding a new intent file in `intents/` requires updating this canonical set
    deliberately (the change is small but the planner-prompt budget is tight, so
    we want a visible test-edit on growth).
    """
    actual = set(registered_intent_ids)
    extras = actual - _CANONICAL_SIX
    missing = _CANONICAL_SIX - actual
    assert not extras and not missing, (
        f"Registry diverged from the canonical 6. "
        f"extras={sorted(extras)}, missing={sorted(missing)}"
    )


def test_schema_enum_has_exactly_six_entries(
    schema_intent_enum: List[str],
) -> None:
    """The schema enum must match the canonical 6 (planner cannot emit anything else)."""
    actual = set(schema_intent_enum)
    extras = actual - _CANONICAL_SIX
    missing = _CANONICAL_SIX - actual
    assert not extras and not missing, (
        f"plan_next_action.schema.json active_intent enum diverged from the canonical 6. "
        f"extras={sorted(extras)}, missing={sorted(missing)}"
    )


def test_schema_enum_only_contains_known_shape(
    schema_intent_enum: List[str],
) -> None:
    """Defensive: every enum value matches the `intent_<word>` shape."""
    bad = [v for v in schema_intent_enum if not v.startswith("intent_")]
    assert not bad, f"non-conforming enum values: {bad}"


def _planner_emission(intent_id: str, *, next_: str = "confirm", tool: str = "WaitSeconds") -> Dict[str, Any]:
    return {
        "next": next_,
        "tool": tool,
        "args": {"seconds": 3},
        "response": "Stub rationale.",
        "active_intent": intent_id,
    }


def test_sample_emissions_validate_for_every_registered_intent(
    schema: Dict[str, Any],
    registered_intent_ids: List[str],
) -> None:
    """A planner emission for each loaded intent must validate."""
    for intent_id in registered_intent_ids:
        payload = _planner_emission(intent_id)
        jsonschema.validate(payload, schema)


def test_unknown_intent_id_is_rejected(schema: Dict[str, Any]) -> None:
    """Drift-detection: a fabricated intent_id must fail validation."""
    payload = _planner_emission("intent_drift_test")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_done_emission_without_tool_validates(schema: Dict[str, Any]) -> None:
    """next=done is the session terminator; tool/args may be omitted."""
    payload = {
        "next": "done",
        "response": "All intents complete.",
        "active_intent": "intent_report",
    }
    jsonschema.validate(payload, schema)


def test_next_outside_closed_set_is_rejected(schema: Dict[str, Any]) -> None:
    """next ∈ {confirm, question, pick-new-goal, done} only."""
    payload = _planner_emission("intent_authenticate", next_="restart")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)
