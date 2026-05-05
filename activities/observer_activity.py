"""Temporal activity that runs the observer registry once per tool result.

The workflow calls this after every device-affecting tool. Per FR-008
the activity does NOT pull additional device data — everything comes
from the workflow's existing tool result. Per FR-022 / FR-027 any
exception is swallowed; the goal run continues.

Module-level dependency injection (set at worker startup):
    set_screen_db(db)         observation_log persistence target
    set_persona(view)         immutable PersonaDialsView for the session
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from temporalio import activity

# Importing the observers package triggers registration of v1 observers.
from observers import tick                              # noqa: F401
from observers.base import PersonaDialsView, ScreenContext
from observers.screen_identity import compute_identity, extract_xml_text


_screen_db: Any = None
_persona_view: Optional[PersonaDialsView] = None
_signatures_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None


def set_screen_db(db: Any) -> None:
    global _screen_db, _signatures_cache
    _screen_db = db
    # Reset the seeded-signatures cache; it'll be repopulated on first use.
    _signatures_cache = None


def set_persona(view: PersonaDialsView) -> None:
    global _persona_view
    _persona_view = view


def _load_signatures(app_context: str = "platform") -> Dict[str, List[Dict[str, Any]]]:
    """Lazy-load and cache the seeded screen_signatures (~30 rows).

    Cached for the worker's lifetime; signatures rarely change between
    deploys, and re-seeding scripts trigger a worker restart anyway. If
    the DB isn't injected we fall back to an empty dict — every screen
    will be unmatched, which is the correct behaviour pre-seeding.
    """
    global _signatures_cache
    if _signatures_cache is not None:
        return _signatures_cache
    if _screen_db is None:
        _signatures_cache = {}
        return _signatures_cache
    try:
        _signatures_cache = _screen_db.get_screen_signatures(app_context) or {}
    except Exception as e:                                # noqa: BLE001 — FR-027
        activity.logger.warning(f"failed to load seeded signatures: {e}")
        _signatures_cache = {}
    return _signatures_cache


# Tools whose result carries page-source content we can match against
# seeded screen_signatures. Other tools (clicks, typing) return action
# acknowledgements; we skip the observer pass for them.
_SCREEN_REVEALING_TOOLS = {
    "appium_get_page_source",
}


@activity.defn
async def run_observers(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Tick the observer registry against the latest tool result.

    Returns:
        {"observations": [ObservationResult.to_dict(), ...],
         "new_signature": str | None}
    """
    last_tool: Optional[str] = payload.get("last_tool_name")
    last_result: Any = payload.get("last_tool_result") or {}
    seen = list(payload.get("seen_signatures") or [])
    run_id: str = str(payload.get("run_id") or "")
    goal_id: str = str(payload.get("goal_id") or "")

    if last_tool not in _SCREEN_REVEALING_TOOLS:
        # Non-screen-revealing tool (click/type/key); observers that
        # depend on screen state get nothing this tick. Always-fire
        # observers (ToolError) will wire in next push.
        return {"observations": [], "new_signature": None}

    raw_xml = extract_xml_text(last_result)
    if not raw_xml:
        return {"observations": [], "new_signature": None}

    signatures = _load_signatures(os.getenv("APP_CONTEXT", "platform"))
    screen_id, novelty_key, score, matched_descriptors = compute_identity(
        raw_xml, signatures
    )

    novelty = novelty_key not in seen
    persona = _persona_view or PersonaDialsView()

    ctx = ScreenContext(
        page_source_xml=None,                            # raw XML parsed inside compute_identity
        screen_signature=novelty_key,
        screen_id=screen_id,
        novelty=novelty,
        persona=persona,
        last_tool_name=last_tool,
        last_tool_args=payload.get("last_tool_args") or {},
        last_tool_success=bool(payload.get("last_tool_success", True)),
        last_tool_error=payload.get("last_tool_error"),
        balance_snapshot={},
        recent_observations=[],
        run_id=run_id,
        goal_id=goal_id,
    )

    try:
        results = tick(ctx)
    except Exception as e:                               # noqa: BLE001 — FR-022/FR-027
        activity.logger.warning(f"observer tick raised at top level: {e}")
        results = []

    out_observations: list = []
    for r in results:
        out_observations.append(r.to_dict())
        if _screen_db is None:
            continue
        try:
            _screen_db.log_observer_observation(
                r.observer_id,
                run_id=run_id,
                goal_id=goal_id,
                severity=r.severity,
                pass_fail=r.pass_fail,
                matched=r.matched,
                auto_handle=r.auto_handle,
                summary=r.summary,
                evidence_path=r.evidence_path,
                spec_link=r.spec_link,
                failed_rule=r.failed_rule,
                captured_json=json.dumps(r.captured) if r.captured else None,
                sub_flow_json=json.dumps(r.sub_flow_tools) if r.sub_flow_tools else None,
                screen_signature=r.screen_signature,
                screen_id=r.screen_id,
            )
        except Exception as e:                           # noqa: BLE001 — FR-027
            activity.logger.warning(
                f"observation_log write failed for {r.observer_id}: {e}"
            )

    new_sig = novelty_key if novelty else None
    activity.logger.info(
        f"observer tick: tool={last_tool} screen={screen_id or 'unknown'} "
        f"key={novelty_key[:24]} score={score:.2f} novelty={novelty} "
        f"observations={len(out_observations)}"
    )
    return {"observations": out_observations, "new_signature": new_sig}
