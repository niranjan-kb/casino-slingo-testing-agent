"""Slingo QA Android goal — assembled from multi-file prompts + DB coordinates."""

from goals.slingo_qa_android.prompt_loader import (
    assemble_description,
    build_example_conversation,
    build_starter_prompt,
)
from models.tool_definitions import AgentGoal
from shared.mcp_config import get_appium_mcp_server_definition
from shared.screen_map_db import ScreenMapDB
from tools.tool_registry import (
    slingo_detect_screen_tool,
    slingo_generate_report_tool,
    slingo_lookup_element_coords_tool,
    slingo_save_evidence_tool,
    slingo_tap_mapped_tool,
    slingo_tap_coordinate_tool,
    slingo_verify_tap_tool,
    slingo_wait_seconds_tool,
)

# appium-mcp tools required for Android Slingo QA
_ANDROID_TOOLS = [
    "appium_screenshot",
    "appium_click",
    "appium_double_tap",
    "appium_set_value",
    "appium_get_text",
    "appium_find_element",
    "appium_get_page_source",
    "appium_app",
    "appium_context",
    "appium_mobile_press_key",
    "appium_alert",
    "appium_scroll",
    "appium_swipe",
    "create_session",
    "delete_session",
    "select_device",
]

# Local Python tools for the Slingo QA agent
_SLINGO_TOOLS = [
    slingo_tap_mapped_tool,
    slingo_wait_seconds_tool,
    slingo_tap_coordinate_tool,
    slingo_detect_screen_tool,
    slingo_lookup_element_coords_tool,
    slingo_verify_tap_tool,
    slingo_save_evidence_tool,
    slingo_generate_report_tool,
]


def build_goal(db: ScreenMapDB = None) -> AgentGoal:
    """Build the Slingo QA Android goal with prompts assembled from files + DB.

    Args:
        db: ScreenMapDB instance for loading dynamic coordinates.
            If None, coordinates from DB are not included (template only).
    """
    return AgentGoal(
        id="goal_slingo_qa_android",
        category_tag="casino-qa",
        agent_name="Slingo QA Agent (Android)",
        agent_friendly_description=(
            "Play Slingo Cash Eruption on the Fanatics Casino Android device via Appium "
            "and report QA results. Self-improving — learns coordinates per device over time. "
            "Supports login with OTP, game navigation, and full end-to-end test flows."
        ),
        tools=list(_SLINGO_TOOLS),
        mcp_server_definition=get_appium_mcp_server_definition(
            platform="android",
            included_tools=_ANDROID_TOOLS,
        ),
        description=assemble_description(db),
        starter_prompt=build_starter_prompt(),
        example_conversation_history=build_example_conversation(),
    )


# For backward compatibility — build without DB at import time.
# Workers that have a DB instance should call build_goal(db) instead.
goal_slingo_qa_android = build_goal()
slingo_qa_android_goals = [goal_slingo_qa_android]
