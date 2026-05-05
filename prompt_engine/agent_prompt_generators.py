"""LLM prompt assembly for the Casino QA agent.

The agent_toolPlanner activity uses Anthropic tool-use forcing
(`tool_choice={"type": "function", "function": {"name": "plan_next_action"}}`),
so the model's output shape is structurally guaranteed and we no longer have
to beg for valid JSON in the prompt. That lets these generators stay focused
on the actual content the model needs: the goal, the tools, the recent
conversation, and the decision rules — nothing else.

Sections produced (in order):

    # <Agent name>
    <goal description — soul + identity + tools.md + user.md>

    ## Tools
    <one canonical list of tools with name, description, args>

    ## Conversation so far
    <conversation history, with large items truncated>

    ## Example conversation                  (only if the goal provides one)
    <agent_goal.example_conversation_history>

    ## Decision rules                        (terse, domain-agnostic)
    <how to choose `next` and `tool`>

    ## Validate this proposed action         (only when raw_json is supplied)
    <previously-emitted plan to double-check>

The structured response shape (next/tool/args/response) is documented inside
the plan_next_action tool schema — the model already sees it from the
forced-tool-use machinery, so we don't restate it here.
"""

import json
from typing import Any, Dict, List, Optional

from models.tool_definitions import AgentGoal


# Truncation thresholds for the conversation history. Page-source XML dumps
# from appium-mcp can run >30k chars; replaying every one of them on every
# turn drowns the prompt and pushes useful context out of the window.
_MAX_MESSAGE_CHARS = 4000
_MAX_HISTORY_MESSAGES = 80


def generate_genai_prompt(
    agent_goal: AgentGoal,
    conversation_history: Any,
    multi_goal_mode: bool,
    raw_json: Optional[str] = None,
    mcp_tools_info: Optional[dict] = None,
) -> str:
    """Build the system-message text for the toolPlanner LLM call."""
    sections: List[str] = []

    # 1. Goal — the long-form persona + identity + phase logic
    sections.append(
        f"# {agent_goal.agent_name}\n\n{agent_goal.description}"
    )

    # 2. Tools — single canonical listing (the upstream listed twice).
    sections.append(_format_tools(agent_goal, mcp_tools_info))

    # 3. Conversation so far, with large entries elided so we don't drown
    #    the window in stale page_source dumps.
    sections.append(_format_history(conversation_history))

    # 4. Optional few-shot example provided by the goal definition.
    if agent_goal.example_conversation_history:
        sections.append(
            "## Example conversation flow\n\n"
            f"{agent_goal.example_conversation_history}"
        )

    # 5. Decision rules — terse, no domain-specific examples bleeding in.
    sections.append(_decision_rules(multi_goal_mode))

    # 6. Validation mode — re-evaluate a previously-proposed plan.
    if raw_json is not None:
        sections.append(
            "## Validate this proposed action\n\n"
            "A previous turn proposed the action below. Re-evaluate it given "
            "the current conversation history; correct any wrong tool/args/next, "
            "or accept it as-is by re-emitting the same shape via plan_next_action.\n\n"
            f"```json\n{json.dumps(raw_json, indent=2)}\n```"
        )

    return "\n\n---\n\n".join(sections)


# ----- Section builders ----------------------------------------------------


def _format_tools(agent_goal: AgentGoal, mcp_tools_info: Optional[dict]) -> str:
    """Render the tool catalog the model can choose from.

    We list every tool exactly once. Native tools (declared on the goal) and
    MCP-provided tools (auto-discovered at workflow start) are merged into a
    single section so the model has one place to look.
    """
    lines: List[str] = ["## Tools"]
    seen: set[str] = set()

    # Native tools declared on the goal.
    for tool in agent_goal.tools:
        if tool.name in seen:
            continue
        seen.add(tool.name)
        lines.append(_render_tool(
            name=tool.name,
            description=tool.description,
            args=[(a.name, a.type, a.description) for a in tool.arguments],
        ))

    # MCP tools discovered at runtime.
    if mcp_tools_info and mcp_tools_info.get("success"):
        for tool_name, info in (mcp_tools_info.get("tools") or {}).items():
            if tool_name in seen:
                continue
            seen.add(tool_name)
            args = _mcp_tool_args(info.get("inputSchema"))
            lines.append(_render_tool(
                name=tool_name,
                description=info.get("description", ""),
                args=args,
            ))

    return "\n".join(lines)


