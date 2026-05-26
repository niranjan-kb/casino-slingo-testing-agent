import asyncio
import logging
import os

from ._deps import get_mcp_manager, get_screen_db
from ._transition_recorder import record_outcome_safely
from .detect_screen import detect_screen

log = logging.getLogger(__name__)


def _record_transition_safely(db, **kwargs) -> None:
    """Wrap record_transition_observation in a try/except so any DB write
    error logs a warning and continues — the goal loop must never halt on
    auto-record failure (FR-027)."""
    try:
        db.record_transition_observation(**kwargs)
    except Exception as e:  # noqa: BLE001 — failure-tolerant by contract
        log.warning(
            "record_transition_observation: failed (from=%s verb=%s target=%s to=%s): %s",
            kwargs.get("from_screen"), kwargs.get("intent_verb"),
            kwargs.get("intent_target"), kwargs.get("to_screen"), e,
        )


async def tap_mapped(args: dict) -> dict:
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
                purpose=guess.get("purpose"),
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

            # ── 6. AUTO-RECORD TRANSITION (MW-1, FR-017) ─────────────
            if verified:
                _record_transition_safely(
                    db,
                    from_screen=screen_name,
                    intent_verb="tap",
                    intent_target=element_name,
                    to_screen=current_screen,
                    success=True,
                    app_context=app_context,
                )
                # T044: stochastic-outcomes mirror.
                record_outcome_safely(
                    db,
                    start_sig=screen_name,
                    action=f"tap:{element_name}",
                    end_sig=current_screen,
                    edge_kind="tap",
                    outcome="success",
                )
            else:
                # Spec 006 T604: tap-miss diagnostics flow through
                # transition_outcomes (success=False edge below) + the
                # observation_log; the legacy `run_observations` write is gone.
                # Verified divergence: decrement the expected (wrong) edge
                # and upsert the actual edge as a competing transition.
                if expected_screen and current_screen != expected_screen:
                    _record_transition_safely(
                        db,
                        from_screen=screen_name,
                        intent_verb="tap",
                        intent_target=element_name,
                        to_screen=expected_screen,
                        success=False,
                        app_context=app_context,
                    )
                    if current_screen and current_screen != "unknown":
                        _record_transition_safely(
                            db,
                            from_screen=screen_name,
                            intent_verb="tap",
                            intent_target=element_name,
                            to_screen=current_screen,
                            success=True,
                            app_context=app_context,
                        )
                        # T044: divergent stochastic outcome — still a real
                        # observed end_sig, just not the expected one.
                        record_outcome_safely(
                            db,
                            start_sig=screen_name,
                            action=f"tap:{element_name}",
                            end_sig=current_screen,
                            edge_kind="tap",
                            outcome="verify_fail",
                        )
        else:
            # Detection failed — still record the tap attempt
            db.record_tap_result(profile_id, app_context, screen_name, element_name, False)
            verified = None
    else:
        # Graduated element — record success optimistically
        db.record_tap_result(profile_id, app_context, screen_name, element_name, True)
        # Optimistic transition write: trust the expected_screen if provided
        if expected_screen:
            _record_transition_safely(
                db,
                from_screen=screen_name,
                intent_verb="tap",
                intent_target=element_name,
                to_screen=expected_screen,
                success=True,
                app_context=app_context,
            )
            record_outcome_safely(
                db,
                start_sig=screen_name,
                action=f"tap:{element_name}",
                end_sig=expected_screen,
                edge_kind="tap",
                outcome="success",
            )

    return {
        "success": verified if verified is not None else True,
        "tapped": {"x": x, "y": y},
        "confidence": confidence,
        "source": source,
        "needs_verification": needs_verify,
        "verified": verified,
        "current_screen": current_screen,
        "expected_screen": expected_screen,
        "from_screen": screen_name,
        "actual_screen": current_screen,
    }
