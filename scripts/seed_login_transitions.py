"""Seed the verified login flow as transitions in screen_map_db.

This is the data form of goals/login/prompts/user.md's phase procedure.
Each row says "from screen A, doing X lands on screen B" — exactly
what the path planner walks. Once seeded, the agent can navigate
app_launch → home without reading the procedural markdown.

Idempotent — uses upsert. Re-run after schema changes.

Verified 2026-04-29 against BUILD_ENV=test on com.betfanatics.casino.test
(Pixel 9 Pro emulator, 1344x2992).

Run:
    uv run scripts/seed_login_transitions.py
"""

from shared.screen_map_db import ScreenMapDB


# Each tuple: (from, verb, target, args, to)
# Composite verbs ("fill_email_and_continue") capture multi-step user actions
# whose precise tool sequence is the agent's job to execute. The graph stays
# screen-to-screen; the executor handles the inner tools.
TRANSITIONS = [
    # ── Pre-login modal cascade ──────────────────────────────────────
    ("app_launch", "launch", "casino_app", None, "location_modal"),

    ("location_modal", "tap", "continue_button", None, "system_permission_location"),

    ("system_permission_location", "tap",
     "permission_allow_foreground_only_button", None,
     "notification_reward_modal"),

    ("notification_reward_modal", "tap", "continue_button", None,
     "system_permission_notification"),

    ("system_permission_notification", "tap", "permission_allow_button", None,
     "fanatics_one_email"),

    # ── Fanatics ONE 2-step login ────────────────────────────────────
    # Composite verbs: each fills the field then taps the proceed button.
    # Args carry the value to type (templated; resolved at runtime via the
    # injected env_context — see prompts/persona/__init__.py).
    ("fanatics_one_email", "fill_and_continue", "email_field",
     {"text_template": "{{TEST_EMAIL}}", "submit_button": "continue_button"},
     "fanatics_one_password"),

    ("fanatics_one_password", "fill_and_login", "password_field",
     {"text_template": "{{TEST_PASSWORD}}", "submit_button": "log_in_button"},
     "fanatics_one_otp"),

    # OTP auto-submits on the 6th digit on test build, so the "submit"
    # is implicit — we still record a wait-and-classify step.
    ("fanatics_one_otp", "fill_otp_and_submit", "otp_field",
     {"text_template": "{{DEFAULT_OTP}}", "auto_submits_on_6_digits": True},
     "loyalty_bottom_sheet"),

    # ── Post-login modal ─────────────────────────────────────────────
    ("loyalty_bottom_sheet", "tap", "close_sheet", None, "home"),

    # ── Alternate paths (lower confidence; planner uses on miss) ─────
    # If OTP routes directly to home (loyalty modal not shown):
    ("fanatics_one_otp", "fill_otp_and_submit", "otp_field",
     {"text_template": "{{DEFAULT_OTP}}", "auto_submits_on_6_digits": True},
     "home"),
]


def main() -> None:
    db = ScreenMapDB()
    print(f"Seeding {len(TRANSITIONS)} login-flow transitions into {db.db_path}\n")

    for (from_s, verb, target, args, to_s) in TRANSITIONS:
        # The two fanatics_one_otp -> ... rows share verb+target; the args
        # differ structurally (which post-OTP screen we observed). Make the
        # second row lower-confidence so the loyalty path is preferred when
        # both edges are present.
        confidence = 0.95 if to_s != "home" or from_s != "fanatics_one_otp" else 0.5
        db.upsert_transition(
            from_screen=from_s,
            intent_verb=verb,
            to_screen=to_s,
            intent_target=target,
            intent_args=args,
            app_context="platform",
            confidence=confidence,
            source="seed",
        )
        args_summary = "" if not args else f"  args={list(args.keys())}"
        print(f"  [{from_s:34s}] --{verb}({target or '-'})--> {to_s}"
              f"  conf={confidence:.2f}{args_summary}")

    stats = db.get_stats()
    print(f"\n✓ DB stats: transitions={stats['transitions']}, "
          f"signatures={stats['signatures']}, games={stats['games']}")


if __name__ == "__main__":
    main()