def _render_tool(name: str, description: str, args: List[tuple]) -> str:
    out = [f"\n### {name}", description.strip() or "(no description)"]
    if args:
        out.append("Arguments:")
        for arg_name, arg_type, arg_desc in args:
            out.append(f"  - `{arg_name}` ({arg_type}): {arg_desc}")
    else:
        out.append("Arguments: none")
    return "\n".join(out)


def _mcp_tool_args(input_schema: Any) -> List[tuple]:
    """Pull (name, type, description) tuples out of an MCP tool's JSON schema.

    MCP returns either a Pydantic model dump or a string fallback; we handle
    the dump shape and gracefully give up on the string.
    """
    if not isinstance(input_schema, dict):
        return []
    properties = input_schema.get("properties") or {}
    if not isinstance(properties, dict):
        return []
    out: List[tuple] = []
    for arg_name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        out.append((
            arg_name,
            spec.get("type", "any"),
            spec.get("description", ""),
        ))
    return out


def _format_history(conversation_history: Any) -> str:
    """Render the conversation history, eliding oversized entries.

    A few rules:
    - The most recent {_MAX_HISTORY_MESSAGES} messages are kept; older ones
      get a one-line summary.
    - Any single message whose serialised body exceeds {_MAX_MESSAGE_CHARS}
      is truncated with a marker so the model knows the original was longer.
    - This keeps the prompt bounded even after long page-source dumps or
      verbose tool results.
    """
    if not conversation_history:
        return "## Conversation so far\n\n(empty)"

    messages = (
        conversation_history.get("messages")
        if isinstance(conversation_history, dict)
        else conversation_history
    ) or []

    skipped = 0
    if len(messages) > _MAX_HISTORY_MESSAGES:
        skipped = len(messages) - _MAX_HISTORY_MESSAGES
        messages = messages[-_MAX_HISTORY_MESSAGES:]

    lines: List[str] = ["## Conversation so far"]
    if skipped:
        lines.append(f"_({skipped} earlier message(s) omitted to keep the prompt bounded.)_\n")

    for msg in messages:
        actor = msg.get("actor", "unknown") if isinstance(msg, dict) else "unknown"
        body = msg.get("response", "") if isinstance(msg, dict) else msg
        rendered = body if isinstance(body, str) else json.dumps(body, default=str)
        if len(rendered) > _MAX_MESSAGE_CHARS:
            head = rendered[: _MAX_MESSAGE_CHARS - 100]
            rendered = (
                f"{head}\n[…truncated, original was {len(rendered)} chars; "
                f"call appium_get_page_source again if you need the latest tree]"
            )
        lines.append(f"\n**{actor}:**\n{rendered}")

    return "\n".join(lines)


