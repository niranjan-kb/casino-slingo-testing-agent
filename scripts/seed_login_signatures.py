"""Seed verified screen signatures for the login flow into the screen-map DB.

These signatures let `DetectScreen` identify each screen without page-source
parsing. Verified against BUILD_ENV=test on com.betfanatics.casino.test
(Pixel 9 Pro emulator, 1344x2992) on 2026-04-29.

Run once:
    uv run scripts/seed_login_signatures.py

Idempotent — uses upsert. Re-run after schema changes or to refresh priorities.
"""

from shared.screen_map_db import ScreenMapDB


# (screen_name, signature_type, signature_value, priority)
# Higher priority signatures are checked first.
SIGNATURES = [
    # === Pre-login modals ===
    ("location_modal", "element_text", "Precise location required", 100),
    ("location_modal", "element_id", "location permission button", 90),

    ("notification_reward_modal", "element_text", "Get rewarded — Fanatically", 100),
    ("notification_reward_modal", "element_text", "FanCash", 60),
    ("notification_reward_modal", "element_id", "notification permission button", 90),

    ("system_permission_location", "element_id",
     "com.android.permissioncontroller:id/permission_allow_foreground_only_button", 100),
    ("system_permission_location", "element_text", "While using the app", 80),
    ("system_permission_location", "element_text", "Allow Fanatics Casino to access this device", 70),

    ("system_permission_notification", "element_id",
     "com.android.permissioncontroller:id/permission_allow_button", 100),
    ("system_permission_notification", "element_text", "Allow Fanatics Casino to send you notifications", 90),

    # === Fanatics ONE 2-step login ===
    ("fanatics_one_email", "element_text", "Log in or sign up", 100),
    ("fanatics_one_email", "element_id", "email address text", 95),
    ("fanatics_one_email", "element_text", "Enter the email you use to sign in", 70),

    ("fanatics_one_password", "element_text", "Enter your password", 100),
    ("fanatics_one_password", "element_id", "password text", 95),
    ("fanatics_one_password", "element_text", "Forgot password?", 60),

    ("fanatics_one_otp", "element_text", "One time passcode", 100),
    ("fanatics_one_otp", "element_id", "mfa code text", 95),
    ("fanatics_one_otp", "element_text", "Please enter the 6-digit code", 80),

    # === Logged-in home / lobby ===
    ("home_lobby", "element_text", "Hollywood Casino", 100),
    ("home_lobby", "element_text", "Featured", 70),
    ("home_lobby", "element_text", "Slingo", 60),
    ("home_lobby", "element_text", "FanCash", 50),

    # === Post-login loyalty bottom-sheet (intermediate) ===
    ("loyalty_bottom_sheet", "element_text", "ONE member", 100),
    ("loyalty_bottom_sheet", "element_text", "Learn more", 60),
    ("loyalty_bottom_sheet", "element_text", "Close sheet", 80),
]


def main() -> None:
    db = ScreenMapDB()
    inserted = 0
    for screen_name, sig_type, sig_value, priority in SIGNATURES:
        db.upsert_screen_signature(
            screen_name=screen_name,
            app_context="platform",
            signature_type=sig_type,
            signature_value=sig_value,
            priority=priority,
        )
        inserted += 1
        print(f"  [{screen_name:32s}] {sig_type}={sig_value!r:60s} pri={priority}")

    # Quick verification
    sigs = db.get_screen_signatures("platform")
    print(f"\n✓ Seeded {inserted} signatures across {len(sigs)} screens")
    for screen, rows in sorted(sigs.items()):
        print(f"  - {screen}: {len(rows)} signatures")


if __name__ == "__main__":
    main()
