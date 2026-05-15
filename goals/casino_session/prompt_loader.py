"""Loader for goal_casino_session — composes shared persona + session-specific user/tools."""

import os

from prompts.persona import env_context, load as persona_load, render, soul_and_identity


_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load(filename: str) -> str:
    path = os.path.join(_PROMPTS_DIR, filename)
    with open(path) as f:
        return f.read()


def assemble_description() -> str:
    """Soul + identity + tools + login user-flow, with env vars rendered in."""
    env = env_context()
    persona = soul_and_identity()
    tools = render(_load("tools.md"), env)
    user = render(_load("user.md"), env)
    return "\n\n---\n\n".join([persona, tools, user])


def build_starter_prompt() -> str:
    env = env_context()
    auto_otp = env["BUILD_ENV"] in {"dev", "test"} and env["DEFAULT_OTP"] != "<not configured>"
    otp_note = (
        f"OTP: auto-using `{env['DEFAULT_OTP']}` (BUILD_ENV={env['BUILD_ENV']})."
        if auto_otp
        else "OTP: I'll ask you when the SMS arrives."
    )
    return (
        "Hello — I'm **Danny Ocean**, running a **goal_casino_session**.\n"
        "_\"Winning isn't the end. It's just the buy-in for the next hand.\"_\n\n"
        "Send me a free-text session ask and I'll compile it into a SessionIntent, "
        "authenticate, walk the lobby to your game, play within budget, and write "
        "a run report. Examples:\n"
        "- `play any blackjack`\n"
        "- `play slingo for 5 spins`\n"
        "- `play fanatics blackjack until I lose $2`\n"
        "- `audit the casino lobby` (no betting)\n\n"
        f"Account: `{env['TEST_EMAIL']}` | Build: `{env['BUILD_ENV']}` | "
        f"Platform: `{env['PLATFORM']}` | Resolution: `{env['DEVICE_RESOLUTION']}`\n"
        f"{otp_note}\n\n"
        "Send your prompt, or say `login` to do just the auth flow."
    )


def build_example_conversation() -> str:
    env = env_context()
    return "\n ".join([
        "user: log in",
        "agent: Starting login. Selecting device.",
        "user_confirmed_tool_run: <select_device>",
        f"tool_result: {{\"device\": \"{env['ANDROID_SERIAL']}\", \"platform\": \"android\"}}",
        "agent: Device connected. Creating session and launching app.",
        "user_confirmed_tool_run: <create_session>",
        "user_confirmed_tool_run: <appium_app activate>",
        "tool_result: {\"status\": \"success\"}",
        "agent: App launched. Dumping page source to classify the screen.",
        "user_confirmed_tool_run: <appium_get_page_source>",
        "tool_result: <Precise location required modal>",
        "agent: Location permission modal. Tapping Continue.",
        "user_confirmed_tool_run: <appium_find_element strategy='xpath' selector=\"//*[@text='Continue']\">",
        "user_confirmed_tool_run: <appium_click elementUUID=...>",
        "agent: ...(loops through up to 4 modals)... Login screen detected. Filling email.",
        f"user_confirmed_tool_run: <appium_set_value text='{env['TEST_EMAIL']}'>",
        "user_confirmed_tool_run: <appium_click on Continue>",
        "agent: On password screen. Filling password (not echoed).",
        "user_confirmed_tool_run: <appium_set_value text='***'>",
        "user_confirmed_tool_run: <appium_click on 'Log in'>",
        "agent: OTP screen reached. Auto-filling fixed OTP for build_env=test.",
        f"user_confirmed_tool_run: <appium_set_value text='{env['DEFAULT_OTP']}'>",
        "user_confirmed_tool_run: <appium_click on Done>",
        "agent: Home screen confirmed. Balance visible.",
        "agent: LOGIN PASS — email=<email> | balance=$NN,NNN.NN | platform=android | build=test | resolution=1344x2992",
    ])
