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
