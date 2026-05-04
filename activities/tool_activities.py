import inspect
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from litellm import completion
from temporalio import activity
from temporalio.common import RawValue
from temporalio.exceptions import ApplicationError

from models.data_types import (
    EnvLookupInput,
    EnvLookupOutput,
    ToolPromptInput,
    ValidationInput,
    ValidationResult,
)
from models.tool_definitions import MCPServerDefinition
from shared.mcp_client_manager import MCPClientManager

# Import MCP client libraries
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
except ImportError:
    # Fallback if MCP not installed
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    sse_client = None

load_dotenv(override=True)

# Module-level persistent MCP manager — shared across all activity calls
_persistent_mcp_manager: Optional[MCPClientManager] = None


# Synthetic tool used as the LLM's structured-output channel.
#
# Every agent_toolPlanner LLM call forces tool_choice to this tool, so the
# model's output shape is guaranteed by the API instead of by prompt-prayer.
# The `tool` field inside this tool's arguments names the user-facing tool
# the orchestrator should run next (e.g. "appium_click", "FindElementWithFallback").
#
# We build the schema per-call so the `tool` field can be constrained to an
# enum of the tools actually available in the current goal — the model
# literally cannot emit a name that wasn't on the goal's tool list. This
# prevents hallucinations like `tool="ToolActivities.agent_toolPlanner"`.


def _build_plan_next_action_tool(allowed_tool_names: Optional[List[str]]) -> Dict[str, Any]:
    """Build the plan_next_action schema with `tool` constrained to a per-call enum.

    `allowed_tool_names` should be every user-facing tool name the agent is
    allowed to call this turn (native tools + MCP tools). When None or empty,
    `tool` is left as a free-form string (development fallback).
    """
    if allowed_tool_names:
        # Anthropic JSON Schema doesn't permit `enum` on a `["string", "null"]`
        # union directly, but it accepts `enum` containing both strings and
        # null. We use that form so the model can still set tool=null for
        # question/done/pick-new-goal steps.
        tool_field: Dict[str, Any] = {
            "type": ["string", "null"],
            "enum": [None, *sorted(set(allowed_tool_names))],
            "description": (
                "Name of the user-facing tool to run when next='confirm'. "
                "MUST be one of the tools listed in the enum. "
                "Set to null when next is 'question', 'pick-new-goal', or 'done'."
            ),
        }
    else:
        tool_field = {
            "type": ["string", "null"],
            "description": (
                "Name of the user-facing tool to run when next='confirm'. "
                "Must be exactly one of the tools listed in the system prompt. "
                "Set to null when next is 'question', 'pick-new-goal', or 'done'."
            ),
        }

    return {
        "type": "function",
        "function": {
            "name": "plan_next_action",
            "description": (
                "Emit the agent's next planning step. Always called exactly once per turn. "
                "The orchestrator dispatches based on the `next` and `tool` fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "next": {
                        "type": "string",
                        "enum": ["question", "confirm", "pick-new-goal", "done"],
                        "description": (
                            "What the orchestrator should do next. "
                            "'question' = ask the user for input via the `response` field. "
                            "'confirm' = run the named `tool` with `args`. "
                            "'pick-new-goal' = signal that the current goal is complete and a new one should be selected (multi-goal mode only). "
                            "'done' = end the conversation."
                        ),
                    },
                    "tool": tool_field,
                    "args": {
                        "type": "object",
                        "description": (
                            "Arguments for the named tool. Empty object {} when tool is null. "
                            "All values must match the tool's declared argument types and names."
                        ),
                        "additionalProperties": True,
                    },
                    "response": {
                        "type": "string",
                        "description": (
                            "Plain-text message shown to the user. May be a question (when next='question'), "
                            "a status update before running a tool (when next='confirm'), or a final summary (when next='done')."
                        ),
                    },
                },
                "required": ["next", "response"],
                "additionalProperties": False,
            },
        },
    }


