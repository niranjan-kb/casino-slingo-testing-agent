import os

from ._deps import get_mcp_manager, get_screen_db


async def detect_screen(args: dict) -> dict:
    """Detect which screen the app is currently showing.

    Uses appium_find_element to get on-screen elements, then matches them
    against screen signatures in the DB.

    Args:
        app_context: "platform" or game name (default: "platform")
    """
    app_context = args.get("app_context", "platform")
    db = get_screen_db()
    manager = get_mcp_manager()

    if not manager or not manager.is_running:
        return {"status": "error", "error": "MCP manager not running"}

    # Get visible elements via appium. We use page-source XML rather than
    # find-element with `.*` because the latter only ever returns one node.
    try:
        result = await manager.call_tool("appium_get_page_source", {})
        elements = _parse_page_source(result)
    except Exception as e:
        return {"status": "error", "error": f"appium_get_page_source failed: {e}"}

    if not db:
        return {
            "status": "success",
            "screen": "unknown",
            "confidence": 0.0,
            "method": "no_db",
            "elements_found": len(elements),
            "element_texts": [e.get("text", "") for e in elements[:10]],
        }

    # Match against signatures
    signatures = db.get_screen_signatures(app_context)
    if not signatures:
        return {
            "status": "success",
            "screen": "unknown",
            "confidence": 0.0,
            "method": "no_signatures",
            "elements_found": len(elements),
            "element_texts": [e.get("text", "") for e in elements[:10]],
        }

    best_screen, best_score, matched = _match_signatures(elements, signatures)

    # Cache found element coordinates
    if best_screen and db:
        device_name = os.getenv("ANDROID_SERIAL", "emulator-5554")
        resolution = os.getenv("DEVICE_RESOLUTION", "1080x1920")
        profile_id = db.ensure_device_profile(device_name, resolution, "android")
        _cache_elements(db, profile_id, app_context, best_screen, elements)

    return {
        "status": "success",
        "screen": best_screen or "unknown",
        "confidence": best_score,
        "method": "element",
        "matched_signatures": matched,
        "elements_found": len(elements),
    }


def _parse_elements(result) -> list:
    """Parse appium_find_element result into list of dicts (legacy)."""
    elements = []
    if hasattr(result, "content"):
        import json
        for item in result.content:
            text = getattr(item, "text", str(item))
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    elements.extend(parsed)
                elif isinstance(parsed, dict):
                    elements.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
    return elements


def _parse_page_source(result) -> list:
    """Parse appium_get_page_source XML into a flat list of element dicts."""
    import re
    import xml.etree.ElementTree as ET

    if not hasattr(result, "content"):
        return []

    raw = ""
    for item in result.content:
        raw += getattr(item, "text", str(item))

    # MCP wraps the XML in a markdown fence and HTML-escapes it. Unescape + extract.
    raw = (raw.replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&amp;", "&"))
    m = re.search(r"<\?xml.*?</hierarchy>", raw, re.DOTALL)
    if not m:
        return []

    try:
        root = ET.fromstring(m.group(0))
    except ET.ParseError:
        return []

    elements = []
    for node in root.iter():
        attrs = node.attrib
        text = (attrs.get("text") or "").strip()
        res_id = attrs.get("resource-id") or ""
        desc = attrs.get("content-desc") or ""
        bounds = attrs.get("bounds") or ""
        if not (text or res_id or desc):
            continue
        elements.append({
            "text": text,
            "resource-id": res_id,
            "content-desc": desc,
            "class": attrs.get("class", ""),
            "bounds": bounds,
            "clickable": attrs.get("clickable") == "true",
            "password": attrs.get("password") == "true",
        })
    return elements


def _match_signatures(elements, signatures):
    """Match found elements against screen signatures."""
    found_texts = set()
    found_ids = set()
    for elem in elements:
        if text := (elem.get("text") or ""):
            found_texts.add(text.strip())
        if res_id := (elem.get("resource-id") or elem.get("id") or ""):
            short_id = res_id.split("/")[-1] if "/" in res_id else res_id
            found_ids.add(short_id)
            found_ids.add(res_id)

    best_screen = None
    best_score = 0.0
    best_matched = []

    for screen_name, sigs in signatures.items():
        score = 0
        matched = []
        max_possible = sum(s["priority"] for s in sigs)

        for sig in sigs:
            sig_type = sig["signature_type"]
            sig_value = sig["signature_value"]
            hit = False

            if sig_type == "element_text":
                hit = any(sig_value.lower() in t.lower() for t in found_texts)
            elif sig_type == "element_id":
                hit = any(sig_value.lower() in i.lower() for i in found_ids)

            if hit:
                score += sig["priority"]
                matched.append(f"{sig_type}:{sig_value}")

        confidence = min(score / max(max_possible, 1), 1.0)
        if confidence > best_score:
            best_score = confidence
            best_screen = screen_name
            best_matched = matched

    return best_screen, best_score, best_matched


def _cache_elements(db, profile_id, app_context, screen_name, elements):
    """Cache element coordinates discovered via appium_find_element."""
    for elem in elements:
        bounds = elem.get("bounds")
        x = elem.get("x")
        y = elem.get("y")
        if bounds and not (x and y):
            try:
                parts = bounds.replace("][", ",").strip("[]").split(",")
                if len(parts) == 4:
                    x = (int(parts[0]) + int(parts[2])) // 2
                    y = (int(parts[1]) + int(parts[3])) // 2
            except (ValueError, IndexError):
                continue

        if x is None or y is None:
            continue

        elem_name = None
        if text := elem.get("text"):
            elem_name = text.lower().replace(" ", "_")[:30]
        elif res_id := (elem.get("resource-id") or elem.get("id") or ""):
            elem_name = res_id.split("/")[-1] if "/" in res_id else res_id
        elif desc := (elem.get("content-desc") or elem.get("contentDescription") or ""):
            elem_name = desc.lower().replace(" ", "_")[:30]

        if elem_name:
            db.upsert_element(
                device_profile_id=profile_id,
                app_context=app_context,
                screen_name=screen_name,
                element_name=elem_name,
                x=int(x),
                y=int(y),
                source="element",
                confidence=0.8,
            )
