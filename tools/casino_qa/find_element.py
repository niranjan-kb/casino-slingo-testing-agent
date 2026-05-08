"""FindElementWithFallback — try multiple selector strategies in one tool call.

Without this, the agent burns one LLM call per failed strategy when
appium-mcp's `appium_find_element` misses. This tool takes a list of
(strategy, selector) tuples and returns the first match — collapsing what was
typically 3-6 LLM round-trips per modal into 1.

Why we need it:
- Compose UIs (Fanatics ONE) expose testTags as resource-ids that contain
  spaces (e.g. `email address text`), which makes by-id lookups flaky across
  appium-mcp versions; xpath usually wins but sometimes by-id is the only hit.
- The screen-map DB stores xpath/id selectors; we want a lookup-and-find tool
  that doesn't require the LLM to retry-pick strategies.
"""

import logging
import os
from typing import Any, Dict, List

from ._deps import get_mcp_manager, get_screen_db

log = logging.getLogger(__name__)


_SUPPORTED_STRATEGIES = {
    "xpath",
    "id",
    "name",
    "class name",
    "accessibility id",
    "css selector",
    "-android uiautomator",
    "-ios predicate string",
    "-ios class chain",
}


async def find_element_with_fallback(args: Dict[str, Any]) -> Dict[str, Any]:
    """Try each (strategy, selector) tuple in order; return the first match.

    Args:
        candidates: list of dicts with keys 'strategy' and 'selector'.
                    Tried in order, first hit wins.
                    Example:
                        [{"strategy": "xpath", "selector": "//*[@text='Continue']"},
                         {"strategy": "accessibility id", "selector": "next button"},
                         {"strategy": "id", "selector": "continue_button"}]

    Returns:
        On hit: {"found": True, "elementUUID": "...", "strategy": "xpath",
                 "selector": "...", "tries": <int>}
        On miss: {"found": False, "tries": <int>, "errors": [{"strategy", "selector", "error"}, ...]}

    The returned `elementUUID` plugs straight into appium_click / appium_set_value /
    appium_get_text without further translation.
    """
    manager = get_mcp_manager()
    if not manager or not manager.is_running:
        return {"found": False, "error": "MCP manager not running"}

    raw_candidates = args.get("candidates") or []
    if not isinstance(raw_candidates, list) or not raw_candidates:
        return {"found": False, "error": "candidates must be a non-empty list"}

    errors: List[Dict[str, str]] = []
    tries = 0

    for cand in raw_candidates:
        if not isinstance(cand, dict):
            errors.append({"strategy": "?", "selector": "?", "error": "candidate not a dict"})
            continue

        strategy = (cand.get("strategy") or "").strip()
        selector = cand.get("selector")

        if not strategy or selector is None:
            errors.append({
                "strategy": str(strategy),
                "selector": str(selector),
                "error": "strategy and selector are both required",
            })
            continue

        if strategy not in _SUPPORTED_STRATEGIES:
            errors.append({
                "strategy": strategy,
                "selector": str(selector),
                "error": f"unsupported strategy (must be one of {sorted(_SUPPORTED_STRATEGIES)})",
            })
            continue

        tries += 1
        try:
            result = await manager.call_tool(
                "appium_find_element",
                {"strategy": strategy, "selector": selector},
            )
        except Exception as e:
            errors.append({
                "strategy": strategy,
                "selector": str(selector),
                "error": f"{type(e).__name__}: {e}",
            })
            continue

        element_uuid = _extract_element_uuid(result)
        if element_uuid:
            recorded = _maybe_upsert_element(args, strategy, selector)
            return {
                "found": True,
                "elementUUID": element_uuid,
                "strategy": strategy,
                "selector": selector,
                "tries": tries,
                "recorded": recorded,
            }

        errors.append({
            "strategy": strategy,
            "selector": str(selector),
            "error": _summarize_miss(result),
        })

    return {"found": False, "tries": tries, "errors": errors}


def _maybe_upsert_element(
    args: Dict[str, Any],
    strategy: str,
    selector: str,
) -> bool:
    """Best-effort element upsert when caller passes intent context (MW-2 / FR-019).

    Records the matched element into screen_elements ONLY when the caller has
    already supplied coordinates (via `x`, `y` in args) — this tool itself
    cannot cheaply extract bounds from appium-mcp's find_element response.
    SmartTap is the high-volume writer; this is a hook for raw-exploration
    callers that already have bounds.

    Failures are swallowed and logged; the user-facing return is unchanged.
    """
    try:
        screen_name = args.get("screen_name")
        if not screen_name:
            return False
        x = args.get("x")
        y = args.get("y")
        if x is None or y is None:
            return False
        db = get_screen_db()
        if not db:
            return False
        app_context = args.get("app_context", "platform")
        intent_target = args.get("intent_target") or f"{strategy}:{selector}"
        device_name = os.getenv("ANDROID_SERIAL", "emulator-5554")
        resolution = os.getenv("DEVICE_RESOLUTION", "1080x1920")
        platform = os.getenv("PLATFORM", "android")
        profile_id = db.ensure_device_profile(device_name, resolution, platform)
        db.upsert_element(
            device_profile_id=profile_id,
            app_context=app_context,
            screen_name=screen_name,
            element_name=str(intent_target)[:60],
            x=int(x),
            y=int(y),
            source="element",
            confidence=0.6,
        )
        return True
    except Exception as e:  # noqa: BLE001 — failure-tolerant per FR-027
        log.warning("find_element_with_fallback: upsert_element failed: %s", e)
        return False


def _extract_element_uuid(result: Any) -> str:
    """Pull the elementUUID out of an appium-mcp find_element response.

    appium-mcp returns text like:
        "Successfully found element //* with strategy xpath. Element id 00000000-0000-001b-0000-..."
    Failure looks like:
        "Failed to find element. Error: An element could not be located..."
    """
    import re

    if not hasattr(result, "content"):
        return ""

    for item in result.content:
        text = getattr(item, "text", "") or ""
        if not text or "Failed to find" in text:
            continue
        match = re.search(r"[Ee]lement\s*(?:id|UUID)\s+([0-9a-f-]{16,})", text)
        if match:
            return match.group(1)
    return ""


def _summarize_miss(result: Any) -> str:
    """Short error message from a missed find_element response."""
    if not hasattr(result, "content"):
        return "no content"
    for item in result.content:
        text = getattr(item, "text", "") or ""
        if text:
            return text[:200]
    return "miss (no text in response)"