def get_persistent_mcp_manager() -> Optional[MCPClientManager]:
    """Get the module-level persistent MCP manager (if running)."""
    global _persistent_mcp_manager
    if _persistent_mcp_manager and _persistent_mcp_manager.is_running:
        return _persistent_mcp_manager
    return None


def set_persistent_mcp_manager(manager: MCPClientManager) -> None:
    """Set the module-level persistent MCP manager (called from worker startup)."""
    global _persistent_mcp_manager
    _persistent_mcp_manager = manager


class ToolActivities:
    def __init__(self, mcp_client_manager: MCPClientManager = None):
        """Initialize LLM client using LiteLLM and optional MCP client manager"""
        self.llm_model = os.environ.get("LLM_MODEL", "openai/gpt-4")
        self.llm_key = os.environ.get("LLM_KEY")
        self.llm_base_url = os.environ.get("LLM_BASE_URL")
        self.mcp_client_manager = mcp_client_manager
        print(f"Initializing ToolActivities with LLM model: {self.llm_model}")
        if self.llm_base_url:
            print(f"Using custom base URL: {self.llm_base_url}")
        if self.mcp_client_manager:
            print("MCP client manager enabled for connection pooling")

    @activity.defn
    async def agent_validatePrompt(
        self, validation_input: ValidationInput
    ) -> ValidationResult:
        """
        ARCHIVED 2026-04-29 — no longer invoked by AgentGoalWorkflow.

        Reason: full LLM round-trip per user message for low ROI. The toolPlanner
        already handles off-topic input gracefully (returns next='question' with
        a clarifying response). Validator added ~500ms-2s + thousands of tokens
        per turn without measurably improving conversation quality.

        Kept here so it can be re-introduced (e.g. as a faster heuristic, or
        gated behind a STRICT_VALIDATION env flag) without recreating the
        plumbing. The activity is still registered with the worker on startup.

        Validates the prompt in the context of the conversation history and agent goal.
        Returns a ValidationResult indicating if the prompt makes sense given the context.
        """
        # Create simple context string describing tools and goals
        tools_description = []
        for tool in validation_input.agent_goal.tools:
            tool_str = f"Tool: {tool.name}\n"
            tool_str += f"Description: {tool.description}\n"
            tool_str += "Arguments: " + ", ".join(
                [f"{arg.name} ({arg.type})" for arg in tool.arguments]
            )
            tools_description.append(tool_str)
        tools_str = "\n".join(tools_description)

        # Convert conversation history to string
        history_str = json.dumps(validation_input.conversation_history, indent=2)

        # Create context instructions
        context_instructions = f"""The agent goal and tools are as follows:
            Description: {validation_input.agent_goal.description}
            Available Tools:
            {tools_str}
            The conversation history to date is:
            {history_str}"""

        # Create validation prompt
        validation_prompt = f"""The user's prompt is: "{validation_input.prompt}"
            Please validate if this prompt makes sense given the agent goal and conversation history.
            If the prompt makes sense toward the goal then validationResult should be true.
            If the prompt is wildly nonsensical or makes no sense toward the goal and current conversation history then validationResult should be false.
            If the response is low content such as "yes" or "that's right" then the user is probably responding to a previous prompt.  
             Therefore examine it in the context of the conversation history to determine if it makes sense and return true if it makes sense.
            Return ONLY a JSON object with the following structure:
                "validationResult": true/false,
                "validationFailedReason": "If validationResult is false, provide a clear explanation to the user in the response field 
                about why their request doesn't make sense in the context and what information they should provide instead.
                validationFailedReason should contain JSON in the format
                {{
                    "next": "question",
                    "response": "[your reason here and a response to get the user back on track with the agent goal]"
                }}
                If validationResult is true (the prompt makes sense), return an empty dict as its value {{}}"
            """

        # Call the LLM with the validation prompt
        prompt_input = ToolPromptInput(
            prompt=validation_prompt, context_instructions=context_instructions
        )

        result = await self.agent_toolPlanner(prompt_input)

        return ValidationResult(
            validationResult=result.get("validationResult", False),
            validationFailedReason=result.get("validationFailedReason", {}),
        )

    @activity.defn
    async def agent_toolPlanner(self, input: ToolPromptInput) -> dict:
        """Plan the next action via Anthropic tool-use forcing.

        We define a single synthetic tool, `plan_next_action`, whose schema is
        the structured shape we need (next/tool/args/response). LiteLLM forwards
        `tools=[...]` + `tool_choice` to Bedrock-Anthropic; the model MUST call
        that tool with arguments matching the schema. No JSON parsing, no prose
        slicing, no parse-and-pray. Structurally guaranteed by the model.
        """
        messages = [
            {
                "role": "system",
                "content": input.context_instructions
                + "\n\nCurrent date: "
                + datetime.now().strftime("%B %d, %Y"),
            },
            {
                "role": "user",
                "content": input.prompt,
            },
        ]

        # Build the planning tool with the goal's allowed tool names baked in
        # as an enum on the `tool` field. The model literally cannot hallucinate
        # a tool name not on this list.
        allowed_names = getattr(input, "allowed_tool_names", None) or []
        plan_tool = _build_plan_next_action_tool(allowed_names)

        completion_kwargs = {
            "model": self.llm_model,
            "messages": messages,
            "api_key": self.llm_key,
            "tools": [plan_tool],
            "tool_choice": {
                "type": "function",
                "function": {"name": "plan_next_action"},
            },
            # LiteLLM gates tool-use behind a per-model capability list. For
            # Bedrock-Anthropic, native tool-use works on every Sonnet/Opus
            # 3.5+ model, but LiteLLM only auto-enables it for ids it has in
            # its registry. Force-allow these params so tool-use forcing works
            # for newer models LiteLLM hasn't catalogued yet.
            "allowed_openai_params": ["tools", "tool_choice"],
        }
        if self.llm_base_url:
            completion_kwargs["base_url"] = self.llm_base_url

        try:
            response = completion(**completion_kwargs)
        except Exception as e:
            activity.logger.error(f"LLM completion failed: {e}")
            raise

        return self._extract_planned_action(response)

    @staticmethod
    def _extract_planned_action(response: Any) -> dict:
        """Pull the structured plan out of a forced-tool-use response.

        LiteLLM normalises Anthropic's `tool_use` blocks into OpenAI-style
        `message.tool_calls`. With `tool_choice` forced, exactly one call to
        `plan_next_action` is guaranteed; its `.function.arguments` field is a
        JSON string of the validated schema.
        """
        try:
            choice = response.choices[0]
            tool_calls = getattr(choice.message, "tool_calls", None) or []
        except (AttributeError, IndexError) as e:
            raise ApplicationError(
                f"LLM response missing choices/message: {e!r}"
            ) from e

        if not tool_calls:
            # Defensive fallback: model returned plain text despite tool_choice.
            # This should never happen on Anthropic with tool_choice forced;
            # log loudly and try to salvage the content as JSON.
            content = getattr(choice.message, "content", "") or ""
            activity.logger.error(
                "LLM returned no tool_calls despite forced tool_choice. "
                f"Content fallback: {content[:500]!r}"
            )
            raise ApplicationError(
                "Model did not call plan_next_action — structured output broken"
            )

        call = tool_calls[0]
        try:
            args_json = call.function.arguments
        except AttributeError as e:
            raise ApplicationError(
                f"tool_call shape unexpected: {call!r}"
            ) from e

        try:
            data = json.loads(args_json) if isinstance(args_json, str) else args_json
        except json.JSONDecodeError as e:
            # The model is supposed to give us JSON, but if Bedrock ever
            # surfaces invalid JSON we want the failure visible, not silent.
            activity.logger.error(
                f"plan_next_action arguments not valid JSON: {args_json!r}"
            )
            raise ApplicationError(f"Invalid JSON from plan_next_action: {e}") from e

        # Normalise: ensure required-ish fields exist downstream (workflow
        # reads tool_data.get('next'), get('tool'), get('args'), get('response')).
        data.setdefault("next", "question")
        data.setdefault("tool", None)
        data.setdefault("args", {})
        data.setdefault("response", "")

        activity.logger.info(
            f"Planned action: next={data['next']} tool={data['tool']} "
            f"response={str(data.get('response', ''))[:160]!r}"
        )
        return data

    @activity.defn
    async def get_wf_env_vars(self, input: EnvLookupInput) -> EnvLookupOutput:
        """gets env vars for workflow as an activity result so it's deterministic
        handles default/None
        """
        output: EnvLookupOutput = EnvLookupOutput(
            show_confirm=input.show_confirm_default, multi_goal_mode=False
        )
        show_confirm_value = os.getenv(input.show_confirm_env_var_name)
        if show_confirm_value is None:
            output.show_confirm = input.show_confirm_default
        elif show_confirm_value is not None and show_confirm_value.lower() == "false":
            output.show_confirm = False
        else:
            output.show_confirm = True

        first_goal_value = os.getenv("AGENT_GOAL")
        if first_goal_value is None:
            output.multi_goal_mode = False  # default to single agent mode if unset
        elif (
            first_goal_value is not None
            and first_goal_value.lower() == "goal_choose_agent_type"
        ):
            output.multi_goal_mode = True
        else:
            output.multi_goal_mode = False

        return output

    @activity.defn
    async def mcp_tool_activity(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """MCP Tool - now using pooled connections"""
        activity.logger.info(f"Executing MCP tool: {tool_name} with args: {tool_args}")

        # Extract server definition
        server_definition = tool_args.pop("server_definition", None)

        if self.mcp_client_manager:
            # Use pooled connection
            return await self._execute_mcp_tool_pooled(
                tool_name, tool_args, server_definition
            )
        else:
            # Fallback to original implementation
            return await _execute_mcp_tool(tool_name, tool_args, server_definition)

    async def _execute_mcp_tool_pooled(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        server_definition: MCPServerDefinition | Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        """Execute MCP tool using pooled client connection"""
        activity.logger.info(f"Executing MCP tool with pooled connection: {tool_name}")

        # Convert argument types for MCP tools
        converted_args = _convert_args_types(tool_args)

        try:
            # Get pooled client
            client = await self.mcp_client_manager.get_client(server_definition)

            # Call the tool using existing client session
            result = await client.call_tool(tool_name, arguments=converted_args)
            normalized_result = _normalize_result(result)

            return {
                "tool": tool_name,
                "success": True,
                "content": normalized_result,
            }
        except Exception as e:
            activity.logger.error(f"MCP tool {tool_name} failed: {str(e)}")
            return {
                "tool": tool_name,
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }


@activity.defn(dynamic=True)
async def dynamic_tool_activity(args: Sequence[RawValue]) -> dict:
    from tools import get_handler

    tool_name = activity.info().activity_type  # e.g. "FindEvents"
    tool_args = activity.payload_converter().from_payload(args[0].payload, dict)
    activity.logger.info(f"Running dynamic tool '{tool_name}' with args: {tool_args}")

    # Check if this is an MCP tool call by looking for server_definition in args
    server_definition = tool_args.pop("server_definition", None)

    if server_definition:
        # This is an MCP tool call - handle it directly
        activity.logger.info(f"Executing MCP tool: {tool_name}")
        return await _execute_mcp_tool(tool_name, tool_args, server_definition)
    else:
        # This is a regular tool - delegate to the relevant function
        handler = get_handler(tool_name)
        if inspect.iscoroutinefunction(handler):
            result = await handler(tool_args)
        else:
            result = handler(tool_args)

        # Optionally log or augment the result
        activity.logger.info(f"Tool '{tool_name}' result: {result}")
        return result


# MCP Client Activities


def _build_connection(
    server_definition: MCPServerDefinition | Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Build connection parameters from MCPServerDefinition or dict"""
    if server_definition is None:
        # Default to stdio connection with the main server
        return {"type": "stdio", "command": "python", "args": ["server.py"], "env": {}}

    # Handle both MCPServerDefinition objects and dicts (from Temporal serialization)
    if isinstance(server_definition, dict):
        return {
            "type": server_definition.get("connection_type", "stdio"),
            "command": server_definition.get("command", "python"),
            "args": server_definition.get("args", ["server.py"]),
            "env": server_definition.get("env", {}) or {},
            "sse_url": server_definition.get("sse_url"),
        }

    return {
        "type": server_definition.connection_type,
        "command": server_definition.command,
        "args": server_definition.args,
        "env": server_definition.env or {},
        "sse_url": getattr(server_definition, "sse_url", None),
    }


def _normalize_result(result: Any) -> Any:
    """Normalize MCP tool result for serialization.

    Large image payloads (base64 screenshots) are saved to files to avoid
    exceeding Temporal's ~2MB payload limit.
    """
    if hasattr(result, "content"):
        if hasattr(result.content, "__iter__") and not isinstance(result.content, str):
            normalized = []
            for item in result.content:
                item_type = getattr(item, "type", None)

                # Handle base64 image content — save to file
                if item_type == "image" and hasattr(item, "data"):
                    filepath = _save_screenshot(item.data, getattr(item, "mimeType", "image/png"))
                    normalized.append(f"Screenshot saved to: {filepath}")
                elif hasattr(item, "text"):
                    text = item.text
                    # Catch base64-encoded images embedded in text fields
                    if len(text) > 50000 and ("base64" in text[:200].lower() or text[:20].startswith("iVBOR")):
                        filepath = _save_screenshot(text, "image/png")
                        normalized.append(f"Screenshot saved to: {filepath}")
                    else:
                        copied = _copy_external_screenshot(text)
                        normalized.append(copied if copied else text)
                else:
                    s = str(item)
                    if len(s) > 50000:
                        normalized.append(s[:500] + f"... [truncated, {len(s)} chars total]")
                    else:
                        normalized.append(s)
            return normalized
        return str(result.content)
    return result


_EXTERNAL_SCREENSHOT_RE = re.compile(
    r"(/(?:[^\s\"'`<>|]+/)?screenshot[_\-]?[^\s\"'`<>|]*\.(?:png|jpe?g))",
    re.IGNORECASE,
)


def _copy_external_screenshot(text: str) -> Optional[str]:
    """If `text` references an existing image file outside our screenshots dir,
    copy it into ./screenshots/ so the API/sidebar can serve it.

    Returns a replacement message containing the new path, or None if nothing
    was copied (text passes through unchanged).
    """
    if not text or len(text) > 4000:
        return None

    match = _EXTERNAL_SCREENSHOT_RE.search(text)
    if not match:
        return None

    src = match.group(1)
    if not os.path.isfile(src):
        return None

    screenshots_dir = os.path.join(os.getcwd(), "screenshots")
    if os.path.commonpath([os.path.abspath(src), os.path.abspath(screenshots_dir)]) == os.path.abspath(screenshots_dir):
        return None  # already inside our dir

    os.makedirs(screenshots_dir, exist_ok=True)
    ext = os.path.splitext(src)[1].lower().lstrip(".") or "png"
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
    dest = os.path.join(screenshots_dir, f"screenshot_{timestamp}.{ext}")

    try:
        shutil.copyfile(src, dest)
    except OSError as e:
        activity.logger.warning(f"Failed to copy screenshot {src} -> {dest}: {e}")
        return None

    activity.logger.info(f"Screenshot copied: {src} -> {dest}")
    return f"Screenshot saved to: {dest}"


def _save_screenshot(data: str, mime_type: str = "image/png") -> str:
    """Save base64 screenshot data to a file and return the path."""
    import base64

    screenshots_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    ext = "png" if "png" in mime_type else "jpg"
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    filepath = os.path.join(screenshots_dir, f"screenshot_{timestamp}.{ext}")

    # Remove data URI prefix if present
    if "," in data[:100]:
        data = data.split(",", 1)[1]

    with open(filepath, "wb") as f:
        f.write(base64.b64decode(data))

    logger_msg = f"Screenshot saved: {filepath} ({os.path.getsize(filepath)} bytes)"
    activity.logger.info(logger_msg)
    return filepath


_STRING_ONLY_KEYS = frozenset({
    "text",        # appium_set_value
    "value",       # legacy alias
    "selector",    # appium_find_element
    "strategy",    # appium_find_element
    "elementUUID", # appium_click / set_value / get_text
    "elementId",   # legacy
    "id",          # appium_app id (package name)
    "key",         # appium_mobile_press_key
    "context",     # appium_context
    "label",       # SaveEvidence / GenerateReport
    "app_context",
    "screen_name",
    "element_name",
    "expected_screen",
    "platform",
    "deviceUdid",
    "action",      # appium_app, appium_alert, appium_context
})


def _convert_args_types(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Convert string arguments to appropriate types for MCP tools.

    NOTE: Numeric-looking strings on string-only keys (e.g. an OTP `text="864408"`)
    must NOT be coerced to int — the MCP server rejects them as type-mismatched.
    """
    converted_args = {}

    for key, value in tool_args.items():
        if key == "server_definition":
            # Skip server_definition - it's metadata
            continue

        if key in _STRING_ONLY_KEYS:
            # Preserve as-is; coercion would corrupt OTPs, package names, etc.
            converted_args[key] = value
            continue

        if isinstance(value, str):
            # Try to convert string values to appropriate types
            if value.isdigit():
                # Convert numeric strings to integers
                converted_args[key] = int(value)
            elif value.replace(".", "").isdigit() and value.count(".") == 1:
                # Convert decimal strings to floats
                converted_args[key] = float(value)
            elif value.lower() in ("true", "false"):
                # Convert boolean strings
                converted_args[key] = value.lower() == "true"
            else:
                # Keep as string
                converted_args[key] = value
        else:
            # Keep non-string values as-is
            converted_args[key] = value

    return converted_args


async def _execute_mcp_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    server_definition: MCPServerDefinition | Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Execute an MCP tool with the given arguments and server definition"""
    activity.logger.info(f"Executing MCP tool: {tool_name}")

    # Convert argument types for MCP tools
    converted_args = _convert_args_types(tool_args)
    connection = _build_connection(server_definition)

    try:
        if connection["type"] == "sse" and connection.get("sse_url"):
            # Use the persistent manager (keeps session alive across calls)
            manager = get_persistent_mcp_manager()
            if manager:
                activity.logger.info(
                    f"Using persistent MCP manager for {tool_name}"
                )
                result = await manager.call_tool(tool_name, converted_args)
                activity.logger.info(f"MCP tool {tool_name} returned result: {result}")
                normalized_result = _normalize_result(result)
                activity.logger.info(f"MCP tool {tool_name} completed successfully")
                return {
                    "tool": tool_name,
                    "success": True,
                    "content": normalized_result,
                }
            else:
                # Fallback: ephemeral SSE connection (session won't persist)
                activity.logger.warning(
                    "Persistent MCP manager not available, using ephemeral SSE connection"
                )
                return await _execute_via_sse(
                    tool_name, converted_args, connection["sse_url"]
                )

        elif connection["type"] == "stdio":
            # Handle stdio connection (spawns new process per call)
            async with _stdio_connection(
                command=connection.get("command", "python"),
                args=connection.get("args", ["server.py"]),
                env=connection.get("env", {}),
            ) as (read, write):
                return await _call_mcp_tool(tool_name, converted_args, read, write)

        else:
            raise ApplicationError(f"Unsupported connection type: {connection['type']}")

    except Exception as e:
        activity.logger.error(f"MCP tool {tool_name} failed: {str(e)}")

        # Return error information
        return {
            "tool": tool_name,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


async def _call_mcp_tool(
    tool_name: str, converted_args: Dict[str, Any], read, write
) -> Dict[str, Any]:
    """Call an MCP tool over an established read/write connection"""
    async with ClientSession(read, write) as session:
        activity.logger.info(f"Initializing MCP session for {tool_name}")
        await session.initialize()
        activity.logger.info(f"MCP session initialized for {tool_name}")

        activity.logger.info(
            f"Calling MCP tool {tool_name} with args: {converted_args}"
        )
        try:
            result = await session.call_tool(tool_name, arguments=converted_args)
            activity.logger.info(f"MCP tool {tool_name} returned result: {result}")
        except Exception as tool_exc:
            activity.logger.error(
                f"MCP tool {tool_name} call failed: {type(tool_exc).__name__}: {tool_exc}"
            )
            raise

        normalized_result = _normalize_result(result)
        activity.logger.info(f"MCP tool {tool_name} completed successfully")

        return {
            "tool": tool_name,
            "success": True,
            "content": normalized_result,
        }


async def _execute_via_sse(
    tool_name: str, converted_args: Dict[str, Any], sse_url: str
) -> Dict[str, Any]:
    """Execute an MCP tool via SSE connection to a persistent server"""
    if sse_client is None:
        raise ApplicationError("MCP SSE client not available")

    activity.logger.info(f"Connecting to MCP server via SSE: {sse_url}")
    async with sse_client(sse_url) as (read, write):
        return await _call_mcp_tool(tool_name, converted_args, read, write)


@asynccontextmanager
async def _stdio_connection(command: str, args: list, env: dict):
    """Create stdio connection to MCP server"""
    if stdio_client is None:
        raise ApplicationError("MCP client libraries not available")

    # Explicitly pass os.environ so the subprocess inherits PATH, ANDROID_HOME, etc.
    # StdioServerParameters(env=None) may not reliably inherit the parent env in all MCP client versions.
    # Merge any non-empty overrides from the caller on top of the full parent environment.
    merged_env = dict(os.environ)
    if env:
        for k, v in env.items():
            if v:  # only override with non-empty values
                merged_env[k] = v
    server_params = StdioServerParameters(command=command, args=args, env=merged_env)

    async with stdio_client(server_params) as (read, write):
        yield read, write


@activity.defn
async def mcp_list_tools(
    server_definition: MCPServerDefinition, include_tools: Optional[List[str]] = None
) -> Dict[str, Any]:
    """List available MCP tools from the specified server"""

    activity.logger.info(f"Listing MCP tools for server: {server_definition.name}")

    connection = _build_connection(server_definition)

    async def _list_tools_on_session(read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            tools_info = {}
            for tool in tools_response.tools:
                if include_tools is None or tool.name in include_tools:
                    tools_info[tool.name] = {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": (
                            tool.inputSchema.model_dump()
                            if hasattr(tool.inputSchema, "model_dump")
                            else str(tool.inputSchema)
                        ),
                    }
            activity.logger.info(
                f"Found {len(tools_info)} tools for server {server_definition.name}"
            )
            return {
                "server_name": server_definition.name,
                "success": True,
                "tools": tools_info,
                "total_available": len(tools_response.tools),
                "filtered_count": len(tools_info),
            }

    try:
        if connection["type"] == "sse" and connection.get("sse_url"):
            async with sse_client(connection["sse_url"]) as (read, write):
                return await _list_tools_on_session(read, write)

        elif connection["type"] == "stdio":
            async with _stdio_connection(
                command=connection.get("command", "python"),
                args=connection.get("args", ["server.py"]),
                env=connection.get("env", {}),
            ) as (read, write):
                return await _list_tools_on_session(read, write)

        else:
            raise ApplicationError(f"Unsupported connection type: {connection['type']}")

    except Exception as e:
        activity.logger.error(
            f"Failed to list tools for server {server_definition.name}: {str(e)}"
        )

        return {
            "server_name": server_definition.name,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
