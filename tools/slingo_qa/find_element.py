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

from typing import Any, Dict, List

from ._deps import get_mcp_manager


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
            return {
                "found": True,
                "elementUUID": element_uuid,
                "strategy": strategy,
                "selector": selector,
                "tries": tries,
            }

        errors.append({
            "strategy": strategy,
            "selector": str(selector),
            "error": _summarize_miss(result),
        })

    return {"found": False, "tries": tries, "errors": errors}


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
