import os

from ._deps import get_screen_db


def lookup_element_coords(args: dict) -> dict:
    """Look up stored coordinates for an element from the screen map DB.

    Args:
        app_context: "platform" or game name (e.g. "slingo_cash_eruption")
        screen_name: Screen name (e.g. "home", "main_game")
        element_name: Element to find (e.g. "spin_button", "search_bar")
    """
    app_context = args.get("app_context", "platform")
    screen_name = args.get("screen_name", "")
    element_name = args.get("element_name", "")

    if not screen_name or not element_name:
        return {"found": False, "error": "screen_name and element_name are required"}

    db = get_screen_db()
    if not db:
        return {"found": False, "error": "Screen map DB not available"}

    device_name = os.getenv("ANDROID_SERIAL", "emulator-5554")
    resolution = os.getenv("DEVICE_RESOLUTION", "1080x1920")
    profile_id = db.ensure_device_profile(device_name, resolution, "android")

    # Exact device match
    elem = db.get_element_coords(profile_id, app_context, screen_name, element_name)
    if elem:
        needs_verify = db.should_verify_tap(profile_id, app_context, screen_name, element_name)
        return {
            "found": True,
            "x": elem["x"],
            "y": elem["y"],
            "confidence": elem["confidence"],
            "source": "db",
            "needs_verification": needs_verify,
        }

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
        return {
            "found": True,
            "x": guess["x"],
            "y": guess["y"],
            "confidence": 0.3,
            "source": "cross_device",
            "needs_verification": True,
        }

    return {"found": False}
