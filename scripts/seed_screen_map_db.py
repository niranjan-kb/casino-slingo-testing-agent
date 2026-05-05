"""
Seed the screen map SQLite DB from existing JSON screen maps.

Also inserts screen signatures for element-based screen detection
and login/OTP screen definitions (no JSON maps exist for those yet).

Run: uv run scripts/seed_screen_map_db.py [--reset]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.screen_map_db import ScreenMapDB

# ── JSON screen map files to import ──────────────────────────────────

SCREEN_MAP_DIR = os.path.join(os.path.dirname(__file__), "..", "screen_maps")

JSON_MAPS = [
    # (file_path, app_context)
    ("platform/android/1080x1920.json", "platform"),
    ("games/slingo_cash_eruption/android/1080x1920.json", "slingo_cash_eruption"),
]

# ── Screen signatures for element-based detection ────────────────────
# Format: (screen_name, app_context, signature_type, signature_value, priority)

SCREEN_SIGNATURES = [
    # Login screen
    ("login", "platform", "element_text", "Sign In", 10),
    ("login", "platform", "element_text", "Log In", 10),
    ("login", "platform", "element_text", "Email", 5),
    ("login", "platform", "element_id", "email", 5),
    ("login", "platform", "element_id", "password", 5),

    # OTP screen
    ("otp", "platform", "element_text", "Enter Code", 10),
    ("otp", "platform", "element_text", "Verification Code", 10),
    ("otp", "platform", "element_text", "Enter OTP", 10),
    ("otp", "platform", "element_text", "We sent a code", 8),
    ("otp", "platform", "element_text", "Enter the code", 8),

    # Home screen
    ("home", "platform", "element_text", "Search", 5),
    ("home", "platform", "element_text", "Casino", 3),
    ("home", "platform", "element_text", "Featured", 3),

    # Search results
    ("search_results", "platform", "element_text", "Search Results", 8),
    ("search_results", "platform", "element_text", "Slingo", 3),

    # Keep Playing modal
    ("keep_playing_modal", "platform", "element_text", "Keep Playing", 10),
    ("keep_playing_modal", "platform", "element_text", "Keep playing?", 10),
    ("keep_playing_modal", "platform", "element_text", "No thanks", 8),

    # FanCash prompt
    ("fancash_prompt", "platform", "element_text", "FanCash", 8),
    ("fancash_prompt", "platform", "element_text", "Start Playing", 5),

    # Game header (native bar above WebView)
    ("game_header", "platform", "element_text", "Close", 5),

    # Reality check / responsible gaming popup
    ("reality_check", "platform", "element_text", "Reality Check", 10),
    ("reality_check", "platform", "element_text", "Continue Playing", 5),

    # Location permission
    ("location_prompt", "platform", "element_text", "Allow", 3),
    ("location_prompt", "platform", "element_text", "location", 5),
]

# ── Login / OTP seed coordinates (best guesses for 1080x1920) ────────
# These will be corrected by the verify loop on first run.

LOGIN_OTP_ELEMENTS = [
    # Login screen elements
    {
        "app_context": "platform",
        "screen_name": "login",
        "element_name": "email_field",
        "x": 540, "y": 700,
        "element_type": "input",
        "intent": "Email address input field",
    },
    {
        "app_context": "platform",
        "screen_name": "login",
        "element_name": "password_field",
        "x": 540, "y": 850,
        "element_type": "input",
        "intent": "Password input field",
    },
    {
        "app_context": "platform",
        "screen_name": "login",
        "element_name": "sign_in_button",
        "x": 540, "y": 1050,
        "element_type": "button",
        "intent": "Submit login credentials",
    },
    # OTP screen elements
    {
        "app_context": "platform",
        "screen_name": "otp",
        "element_name": "otp_input",
        "x": 540, "y": 800,
        "element_type": "input",
        "intent": "OTP / verification code input field",
    },
    {
        "app_context": "platform",
        "screen_name": "otp",
        "element_name": "otp_submit",
        "x": 540, "y": 1000,
        "element_type": "button",
        "intent": "Submit OTP code",
    },
]


def import_json_map(db: ScreenMapDB, json_path: str, app_context: str) -> int:
    """Import a JSON screen map file into the DB. Returns count of elements imported."""
    full_path = os.path.join(SCREEN_MAP_DIR, json_path)
    if not os.path.exists(full_path):
        print(f"  SKIP {json_path} (file not found)")
        return 0

    with open(full_path) as f:
        data = json.load(f)

    platform = data.get("platform", "android")
    resolution = data.get("resolution", "1080x1920")
    device_name = data.get("note", "").split("Device: ")[-1].split(".")[0].split(" ")[0] if "Device:" in data.get("note", "") else "unknown"
    if device_name == "unknown":
        device_name = f"{platform}_{resolution}"

    profile_id = db.ensure_device_profile(device_name, resolution, platform)
    count = 0

    for screen_name, screen_data in data.get("screens", {}).items():
        # Handle flat element dicts (platform maps)
        elements = screen_data.get("elements", {})
        for elem_name, elem_data in elements.items():
            db.upsert_element(
                device_profile_id=profile_id,
                app_context=app_context,
                screen_name=screen_name,
                element_name=elem_name,
                x=elem_data["x"],
                y=elem_data["y"],
                source="seed",
                element_type=elem_data.get("type"),
                intent=elem_data.get("intent"),
                confidence=0.5,
            )
            count += 1

        # Handle game maps with grid/reel/controls structure
        if "grid" in screen_data:
            grid = screen_data["grid"]
            cols = grid.get("columns", {})
            rows = grid.get("rows", {})
            for row_num, row_y in rows.items():
                for col_num, col_x in cols.items():
                    db.upsert_element(
                        device_profile_id=profile_id,
                        app_context=app_context,
                        screen_name=screen_name,
                        element_name=f"grid_r{row_num}_c{col_num}",
                        x=int(col_x),
                        y=int(row_y),
                        source="seed",
                        element_type="cell",
                        intent=f"Grid cell row {row_num}, column {col_num}",
                        confidence=0.5,
                    )
                    count += 1

        if "reel" in screen_data:
            reel = screen_data["reel"]
            reel_y = reel["y"]
            for i, slot_x in enumerate(reel.get("slots", []), 1):
                db.upsert_element(
                    device_profile_id=profile_id,
                    app_context=app_context,
                    screen_name=screen_name,
                    element_name=f"reel_slot_{i}",
                    x=int(slot_x),
                    y=int(reel_y),
                    source="seed",
                    element_type="cell",
                    intent=f"Reel slot {i}",
                    confidence=0.5,
                )
                count += 1

        if "controls" in screen_data:
            for ctrl_name, ctrl_data in screen_data["controls"].items():
                db.upsert_element(
                    device_profile_id=profile_id,
                    app_context=app_context,
                    screen_name=screen_name,
                    element_name=ctrl_name,
                    x=ctrl_data["x"],
                    y=ctrl_data["y"],
                    source="seed",
                    element_type=ctrl_data.get("type"),
                    intent=ctrl_data.get("intent"),
                    confidence=0.5,
                )
                count += 1

    return count


def seed_login_otp_elements(db: ScreenMapDB, profile_id: str) -> int:
    """Seed login and OTP elements with best-guess coordinates."""
    count = 0
    for elem in LOGIN_OTP_ELEMENTS:
        db.upsert_element(
            device_profile_id=profile_id,
            app_context=elem["app_context"],
            screen_name=elem["screen_name"],
            element_name=elem["element_name"],
            x=elem["x"],
            y=elem["y"],
            source="seed",
            element_type=elem.get("element_type"),
            intent=elem.get("intent"),
            confidence=0.3,  # lower confidence — untested guesses
        )
        count += 1
    return count


def seed_signatures(db: ScreenMapDB) -> int:
    """Seed screen signatures for element-based detection."""
    for sig in SCREEN_SIGNATURES:
        db.upsert_screen_signature(*sig)
    return len(SCREEN_SIGNATURES)


def main():
    parser = argparse.ArgumentParser(description="Seed screen map DB from JSON files")
    parser.add_argument("--reset", action="store_true", help="Delete existing DB and start fresh")
    parser.add_argument("--db-path", default=None, help="Override DB path")
    args = parser.parse_args()

    db_path = args.db_path
    db = ScreenMapDB(db_path) if db_path else ScreenMapDB()

    if args.reset and os.path.exists(db.db_path):
        print(f"Resetting DB: {db.db_path}")
        os.remove(db.db_path)
        db = ScreenMapDB(db_path) if db_path else ScreenMapDB()

    print(f"DB path: {db.db_path}")
    print()

    # Import JSON screen maps
    total_elements = 0
    default_profile_id = None
    for json_path, app_context in JSON_MAPS:
        count = import_json_map(db, json_path, app_context)
        print(f"  Imported {count} elements from {json_path}")
        total_elements += count

    # Get or create default device profile for login/OTP seeds
    profiles = db.list_device_profiles()
    if profiles:
        default_profile_id = profiles[0]["id"]
    else:
        default_profile_id = db.ensure_device_profile("android_1080x1920", "1080x1920", "android")

    # Seed login/OTP elements
    login_count = seed_login_otp_elements(db, default_profile_id)
    print(f"  Seeded {login_count} login/OTP elements for {default_profile_id}")
    total_elements += login_count

    # Seed screen signatures
    sig_count = seed_signatures(db)
    print(f"  Seeded {sig_count} screen signatures")

    print()
    stats = db.get_stats()
    print(f"DB totals: {stats}")
    db.close()


if __name__ == "__main__":
    main()