def _decision_rules(multi_goal_mode: bool) -> str:
    """Concise decision policy. The shape of the response is enforced by
    plan_next_action's schema, so we don't need to repeat it here.
    """
    if multi_goal_mode:
        pick_new_goal_rule = (
            "- `pick-new-goal` — ONLY after the **current** goal's phases have actually "
            "executed (i.e. you've already run real tools from this goal and the goal "
            "description's phase list is fully satisfied). **Never** emit `pick-new-goal` "
            "immediately after `ChangeGoal` — the new goal's Phase 0 starts on the very "
            "next turn; pick the first phase's tool with `next='confirm'`."
        )
    else:
        pick_new_goal_rule = "- `next` must never be `'pick-new-goal'` (single-goal mode)."

    return (
        "## Decision rules\n\n"
        "Each turn, you call `plan_next_action` exactly once. Pick `next` from:\n"
        "- `confirm` — you have a tool to run AND every required argument is filled. "
        "Set `tool` to the tool's name and put its arguments in `args`. **This is your "
        "default** whenever the goal description has a next phase to execute.\n"
        "- `question` — you need information from the user that you cannot infer. "
        "Set `tool=null`, put the question in `response`. **Use this sparingly.** "
        "Routine selector misses, screen re-classification, MCP retries — recover "
        "by trying the next strategy from the goal's phases instead of asking.\n"
        f"{pick_new_goal_rule}\n"
        "- `done` — the user has indicated the conversation should end.\n\n"
        "**Goal switches:** when `ChangeGoal` returns `{new_goal: ...}` in the "
        "previous tool result, treat the next turn as the start of that goal's Phase 0. "
        "Do NOT emit `pick-new-goal` to celebrate the switch — emit `confirm` with the "
        "first phase's tool. The switch itself is not the work; the work is the phases.\n\n"
        "When `confirm`-ing a tool: prefer args inferable from the conversation "
        "history (UUIDs from prior `appium_find_element` results, env values "
        "rendered into the goal description, etc.). Don't invent values you "
        "haven't seen — if you can't ground an arg, dump page-source or take "
        "a screenshot first.\n\n"
        "Always put a brief plain-text status in `response` — what you're "
        "about to do, or what you just learned. The user reads it."
    )


# ----- Per-event prompt fragments (appended to the prompt queue) -----------


def generate_tool_completion_prompt(
    current_tool: str,
    dynamic_result: dict,
    multi_goal_mode: bool = False,
) -> str:
    """User-role message handed to the next planner turn after a tool runs.

    Kept terse. The system prompt already explains the schema and decision
    rules; we just need to deliver the result and ask "what next?".
    """
    end_state = (
        "If every phase in the goal is complete, set `next='pick-new-goal'`."
        if multi_goal_mode
        else "If every phase in the goal is complete, set `next='done'`."
    )
    return (
        f"### Tool `{current_tool}` completed.\n\n"
        f"Result:\n```json\n{json.dumps(dynamic_result, default=str, indent=2)}\n```\n\n"
        f"Decide the next step using `plan_next_action`. {end_state}"
    )


def generate_missing_args_prompt(
    current_tool: str,
    tool_data: dict,
    missing_args: list[str],
) -> str:
    """User-role message asking the planner to fill in missing required args."""
    response_so_far = tool_data.get("response", "") if isinstance(tool_data, dict) else ""
    return (
        f"### Tool `{current_tool}` is missing required arguments: "
        f"{', '.join(missing_args)}.\n\n"
        f"Re-emit `plan_next_action` with `next='question'`, `tool=null`, "
        f"and a `response` that asks for those values. Reuse this status, then "
        f"append the question:\n\n{response_so_far}"
    )


# ----- Compatibility shims -------------------------------------------------
#
# Older code paths (tests, future activities) may still import these helpers.
# They were originally global-state singletons; now they're pure parameters.
# Keep the names but deprecate via behaviour.


def set_multi_goal_mode_if_unset(_mode: bool) -> None:  # pragma: no cover
    """Deprecated. Multi-goal mode is now passed explicitly to every generator."""
    return None


def is_multi_goal_mode() -> bool:  # pragma: no cover
    """Deprecated. Multi-goal mode is now passed explicitly to every generator."""
    return False


def generate_pick_new_goal_guidance(multi_goal_mode: bool = False) -> str:  # pragma: no cover
    """Deprecated. Decision rules are inlined into _decision_rules()."""
    if multi_goal_mode:
        return (
            "Set `next='pick-new-goal'` only when every phase in the goal description "
            "is complete or the user explicitly asks to switch."
        )
    return "`next` must never be `'pick-new-goal'` in single-goal mode."


def generate_toolchain_complete_guidance(multi_goal_mode: bool = False) -> str:  # pragma: no cover
    """Deprecated. Decision rules are inlined into _decision_rules()."""
    if multi_goal_mode:
        return "Set `next='pick-new-goal'` and `tool=null`."
    return "Set `next='done'` and `tool=null`."
