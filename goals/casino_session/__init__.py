"""goal_casino_session — platform-agnostic casino session profile.

Configures the toolset (Appium-MCP + screen-map DB tools) for any casino-app
intent: authenticate, navigate to a game, play, report. The per-turn objective
is driven by the intent registry; this module is the session's tool/MCP config.
Platform/build differences live in the screen-map DB, not in the goal name.
"""

from goals.casino_session.prompt_loader import (
    assemble_description,
    build_starter_prompt,
)
from models.tool_definitions import AgentGoal
from shared.mcp_config import get_appium_mcp_server_definition
from tools.tool_registry import (
    slingo_budget_check_tool,
    slingo_detect_screen_tool,
    slingo_find_element_with_fallback_tool,
    slingo_lookup_coords_tool,
    slingo_parse_session_intent_tool,
    slingo_read_balance_tool,
    slingo_resolve_directory_tool,
    slingo_save_evidence_tool,
    slingo_smart_tap_tool,
    slingo_tap_coordinate_tool,
    slingo_verify_tap_tool,
    slingo_wait_for_signature_tool,
    slingo_wait_seconds_tool,
)


_CASINO_SESSION_APPIUM_TOOLS = [
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
    "appium_scroll",  # T052 follow-up: intent_navigate_to_game's scroll-grid fallback
    "create_session",
    "delete_session",
    "select_device",
]

_CASINO_SESSION_LOCAL_TOOLS = [
    slingo_smart_tap_tool,
    slingo_find_element_with_fallback_tool,
    slingo_wait_seconds_tool,
    slingo_tap_coordinate_tool,
    slingo_detect_screen_tool,
    slingo_lookup_coords_tool,
    slingo_verify_tap_tool,
    slingo_save_evidence_tool,
    # Spec 005 (T036–T040): play-flow QA tools.
    slingo_parse_session_intent_tool,
    slingo_resolve_directory_tool,
    slingo_read_balance_tool,
    slingo_budget_check_tool,
    slingo_wait_for_signature_tool,
]


goal_casino_session = AgentGoal(
    id="goal_casino_session",
    category_tag="casino-qa",
    agent_name="Danny Ocean",
    agent_friendly_description=(
        "Run a casino-app session end-to-end. Per-turn objective is driven by "
        "the intent registry, sequenced by graphs/casino_session.yaml: "
        "intent_parse_session → intent_authenticate → intent_navigate_to_game → "
        "intent_load_game_context → intent_play_game (with optional "
        "intent_play_bonus branch) → intent_report. intent_navigate_to_screen "
        "is also available for off-graph navigation. Platform-agnostic; learned "
        "coordinates are persisted per platform/build in the screen-map DB."
    ),
    tools=list(_CASINO_SESSION_LOCAL_TOOLS),
    mcp_server_definition=get_appium_mcp_server_definition(
        platform="android",
        included_tools=_CASINO_SESSION_APPIUM_TOOLS,
    ),
    description=assemble_description(),
    starter_prompt=build_starter_prompt(),
    example_conversation_history="",
)


casino_session_goals = [goal_casino_session]
