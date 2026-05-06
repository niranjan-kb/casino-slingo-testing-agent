"""Casino QA agent goals — capability-named, casino-domain only.

The upstream `temporal-community/temporal-ai-agent` ships a zoo of demo
goals (Event Flight Finder, Schedule PTO, Pirate Treasure, etc.). None of
that belongs in a casino-QA agent. We register only the goals our agent
actually composes: login, navigate, play, etc.
"""

import os
from typing import List

import tools.tool_registry as tool_registry
from goals.casino_session import casino_session_goals
from goals.slingo_qa_android import slingo_qa_android_goals
from models.tool_definitions import AgentGoal


# Single source of truth for which goals the casino agent can run.
# Per-turn behavior is driven by the intent registry (intents/), not by goals.
goal_list: List[AgentGoal] = []
goal_list.extend(casino_session_goals)
goal_list.extend(slingo_qa_android_goals)


# Multi-goal mode is reserved for when we have ≥ 2 distinct goal *configurations*
# (e.g. casino-Android + sportsbook-web with different MCP servers). Today the
# canonical entry point is `AGENT_GOAL=goal_casino_session`. The picker
# (`goal_choose_agent_type`) was an upstream generic-platform construct and is
# no longer registered.
first_goal_value = (os.getenv("AGENT_GOAL") or "").strip().lower()
multi_goal_mode = first_goal_value == "goal_choose_agent_type"

if multi_goal_mode:
    # Future: register a casino-themed picker here. For now, falling back
    # to single-goal is safer than booting an unregistered picker.
    raise RuntimeError(
        "Multi-goal mode is not yet wired for casino. "
        "Set AGENT_GOAL=goal_casino_session (or another concrete goal id) in .env. "
        "When you have ≥3 casino capabilities, register a casino-themed picker."
    )
