import asyncio
import os

from ._deps import get_mcp_manager, get_screen_db
from .detect_screen import detect_screen


async def smart_tap(args: dict) -> dict:
    """Lookup coordinates, tap, wait, verify, and update confidence — all in one call.

    Guarantees the learning loop runs every time. The DB is always consulted
    before tapping and always updated after verification.

    Args:
        app_context: "platform" or game name (e.g. "slingo_cash_eruption")
        screen_name: Current screen name (e.g. "home", "main_game")
        element_name: Element to tap (e.g. "spin_button", "search_bar")
        expected_screen: Screen expected after the tap (optional — if omitted,
                         success = screen changed from screen_name)
        wait_seconds: Seconds to wait after tap for UI transition (default 2)
    """
    app_context = args.get("app_context", "platform")
    screen_name = args.get("screen_name", "")
    element_name = args.get("element_name", "")
    expected_screen = args.get("expected_screen")
    wait_after = min(float(args.get("wait_seconds", 2)), 30)

    if not screen_name or not element_name:
        return {"success": False, "error": "screen_name and element_name are required"}

    db = get_screen_db()
    if not db:
        return {"success": False, "error": "Screen map DB not available"}

    device_name = os.getenv("ANDROID_SERIAL", "emulator-5554")
    resolution = os.getenv("DEVICE_RESOLUTION", "1080x1920")
    profile_id = db.ensure_device_profile(device_name, resolution, "android")

    # ── 1. LOOKUP ────────────────────────────────────────────────────
    elem = db.get_element_coords(profile_id, app_context, screen_name, element_name)
    source = "db"

    if not elem:
        # Cross-device fallback
        guess = db.get_best_guess_coords(app_context, screen_name, element_name, resolution)
        if guess:
            db.upsert_element(
                profile_id, app_context, screen_name, element_name,
                guess["x"], guess["y"],
                source="cross_device",
                element_type=guess.get("element_type"),
                intent=guess.get("intent"),
                confidence=0.3,
            )
            elem = db.get_element_coords(profile_id, app_context, screen_name, element_name)
            source = "cross_device"
        else:
            return {
                "success": False,
                "error": f"No coordinates found for {screen_name}/{element_name}",
                "hint": "Use appium_find_element to discover coordinates, then the agent can store them.",
            }

    x, y = elem["x"], elem["y"]
    confidence = elem.get("confidence", 0)
    needs_verify = db.should_verify_tap(profile_id, app_context, screen_name, element_name)

    # ── 2. TAP ───────────────────────────────────────────────────────
    manager = get_mcp_manager()
    if not manager or not manager.is_running:
        return {"success": False, "error": "MCP manager not running. Is appium-mcp started?"}

    tap_result = await manager.call_tool("appium_swipe", {
        "startX": x, "startY": y, "endX": x, "endY": y,
    })

    # ── 3. WAIT ──────────────────────────────────────────────────────
    await asyncio.sleep(wait_after)

    # ── 4. VERIFY (if needed) ────────────────────────────────────────
    verified = None
    current_screen = None

    if needs_verify:
        detect_result = await detect_screen({"app_context": app_context})
        if detect_result.get("status") == "success":
            current_screen = detect_result.get("screen", "unknown")
            if expected_screen:
                verified = current_screen == expected_screen
            else:
                verified = current_screen != screen_name

            # ── 5. UPDATE DB ─────────────────────────────────────────
            db.record_tap_result(profile_id, app_context, screen_name, element_name, verified)

            if not verified:
                db.log_observation(
                    device_profile_id=profile_id,
                    screen_name=screen_name,
                    element_name=element_name,
                    action="smart_tap",
                    expected_result=f"transition to {expected_screen or 'next screen'}",
                    actual_result=f"still on {current_screen}",
                )
        else:
            # Detection failed — still record the tap attempt
            db.record_tap_result(profile_id, app_context, screen_name, element_name, False)
            verified = None
    else:
        # Graduated element — record success optimistically
        db.record_tap_result(profile_id, app_context, screen_name, element_name, True)

    return {
        "success": verified if verified is not None else True,
        "tapped": {"x": x, "y": y},
        "confidence": confidence,
        "source": source,
        "needs_verification": needs_verify,
        "verified": verified,
        "current_screen": current_screen,
        "expected_screen": expected_screen,
    }
