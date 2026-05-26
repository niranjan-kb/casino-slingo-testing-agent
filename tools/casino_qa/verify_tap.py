import logging
import os

from ._deps import get_screen_db
from ._transition_recorder import record_outcome_safely
from .detect_screen import detect_screen

log = logging.getLogger(__name__)


def _record_transition_safely(db, **kwargs) -> None:
    try:
        db.record_transition_observation(**kwargs)
    except Exception as e:  # noqa: BLE001 — failure-tolerant per FR-027
        log.warning("verify_tap: record_transition_observation failed: %s", e)


async def verify_tap(args: dict) -> dict:
    """Verify that a tap produced the expected screen transition.

    After tapping, call this to check if the screen changed as expected.
    Updates confidence scores in the DB based on the result and writes
    back to screen_transitions (MW-1) so the graph grows on every verified
    step.

    Args:
        app_context: "platform" or game name
        screen_name: Screen you were on BEFORE the tap
        element_name: Element you tapped
        tapped_x: X coordinate tapped
        tapped_y: Y coordinate tapped
        expected_screen: Screen you expect to be on AFTER the tap (optional)
    """
    app_context = args.get("app_context", "platform")
    screen_name = args.get("screen_name", "")
    element_name = args.get("element_name", "")
    tapped_x = int(args.get("tapped_x", 0))
    tapped_y = int(args.get("tapped_y", 0))
    expected_screen = args.get("expected_screen")

    # Detect current screen
    detect_result = await detect_screen({"app_context": app_context})
    if detect_result.get("status") != "success":
        return {"success": False, "error": f"Screen detection failed: {detect_result.get('error')}"}

    current_screen = detect_result.get("screen", "unknown")

    # Determine if tap succeeded
    if expected_screen:
        success = current_screen == expected_screen
    else:
        success = current_screen != screen_name

    # Record in DB
    db = get_screen_db()
    if db and screen_name and element_name:
        device_name = os.getenv("ANDROID_SERIAL", "emulator-5554")
        resolution = os.getenv("DEVICE_RESOLUTION", "1080x1920")
        profile_id = db.ensure_device_profile(device_name, resolution, "android")
        db.record_tap_result(profile_id, app_context, screen_name, element_name, success)

        if success:
            _record_transition_safely(
                db,
                from_screen=screen_name,
                intent_verb="tap",
                intent_target=element_name,
                to_screen=current_screen,
                success=True,
                app_context=app_context,
            )
            record_outcome_safely(
                db,
                start_sig=screen_name,
                action=f"tap:{element_name}",
                end_sig=current_screen,
                edge_kind="tap",
                outcome="success",
            )
        else:
            # Spec 006 T604: tap-miss diagnostics now flow through the
            # transition_outcomes path below + the observer framework's
            # observation_log; the legacy `run_observations` write is gone.
            # Verified divergence: decrement expected, upsert actual
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
                    record_outcome_safely(
                        db,
                        start_sig=screen_name,
                        action=f"tap:{element_name}",
                        end_sig=current_screen,
                        edge_kind="tap",
                        outcome="verify_fail",
                    )

    return {
        "success": success,
        "current_screen": current_screen,
        "actual_screen": current_screen,
        "from_screen": screen_name,
        "expected_screen": expected_screen,
        "tapped": {"x": tapped_x, "y": tapped_y},
    }
