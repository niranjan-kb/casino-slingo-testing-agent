"""Temporal activities for the intent layer (specs/004-nav-graph-intents).

Activities that need non-deterministic ops (DB reads, env lookups, registry
inspection) live here so the workflow can call them and have their results
become part of workflow history (replay-safe per WF-1).

The intent registry itself is loaded at module import time in
workflows/agent_goal_workflow.py — that pattern is replay-safe because
imports are frozen at worker startup. These activities provide DB-backed
helpers that DO need to be activities.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from temporalio import activity

log = logging.getLogger(__name__)

_screen_db: Any = None


def set_screen_db(db: Any) -> None:
    """Worker-startup injection — same pattern as observer_activity."""
    global _screen_db
    _screen_db = db


def get_screen_db() -> Any:
    return _screen_db


# ── Activities ──────────────────────────────────────────────────────────


@activity.defn
async def list_intent_registry_summary() -> List[Dict[str, Any]]:
    """Return a JSON-serializable summary of the loaded intent registry.

    Used by /api endpoints and the React UI to render the registry. Imported
    lazily so the activity is callable from any worker without forcing the
    intents package to load at activity-module import time (avoids replay
    coupling for workers that don't run the casino workflow).
    """
    try:
        from intents import load_registry  # local import: no replay coupling

        registry = load_registry()
    except Exception as e:  # noqa: BLE001
        activity.logger.warning(f"intent registry load failed: {e}")
        return []

    summary: List[Dict[str, Any]] = []
    for intent_id, decl in sorted(registry.items()):
        d = asdict(decl)
        # Drop the body_md from the summary — clients can fetch it on demand.
        d.pop("body_md", None)
        summary.append(d)
    return summary


@activity.defn
async def find_games_for_intent(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Look up games in the catalog for `intent_navigate_to_screen` / `intent_play_game`.

    Payload keys:
        slug:         exact-match (preferred when the user named a specific game)
        category:     filter (e.g. "slingo" / "slots")
        name_like:    substring match (case-insensitive via SQL LIKE)
        limit:        max rows, default 10
    """
    db = get_screen_db()
    if db is None:
        activity.logger.warning("find_games_for_intent: screen_db not set on this worker")
        return []
    try:
        return db.find_games(
            slug=payload.get("slug"),
            category=payload.get("category"),
            name_like=payload.get("name_like"),
            limit=int(payload.get("limit", 10)),
        )
    except Exception as e:  # noqa: BLE001
        activity.logger.warning(f"find_games_for_intent failed: {e}")
        return []


@activity.defn
async def get_play_loop(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetch a game's `play_loop_json` strategy. Returns None when unset.

    Per R3, per-game play strategies are data not code. `intent_play_game`
    reads this to drive a generic spin/decision loop.
    """
    slug = payload.get("slug")
    if not slug:
        return None
    db = get_screen_db()
    if db is None:
        return None
    try:
        rows = db.find_games(slug=slug, limit=1)
    except Exception as e:  # noqa: BLE001
        activity.logger.warning(f"get_play_loop find_games failed: {e}")
        return None
    if not rows:
        return None
    raw = rows[0].get("play_loop_json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        activity.logger.warning(f"get_play_loop: play_loop_json parse failed: {e}")
        return None


# ── Spec 005: Plan-graph guard + RuntimeFacts + intent transitions ──────
#
# Per spec 005 plan §"Phase 2 Foundational" T016. WF-3 keeps this in a NEW
# activity file (NOT tool_activities.py / mcp_client_manager.py).
#
# The plan-graph guard rejects an active_intent that is not reachable from
# the current node per graphs/casino_session.yaml (research §R3). The
# RuntimeFacts loader fuses env + select_device into a JSON envelope for
# the L3 prompt layer (FR-035 replay-safe: result captured in workflow
# history, never re-derived on replay).


_plan_graph: Optional[Dict[str, Any]] = None


def set_plan_graph(graph: Dict[str, Any]) -> None:
    """Worker-startup injection of the parsed graphs/casino_session.yaml."""
    global _plan_graph
    _plan_graph = graph


def get_plan_graph() -> Optional[Dict[str, Any]]:
    return _plan_graph


@activity.defn
async def load_runtime_facts_activity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build RuntimeFacts from env + (optionally) a select_device MCP result.

    Payload:
        session_id:                 workflow id (required)
        select_device_result:       optional dict from a prior select_device call

    Returns the full RuntimeFacts as a JSON-serialisable dict; the workflow
    stores it as state and threads it into prompt assembly (L3) and BudgetCheck.

    Captured in workflow history so replay reads the same facts deterministically.
    """
    from shared.runtime_facts import load_runtime_facts  # local import: avoids replay coupling

    try:
        facts = load_runtime_facts(
            session_id=payload["session_id"],
            select_device_result=payload.get("select_device_result"),
        )
        return facts.to_json_dict()
    except Exception as e:  # noqa: BLE001
        activity.logger.error(f"load_runtime_facts_activity failed: {e}")
        # Fail loud — RuntimeFacts is foundational. The workflow should
        # surface this as a panic terminal rather than silently proceed.
        raise


@activity.defn
async def is_intent_reachable(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Plan-graph reachability guard (FR-031 / research §R3).

    Payload:
        active_intent:        the intent the planner just emitted
        current_node:         the plan-graph node currently 'in flight'
        completed_nodes:      list of node names whose intent has succeeded

    Returns:
        {reachable: bool, target_node: str|null, reason: str}

    'reachable' is True iff the active_intent corresponds to a node in the plan
    graph whose `requires` precondition is satisfied by `completed_nodes`.

    The workflow uses this on every active_intent transition; on `reachable=False`
    it falls back to the last-known reachable intent and saves evidence.
    """
    graph = get_plan_graph()
    if graph is None:
        # No plan graph loaded → no constraint. Useful for legacy goals that
        # haven't migrated to plan-graph guards yet (spec 004 flows).
        return {"reachable": True, "target_node": None, "reason": "no_plan_graph_loaded"}

    active_intent = payload.get("active_intent")
    completed = set(payload.get("completed_nodes") or [])
    if not active_intent:
        return {"reachable": False, "target_node": None, "reason": "no_active_intent"}

    # Find the node whose intent matches the requested active_intent. The plan
    # graph maps node-name → {intent: intent_id, requires: 'X.success'?, ...}.
    nodes: Dict[str, Any] = graph.get("nodes", {})
    candidates = [
        (name, defn) for name, defn in nodes.items() if defn.get("intent") == active_intent
    ]
    if not candidates:
        # The active_intent isn't in the plan graph at all (e.g. a legacy intent).
        # Treat this as reachable to keep spec 004 flows working; the workflow
        # logs and proceeds. Tighten later when all callers migrate.
        return {
            "reachable": True,
            "target_node": None,
            "reason": "intent_not_in_plan_graph",
        }

    # Recovery and trigger nodes are always reachable when their condition fires
    # (e.g. `trigger: bonus_trigger_signature`); the workflow handles those out
    # of band. We only enforce the linear `requires` chain here.
    for name, defn in candidates:
        requires = defn.get("requires")
        if not requires:
            return {"reachable": True, "target_node": name, "reason": "no_precondition"}
        # `requires: 'authenticate.success'` → the predecessor node name is
        # everything before the dot.
        pred = requires.split(".", 1)[0]
        if pred in completed:
            return {"reachable": True, "target_node": name, "reason": f"precondition_met:{pred}"}

    return {
        "reachable": False,
        "target_node": None,
        "reason": "preconditions_unmet",
    }


@activity.defn
async def record_intent_transition(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Record an intent transition to observation_log for traceability.

    Payload:
        workflow_id:    str
        from_intent:    str (or null at session start)
        to_intent:      str
        reason:         str (planner-supplied rationale)
        ts_iso:         ISO-8601 timestamp

    Returns {written: bool}. Failures are swallowed (Constitution III).
    """
    db = get_screen_db()
    if db is None:
        return {"written": False, "reason": "no_screen_db"}
    try:
        db.write_observation(
            run_id=payload.get("workflow_id"),
            observer_id="intent_transition",
            severity="info",
            pass_fail="n/a",
            summary=f"{payload.get('from_intent')} → {payload.get('to_intent')}",
            captured_json=json.dumps(payload),
        )
        return {"written": True}
    except Exception as e:  # noqa: BLE001
        activity.logger.warning(f"record_intent_transition failed: {e}")
        return {"written": False, "reason": str(e)}
