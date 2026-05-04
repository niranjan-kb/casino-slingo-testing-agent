"""goal_login — platform-agnostic capability goal.

Authenticates the casino app and confirms a logged-in home/lobby. Reused across
platforms (Android, iOS, web) — platform/build differences live in the screen-map DB.
"""

from goals.login.prompt_loader import (
    assemble_description,
    build_example_conversation,
    build_starter_prompt,
)
from models.tool_definitions import AgentGoal
from shared.mcp_config import get_appium_mcp_server_definition
from tools.tool_registry import (
    slingo_detect_screen_tool,
    slingo_find_element_with_fallback_tool,
    slingo_lookup_coords_tool,
    slingo_save_evidence_tool,
    slingo_smart_tap_tool,
    slingo_tap_coordinate_tool,
    slingo_verify_tap_tool,
    slingo_wait_seconds_tool,
)


# Appium-MCP tools needed for login (subset — no game-specific tools)
_LOGIN_APPIUM_TOOLS = [
    "appium_screenshot",
    "appium_click",
    "appium_set_value",
    "appium_get_text",
    "appium_find_element",
    "appium_get_page_source",
    "appium_app",
    "appium_alert",
    "appium_mobile_press_key",
    "appium_swipe",
    "create_session",
    "delete_session",
    "select_device",
]

# Local tools — only what login needs (no GenerateReport — login isn't the QA report owner)
_LOGIN_LOCAL_TOOLS = [
    slingo_smart_tap_tool,
    slingo_find_element_with_fallback_tool,
    slingo_wait_seconds_tool,
    slingo_tap_coordinate_tool,
    slingo_detect_screen_tool,
    slingo_lookup_coords_tool,
    slingo_verify_tap_tool,
    slingo_save_evidence_tool,
]


goal_login = AgentGoal(
    id="goal_login",
    category_tag="casino-qa",
    agent_name="Casino Login",
    agent_friendly_description=(
        "Authenticate the casino app end-to-end: launch, dismiss pre-login modals, "
        "Fanatics ONE 2-step login (email → password), OTP (auto in dev/test), and "
        "confirm a logged-in home/lobby. Platform-agnostic; learned coordinates "
        "are persisted per platform/build in the screen-map DB."
    ),
    tools=list(_LOGIN_LOCAL_TOOLS),
    mcp_server_definition=get_appium_mcp_server_definition(
        platform="android",
        included_tools=_LOGIN_APPIUM_TOOLS,
    ),
    description=assemble_description(),
    starter_prompt=build_starter_prompt(),
    example_conversation_history=build_example_conversation(),
)


login_goals = [goal_login]
