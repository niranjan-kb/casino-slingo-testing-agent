"""
Loads and assembles the multi-file prompt for the Slingo QA Android agent.

Reads markdown files from prompts/, injects environment variables,
and populates dynamic sections from the screen map database.
"""

import os
from typing import Dict, List, Optional

from shared.screen_map_db import ScreenMapDB

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def load_prompt_file(filename: str) -> str:
    """Load a prompt markdown file."""
    path = os.path.join(_PROMPTS_DIR, filename)
    with open(path) as f:
        return f.read()


def inject_env_vars(text: str) -> str:
    """Replace {{VAR}} placeholders with environment values."""
    replacements = {
        "{{ANDROID_SERIAL}}": os.getenv("ANDROID_SERIAL", "emulator-5554"),
        "{{DEVICE_RESOLUTION}}": os.getenv("DEVICE_RESOLUTION", "1080x1920"),
        "{{APP_PACKAGE}}": os.getenv("APP_PACKAGE", "com.betfanatics.casino"),
        "{{BUILD_ENV}}": os.getenv("BUILD_ENV", "dev"),
        "{{PRODUCT_FLAVOR}}": os.getenv("PRODUCT_FLAVOR", "casino"),
        "{{PLATFORM}}": os.getenv("PLATFORM", "android"),
        "{{TEST_EMAIL}}": os.getenv("TEST_EMAIL", "not configured"),
        "{{TEST_PASSWORD_STATUS}}": "configured" if os.getenv("TEST_PASSWORD") else "not configured",
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text


def format_coordinates_table(
    elements: List[Dict],
    title: str = "",
) -> str:
    """Format a list of screen elements into a readable coordinate table."""
    if not elements:
        return f"{title}\nNo coordinates stored yet for this device.\n"

    # Group by screen_name
    by_screen: Dict[str, List[Dict]] = {}
    for e in elements:
        screen = e["screen_name"]
        if screen not in by_screen:
            by_screen[screen] = []
        by_screen[screen].append(e)

    lines = []
    if title:
        lines.append(title)

    for screen, elems in sorted(by_screen.items()):
        lines.append(f"\n### {screen}")
        lines.append("| Element | x | y | Confidence | Source | Intent |")
        lines.append("|---------|---|---|------------|--------|--------|")
        for e in sorted(elems, key=lambda x: x["element_name"]):
            conf = f"{e['confidence']:.1f}" if e["confidence"] is not None else "?"
            source = e.get("source", "?")
            intent = e.get("intent", "") or ""
            lines.append(
                f"| {e['element_name']} | {e['x']} | {e['y']} | {conf} | {source} | {intent} |"
            )

    return "\n".join(lines)


def format_signatures(signatures: Dict[str, List[Dict]]) -> str:
    """Format screen signatures into readable text."""
    if not signatures:
        return "No screen signatures configured."

    lines = []
    for screen, sigs in sorted(signatures.items()):
        sig_strs = []
        for s in sorted(sigs, key=lambda x: -x["priority"]):
            sig_strs.append(f'`{s["signature_type"]}`: "{s["signature_value"]}" (pri={s["priority"]})')
        lines.append(f"- **{screen}**: {', '.join(sig_strs)}")

    return "\n".join(lines)


def format_observations(observations: List[Dict]) -> str:
    """Format recent observations into readable text."""
    if not observations:
        return "No observations yet — this is a fresh device."

    lines = []
    for obs in observations[:10]:
        action = obs.get("action", "?")
        screen = obs.get("screen_name", "?")
        element = obs.get("element_name", "?")
        expected = obs.get("expected_result", "")
        actual = obs.get("actual_result", "")
        correction = obs.get("correction", "")
        ts = obs.get("timestamp", "")[:19]

        line = f"- [{ts}] {action} `{element}` on `{screen}`"
        if expected and actual:
            line += f" — expected: {expected}, got: {actual}"
        if correction:
            line += f" → CORRECTED: {correction}"
        lines.append(line)

    return "\n".join(lines)


def _get_elements_with_fallback(
    db: ScreenMapDB,
    device_profile_id: str,
    app_context: str,
    screen_name: str,
    resolution: str,
) -> List[Dict]:
    """Get elements for a screen, falling back to cross-device data if empty."""
    elements = db.get_all_elements_for_screen(device_profile_id, app_context, screen_name)
    if elements:
        return elements

    # Cross-device fallback: query all devices, find ones with matching resolution
    conn = db._get_conn()
    rows = conn.execute(
        """SELECT se.* FROM screen_elements se
           JOIN device_profiles dp ON se.device_profile_id = dp.id
           WHERE se.app_context = ? AND se.screen_name = ? AND dp.resolution = ?
           ORDER BY se.confidence DESC""",
        (app_context, screen_name, resolution),
    ).fetchall()

    if rows:
        # Also copy these into the current device profile for future use
        for row in rows:
            r = dict(row)
            db.upsert_element(
                device_profile_id=device_profile_id,
                app_context=app_context,
                screen_name=screen_name,
                element_name=r["element_name"],
                x=r["x"],
                y=r["y"],
                source="cross_device",
                element_type=r.get("element_type"),
                intent=r.get("intent"),
                confidence=0.3,
            )
        # Re-fetch (now under current device profile)
        return db.get_all_elements_for_screen(device_profile_id, app_context, screen_name)

    return []


def build_memory_section(db: ScreenMapDB, device_profile_id: str) -> str:
    """Build the dynamic memory section from the DB."""
    template = load_prompt_file("memory.md")
    resolution = device_profile_id.split(":")[-1] if ":" in device_profile_id else "1080x1920"

    # Platform coordinates
    platform_elements = []
    for screen in ["login", "otp", "home", "search_results", "game_header",
                    "keep_playing_modal", "fancash_prompt"]:
        platform_elements.extend(
            _get_elements_with_fallback(db, device_profile_id, "platform", screen, resolution)
        )
    platform_table = format_coordinates_table(platform_elements)

    # Game coordinates
    game_elements = _get_elements_with_fallback(
        db, device_profile_id, "slingo_cash_eruption", "main_game", resolution
    )
    game_table = format_coordinates_table(game_elements)

    # Signatures
    signatures = db.get_screen_signatures("platform")
    sig_text = format_signatures(signatures)

    # Recent observations
    observations = db.get_recent_observations(device_profile_id, limit=10)
    obs_text = format_observations(observations)

    # Inject into template
    result = template.replace("{{PLATFORM_COORDINATES}}", platform_table)
    result = result.replace("{{GAME_COORDINATES}}", game_table)
    result = result.replace("{{SCREEN_SIGNATURES}}", sig_text)
    result = result.replace("{{RECENT_OBSERVATIONS}}", obs_text)

    return result


def assemble_description(db: Optional[ScreenMapDB] = None) -> str:
    """Assemble the full agent description from all prompt files.

    Args:
        db: ScreenMapDB instance. If None, memory section uses static template.

    Returns:
        Complete agent description string.
    """
    # Load static files
    soul = load_prompt_file("soul.md")
    identity = load_prompt_file("identity.md")
    tools = load_prompt_file("tools.md")
    user = load_prompt_file("user.md")

    # Inject env vars into identity and user
    identity = inject_env_vars(identity)
    user = inject_env_vars(user)

    # Build memory section (dynamic from DB)
    if db:
        device_name = os.getenv("ANDROID_SERIAL", "emulator-5554")
        resolution = os.getenv("DEVICE_RESOLUTION", "1080x1920")
        profile_id = db.ensure_device_profile(device_name, resolution, "android")
        memory = build_memory_section(db, profile_id)
    else:
        memory = load_prompt_file("memory.md")
        memory = "<!-- DB not available — using template -->\n" + memory

    # Assemble in order: soul → identity → tools → memory → user
    sections = [soul, identity, tools, memory, user]
    return "\n\n---\n\n".join(sections)


def build_starter_prompt() -> str:
    """Build the starter prompt shown when the agent first greets the user."""
    email = os.getenv("TEST_EMAIL", "not configured")
    password_status = "configured" if os.getenv("TEST_PASSWORD") else "not configured"

    return (
        "Hello! I'm the **Slingo QA Agent (Android)**. I test Slingo Cash Eruption "
        "on the Fanatics Casino Android app via Appium.\n\n"
        "Here's what I can do:\n"
        "- **Run the full QA test** (launch → login → OTP → navigate → play → report)\n"
        "- **Take a screenshot** of the device\n"
        "- **Launch the casino app**\n"
        "- **Navigate** to Slingo Cash Eruption\n"
        "- **Play a round** (5 base spins, handle wilds, exit safely, report balance)\n\n"
        f"Test credentials: email={email}, password={password_status}\n"
        "Note: I'll ask you for the OTP code when it's sent via SMS.\n\n"
        "What would you like to do?"
    )


def build_example_conversation() -> str:
    """Build example conversation showing the OTP-aware flow."""
    serial = os.getenv("ANDROID_SERIAL", "emulator-5554")
    email = os.getenv("TEST_EMAIL", "test@example.com")

    return "\n ".join([
        "user: Run the full Slingo QA test.",
        "agent: Starting the full QA test. Selecting device first.",
        "user_confirmed_tool_run: <select_device>",
        f'tool_result: {{"device": "{serial}", "platform": "android"}}',
        "agent: Device connected. Launching Fanatics Casino.",
        "user_confirmed_tool_run: <appium_activate_app>",
        'tool_result: {"status": "success"}',
        "agent: App launched. Taking screenshot to detect current screen.",
        "user_confirmed_tool_run: <appium_screenshot>",
        "tool_result: [screenshot showing login screen with email and password fields]",
        "agent: Login screen detected. Using appium_find_element to locate the email field.",
        "user_confirmed_tool_run: <appium_find_element>",
        'tool_result: {"elements": [{"text": "", "class": "android.widget.EditText", "bounds": "[100,650][980,750]"}]}',
        f"agent: Email field found (elementId=abc123). Tapping and entering email: {email}",
        "user_confirmed_tool_run: <appium_click elementId='abc123'>",
        'tool_result: {"status": "success"}',
        f"user_confirmed_tool_run: <appium_set_value value='{email}'>",
        'tool_result: {"status": "success"}',
        "agent: Email entered. Now finding and filling the password field.",
        "user_confirmed_tool_run: <appium_find_element for password>",
        'tool_result: {"elements": [{"class": "android.widget.EditText", "elementId": "def456", "password": true}]}',
        "user_confirmed_tool_run: <appium_click elementId='def456'>",
        "user_confirmed_tool_run: <appium_set_value value='***'>",
        'tool_result: {"status": "success"}',
        "agent: Password entered. Tapping Sign In button.",
        "user_confirmed_tool_run: <appium_find_element for Sign In>",
        'tool_result: {"elements": [{"text": "Sign In", "elementId": "ghi789"}]}',
        "user_confirmed_tool_run: <appium_click elementId='ghi789'>",
        'tool_result: {"status": "success"}',
        "agent: Login submitted. Checking for OTP screen.",
        "user_confirmed_tool_run: <appium_screenshot>",
        "tool_result: [screenshot showing OTP verification screen with code input field]",
        "agent: OTP verification screen detected. I need the code sent to your phone via SMS. Please enter the OTP code here.",
        "user: 482916",
        "agent: Got it. Entering OTP code 482916.",
        "user_confirmed_tool_run: <appium_find_element for OTP input>",
        'tool_result: {"elements": [{"class": "android.widget.EditText", "elementId": "otp123"}]}',
        "user_confirmed_tool_run: <appium_click elementId='otp123'>",
        "user_confirmed_tool_run: <appium_set_value value='482916'>",
        'tool_result: {"status": "success"}',
        "agent: OTP entered. Submitting.",
        "user_confirmed_tool_run: <appium_find_element for submit>",
        'tool_result: {"elements": [{"text": "Verify", "elementId": "sub456"}]}',
        "user_confirmed_tool_run: <appium_click elementId='sub456'>",
        'tool_result: {"status": "success"}',
        "agent: OTP submitted. Verifying login succeeded.",
        "user_confirmed_tool_run: <appium_screenshot>",
        "tool_result: [screenshot showing Fanatics Casino home screen with search bar and featured games]",
        "agent: Login successful! Home screen detected. Reading starting balance and navigating to Slingo Cash Eruption.",
        "user_confirmed_tool_run: <appium_find_element for balance>",
        'tool_result: {"text": "$50.00"}',
        "agent: Starting balance: $50.00. Searching for Slingo Cash Eruption.",
        "user_confirmed_tool_run: <appium_find_element for search>",
        "user_confirmed_tool_run: <appium_find_element for search → appium_click elementId='search1'>",
        "user_confirmed_tool_run: <appium_set_value value='Slingo Cash Eruption'>",
        "user_confirmed_tool_run: <appium_screenshot>",
        "tool_result: [screenshot showing search results with Slingo Cash Eruption tile]",
        "agent: Game found. Tapping the game tile.",
        "user_confirmed_tool_run: <appium_swipe startX=540, startY=600, endX=540, endY=600>  (tap first result)",
        "tool_result: [game loading...]",
        "user_confirmed_tool_run: <appium_screenshot after 6s wait>",
        "tool_result: [screenshot showing Slingo Cash Eruption loaded with 5x5 grid, SPINS LEFT: 5]",
        "agent: Game loaded! 5 spins remaining. Starting spin 1.",
        "user_confirmed_tool_run: <appium_swipe startX=540, startY=1780, endX=540, endY=1780>  (tap spin button)",
        "user_confirmed_tool_run: <appium_screenshot after 4s>",
        "tool_result: [screenshot: WILD in column 3, SPINS LEFT: 4]",
        "agent: WILD in column 3. Selecting unmarked number in that column.",
        "user_confirmed_tool_run: <appium_swipe startX=540, startY=1050, endX=540, endY=1050>  (tap grid cell col3, row3)",
        "agent: Wild handled. Continuing spins 2-5...",
        "...(spins 2-5 proceed similarly)...",
        "tool_result: [screenshot: SPINS LEFT: 0, button shows SPIN FOR $0.30]",
        "agent: All 5 spins done. Extra spins offered — NOT purchasing. Exiting via native header close button.",
        "user_confirmed_tool_run: <appium_swipe startX=54, startY=130, endX=54, endY=130>  (tap native close button)",
        "user_confirmed_tool_run: <appium_find_element for Keep Playing modal>",
        'tool_result: {"elements": [{"text": "No thanks, exit", "elementId": "exit789"}]}',
        "user_confirmed_tool_run: <appium_click elementId='exit789'>",
        "user_confirmed_tool_run: <appium_find_element for balance>",
        'tool_result: {"text": "$49.80"}',
        "agent: Test complete!\n\n"
        "=== SLINGO QA TEST REPORT (ANDROID) ===\n"
        f"Device: {serial}\n"
        "Starting Balance: $50.00\n"
        "Ending Balance: $49.80\n"
        "Balance Delta: -$0.20\n"
        "Spins Played: 5/5\n"
        "Wilds Encountered: 1\n"
        "Super Wilds Encountered: 0\n"
        "Extra Spins Purchased: 0\n"
        "Anomalies: None\n"
        "Status: PASS",
    ])
