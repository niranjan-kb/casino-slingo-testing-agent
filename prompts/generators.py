"""LLM prompt assembly for the Casino QA agent.

The agent_toolPlanner activity uses Anthropic tool-use forcing
(`tool_choice={"type": "function", "function": {"name": "plan_next_action"}}`),
so the model's output shape is structurally guaranteed and we no longer have
to beg for valid JSON in the prompt. That lets these generators stay focused
on the actual content the model needs.

Sections produced (in order, layered per setup-doc §5 / spec 005):

    L0  # <Agent name>                            persona + identity (cacheable)
    L1  ## Tools                                  filtered by active intent (cacheable)
    L2  ## Active intent                          spec-004 intent body
    L3  ## Runtime facts                          (TBD — supplied by caller)
    L4  ## Game knowledge                         playbook + kind file (spec 005 T026)
    L5  ## Conversation so far                    last-N verbatim + summaries (T027)
    L6  ## Example conversation                   (only if the goal provides one)
    L7  ## Decision rules                         (terse, domain-agnostic)

Spec 005 deltas applied here (additive — defaults preserve legacy behaviour):
    T024  page-source XML stripped from history → {hash, len, hint} stub
    T025  tool list filtered by active_intent via tools/registry/<Tool>.yaml
    T026  game-knowledge layer injected on loaded-game signature
    T027  history compactor: last N=2 verbatim, older → 1-line summaries
    T028  cache_control hooks (deferred — requires tool_activities.py touch)

The structured response shape (next/tool/args/response/active_intent) is
documented inside the plan_next_action tool schema — the model sees it from
the forced-tool-use machinery, so we don't restate it here.
"""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Set

from models.tool_definitions import AgentGoal


# Truncation thresholds for the conversation history. Page-source XML dumps
# from appium-mcp can run >30k chars; replaying every one of them on every
# turn drowns the prompt and pushes useful context out of the window.
_MAX_MESSAGE_CHARS = 4000
_MAX_HISTORY_MESSAGES = 80

# Spec 005 T027: last-N verbatim, older → 1-line summary lines.
_VERBATIM_RECENT_TURNS = int(os.getenv("PROMPT_VERBATIM_RECENT_TURNS", "2"))

# Spec 005 T024: any string in a tool result longer than this and starting with
# '<' (or containing '<hierarchy') is treated as page-source / XML and stubbed.
_XML_STUB_THRESHOLD_CHARS = 1200

# Spec 005 T025/T026: registries on disk. Use os.path (NOT pathlib.Path.resolve)
# because this module is imported into the Temporal workflow sandbox, which
# restricts pathlib path-resolution methods. os.path.abspath is permitted —
# matches the pattern used by workflows/agent_goal_workflow.py itself.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOL_REGISTRY_DIR = os.path.join(_REPO_ROOT, "tools", "registry")
_GAME_KINDS_DIR = os.path.join(_REPO_ROOT, "game_kinds")


def generate_genai_prompt(
    agent_goal: AgentGoal,
    conversation_history: Any,
    multi_goal_mode: bool,
    raw_json: Optional[str] = None,
    mcp_tools_info: Optional[dict] = None,
    active_intent_id: Optional[str] = None,
    active_intent_body: Optional[str] = None,
    completed_intents: Optional[List[str]] = None,
    session_prompt: Optional[str] = None,
    # ── Spec 005 additions (defaults preserve legacy behaviour) ─────────────
    runtime_facts: Optional[Dict[str, Any]] = None,
    game_context: Optional[Dict[str, Any]] = None,
    platform: Optional[str] = None,
) -> str:
    """Build the system-message text for the toolPlanner LLM call.

    The intent-layer parameters (specs/004-nav-graph-intents) inject the active
    intent's body and a short status header (session prompt, completed intents)
    so the LLM has per-turn context about what it is currently driving toward.

    Spec 005 additions:
        runtime_facts   — RuntimeFacts envelope (build_env, device, jurisdiction,
                          stop-loss). Injected as a compact JSON block in L3.
        game_context    — {playbook: dict, kind_name: str} for the current loaded
                          game. Injected as L4 game-knowledge layer (T026).
        platform        — RuntimeFacts.platform; used to filter the tool registry
                          (T025) so per-platform tools don't leak.
    """
    sections: List[str] = []

    # L0. Goal — persona + identity (cacheable prefix).
    sections.append(
        f"# {agent_goal.agent_name}\n\n{agent_goal.description}"
    )

    # L1. Tools — filtered by active intent + platform (T025).
    sections.append(_format_tools(
        agent_goal,
        mcp_tools_info,
        active_intent_id=active_intent_id,
        platform=platform,
    ))

    # L2. Intent layer — active intent body and session header (specs/004).
    intent_section = _format_intent_section(
        active_intent_id=active_intent_id,
        active_intent_body=active_intent_body,
        completed_intents=completed_intents or [],
        session_prompt=session_prompt or "",
    )
    if intent_section:
        sections.append(intent_section)

    # L3. Runtime facts — compact JSON envelope (spec 005 T013).
    if runtime_facts:
        sections.append(_format_runtime_facts(runtime_facts))

    # L4. Game knowledge — playbook + kind file when in a loaded game (T026).
    if game_context:
        kb_section = _format_game_knowledge(game_context)
        if kb_section:
            sections.append(kb_section)

    # L5. Conversation so far — last-N verbatim, older summarized (T024 + T027).
    sections.append(_format_history(conversation_history))

    # L6. Optional few-shot example provided by the goal definition.
    if agent_goal.example_conversation_history:
        sections.append(
            "## Example conversation flow\n\n"
            f"{agent_goal.example_conversation_history}"
        )

    # L7. Decision rules — terse, no domain-specific examples bleeding in.
    sections.append(_decision_rules(multi_goal_mode))

    # Validation mode — re-evaluate a previously-proposed plan.
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


def _format_intent_section(
    *,
    active_intent_id: Optional[str],
    active_intent_body: Optional[str],
    completed_intents: List[str],
    session_prompt: str,
) -> str:
    """Render the active-intent block. Returns '' when no intent context is supplied."""
    if not (active_intent_id or active_intent_body or session_prompt or completed_intents):
        return ""
    lines: List[str] = ["## Active intent"]
    if session_prompt:
        lines.append(f"**Session prompt** (the user's high-level ask): {session_prompt}")
    if completed_intents:
        lines.append(
            "**Completed intents this session**: " + ", ".join(completed_intents)
        )
    if active_intent_id:
        lines.append(f"**Active intent**: `{active_intent_id}`")
    if active_intent_body:
        lines.append("")
        lines.append(active_intent_body.strip())
    lines.append("")
    lines.append(
        "Emit `active_intent` on every plan_next_action call. Switch it when "
        "the prior intent is done; emit next='done' with active_intent set to "
        "the just-completed intent to mark intent-level completion."
    )
    return "\n\n".join(lines)


def _format_tools(
    agent_goal: AgentGoal,
    mcp_tools_info: Optional[dict],
    *,
    active_intent_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """Render the tool catalog the model can choose from.

    Spec 005 T025: when `active_intent_id` is set, the registry side-cars in
    `tools/registry/*.yaml` are consulted. Native tools whose registry entry
    does NOT include the current intent are dropped; same for tools that
    don't include the current platform. MCP tools (appium-mcp etc.) are not
    in the registry and pass through unfiltered — they're already platform-
    bound by virtue of the MCP server itself.

    When the registry lookup fails or no intent is supplied, behaviour is
    legacy: list every tool, dedup'd by name.
    """
    intent_filter = _load_tool_registry_filter(active_intent_id, platform)

    lines: List[str] = ["## Tools"]
    seen: Set[str] = set()
    dropped: List[str] = []

    # Native tools declared on the goal.
    for tool in agent_goal.tools:
        if tool.name in seen:
            continue
        seen.add(tool.name)
        if intent_filter is not None and not intent_filter(tool.name):
            dropped.append(tool.name)
            continue
        lines.append(_render_tool(
            name=tool.name,
            description=tool.description,
            args=[(a.name, a.type, a.description) for a in tool.arguments],
        ))

    # MCP tools discovered at runtime — pass through unfiltered (no registry).
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

    if dropped and active_intent_id:
        lines.append(
            f"\n_(filtered {len(dropped)} tool(s) not applicable to "
            f"`{active_intent_id}`: {', '.join(sorted(dropped))})_"
        )

    return "\n".join(lines)


def _load_tool_registry_filter(
    active_intent_id: Optional[str],
    platform: Optional[str],
) -> Optional[Any]:
    """Return a callable `name → bool` that applies the intent + platform filter,
    or None if filtering is disabled.

    Spec 005 T025 / research §R2. The registry is loaded lazily and cached at
    the function level so we don't re-read 9 YAMLs every prompt build.
    """
    if not active_intent_id and not platform:
        return None
    registry = _tool_registry_cache()
    if registry is None:
        return None  # registry missing or unreadable — fail open

    def _allow(tool_name: str) -> bool:
        spec = registry.get(tool_name)
        if spec is None:
            return True  # tool isn't in the registry (e.g. MCP tool); allow
        if active_intent_id:
            # Registry YAML lists intents with the full `intent_*` id, matching
            # the values the planner emits. Accept both forms (full + short).
            tool_intents = spec.get("intents") or []
            short = active_intent_id.removeprefix("intent_")
            if active_intent_id not in tool_intents and short not in tool_intents:
                return False
        if platform:
            tool_platforms = spec.get("platforms") or []
            if platform not in tool_platforms:
                return False
        return True

    return _allow


_TOOL_REGISTRY: Optional[Dict[str, Dict[str, Any]]] = None
_GAME_KIND_BODIES: Dict[str, str] = {}


def _build_tool_registry() -> Optional[Dict[str, Dict[str, Any]]]:
    """Read tools/registry/*.yaml. Called at module import (outside sandbox)."""
    if not os.path.isdir(_TOOL_REGISTRY_DIR):
        return None
    try:
        import yaml
    except ImportError:
        return None
    out: Dict[str, Dict[str, Any]] = {}
    for fname in os.listdir(_TOOL_REGISTRY_DIR):
        if not fname.endswith(".yaml"):
            continue
        path = os.path.join(_TOOL_REGISTRY_DIR, fname)
        try:
            with open(path) as f:
                spec = yaml.safe_load(f)
            if isinstance(spec, dict) and spec.get("name"):
                out[spec["name"]] = spec
        except Exception:
            continue
    return out


def _build_game_kind_bodies() -> Dict[str, str]:
    """Read game_kinds/*.md. Called at module import (outside sandbox)."""
    out: Dict[str, str] = {}
    if not os.path.isdir(_GAME_KINDS_DIR):
        return out
    for fname in os.listdir(_GAME_KINDS_DIR):
        if not fname.endswith(".md"):
            continue
        kind_name = fname[:-3]
        path = os.path.join(_GAME_KINDS_DIR, fname)
        try:
            with open(path) as f:
                out[kind_name] = f.read()
        except Exception:
            continue
    return out


def _tool_registry_cache() -> Optional[Dict[str, Dict[str, Any]]]:
    """Return the pre-built registry. No I/O — safe to call from workflow sandbox."""
    return _TOOL_REGISTRY


def _reset_tool_registry_cache() -> None:
    """Test hook: re-read the registry from disk. Must be called outside the sandbox."""
    global _TOOL_REGISTRY, _GAME_KIND_BODIES
    _TOOL_REGISTRY = _build_tool_registry()
    _GAME_KIND_BODIES = _build_game_kind_bodies()


# Warm caches at module import — happens during worker startup, BEFORE the
# workflow sandbox restrictions activate. Workflow code then reads from the
# in-memory dicts without touching the filesystem.
_TOOL_REGISTRY = _build_tool_registry()
_GAME_KIND_BODIES = _build_game_kind_bodies()


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


def _format_runtime_facts(runtime_facts: Dict[str, Any]) -> str:
    """L3 layer: compact JSON envelope with build_env, device, jurisdiction,
    target.app_id, constraints. Spec 005 T013 / setup-doc §5.

    Credentials, OTP digits, secrets are NEVER rendered — `account_ref` is an
    opaque secret-store handle and is the only thing visible. The agent reads
    creds at activity-time, not via the prompt.
    """
    facts = dict(runtime_facts)
    target = dict(facts.get("target") or {})
    target.pop("otp_source", None)  # belt-and-suspenders — never leak
    facts["target"] = target
    return (
        "## Runtime facts\n\n"
        "```json\n"
        f"{json.dumps(facts, indent=2, default=str)}\n"
        "```"
    )


def _format_game_knowledge(game_context: Dict[str, Any]) -> str:
    """L4 layer: per-game playbook + per-kind file. Spec 005 T026.

    Triggered by intent_load_game_context when a `game_directory.loaded_signature`
    matches the current screen. Combined size targets ≤ 600 tokens (FR-010).

    `game_context` shape:
        {
            "playbook":    {slug, kind, actions_json, balance_signature,
                            balance_regex, bonus_trigger_signatures, ...},
            "kind_name":   "slingo" | "slots" | "blackjack" | "roulette",
        }
    """
    pb = game_context.get("playbook") or {}
    kind_name = game_context.get("kind_name")
    if not pb and not kind_name:
        return ""

    parts: List[str] = ["## Game knowledge"]

    if pb:
        # Render only the salient playbook fields — drop bookkeeping (created_at, etc).
        salient_keys = (
            "slug", "kind", "round_end_signature", "balance_signature", "balance_regex",
            "bonus_trigger_signatures", "auto_dismiss_signatures", "actions_json",
            "rules_json", "recovery_json",
        )
        playbook_compact = {k: pb.get(k) for k in salient_keys if pb.get(k)}
        if playbook_compact:
            parts.append(
                "**Playbook (per-game):**\n"
                "```json\n"
                f"{json.dumps(playbook_compact, indent=2, default=str)}\n"
                "```"
            )

    if kind_name:
        kind_body = _GAME_KIND_BODIES.get(kind_name)
        if kind_body:
            parts.append(f"**Kind reference (`{kind_name}`):**\n\n{kind_body}")

    return "\n\n".join(parts) if len(parts) > 1 else ""


def _format_history(conversation_history: Any) -> str:
    """Render the conversation history with spec 005 T024 + T027 applied.

    T024 (page-source strip): any tool-result string field that looks like
    XML/page-source (length > 1200 chars and starts with '<' or contains
    '<hierarchy') is replaced with a `{hash, len, hint}` stub. The model never
    sees the raw XML — `FindElementWithFallback` consumed it locally; the
    planner only needs the outcome.

    T027 (history compactor): the most recent N messages (default 2) are kept
    verbatim; older messages collapse to a one-line summary
    `t-K [actor] tool=<name> next=<sig>` so the planner has continuity without
    paying for repeated tool-result payloads.
    """
    if not conversation_history:
        return "## Conversation so far\n\n(empty)"

    messages = (
        conversation_history.get("messages")
        if isinstance(conversation_history, dict)
        else conversation_history
    ) or []

    if not messages:
        return "## Conversation so far\n\n(empty)"

    skipped = 0
    if len(messages) > _MAX_HISTORY_MESSAGES:
        skipped = len(messages) - _MAX_HISTORY_MESSAGES
        messages = messages[-_MAX_HISTORY_MESSAGES:]

    n_recent = min(_VERBATIM_RECENT_TURNS, len(messages))
    older = messages[:-n_recent] if n_recent else messages
    recent = messages[-n_recent:] if n_recent else []

    lines: List[str] = ["## Conversation so far"]
    if skipped:
        lines.append(f"_({skipped} earlier message(s) omitted to keep the prompt bounded.)_")

    # Older → one-line summaries. Indexes are negative offsets from "now".
    if older:
        lines.append("")
        for offset, msg in enumerate(older, start=1):
            t_label = f"t-{len(messages) - offset + 1}"
            lines.append("- " + _summarize_message(msg, t_label=t_label))

    # Recent → verbatim, with page-source stripped.
    for msg in recent:
        actor = msg.get("actor", "unknown") if isinstance(msg, dict) else "unknown"
        body = msg.get("response", "") if isinstance(msg, dict) else msg
        rendered = body if isinstance(body, str) else json.dumps(body, default=str)
        rendered = _strip_xml_payloads(rendered)
        if len(rendered) > _MAX_MESSAGE_CHARS:
            head = rendered[: _MAX_MESSAGE_CHARS - 100]
            rendered = (
                f"{head}\n[…truncated, original was {len(rendered)} chars; "
                f"call appium_get_page_source again if you need the latest tree]"
            )
        lines.append(f"\n**{actor}:**\n{rendered}")

    return "\n".join(lines)


def _summarize_message(msg: Any, *, t_label: str) -> str:
    """One-line distillation of an older history entry (T027).

    Format: `t-K [actor] tool=<name> next=<sig>|status=<short>` — short enough
    to keep N=80 of these well under 5K chars total.

    Spec 005 T024: tool-result bodies that contain page-source XML never bleed
    into the preview — they are described by their key shape, not their content.
    """
    if not isinstance(msg, dict):
        text = str(msg)
        return f"{t_label} {text[:120]}{'…' if len(text) > 120 else ''}"
    actor = msg.get("actor", "?")
    body = msg.get("response", "")
    if isinstance(body, dict):
        tool = body.get("tool") or body.get("current_tool") or ""
        next_label = body.get("next") or ""
        screen = body.get("current_screen_signature") or body.get("screen") or ""
        bits = []
        if tool:
            bits.append(f"tool={tool}")
        if next_label:
            bits.append(f"next={next_label}")
        if screen:
            bits.append(f"screen={screen}")
        if not bits:
            # Tool-result-shape body. Describe by key set, NEVER render values
            # — this is where XML payloads would otherwise leak as the first
            # 120 chars of the dict's JSON representation.
            preview = _summarize_dict_keys(body)
            bits.append(preview)
        return f"{t_label} [{actor}] " + " ".join(bits)
    # Text body — first line, truncated. Apply XML strip first so a long
    # raw-XML body is replaced with the {hash, len} stub.
    s = _strip_xml_payloads(str(body)) if body else ""
    text = s.strip().splitlines()[0] if s else ""
    if len(text) > 120:
        text = text[:117] + "…"
    return f"{t_label} [{actor}] {text}"


def _summarize_dict_keys(body: Dict[str, Any]) -> str:
    """Describe a tool-result dict by its keys + whether any contained
    a stripped XML payload. Never includes raw values that could leak XML."""
    fragments: List[str] = []
    has_xml = False
    for key, val in body.items():
        if isinstance(val, str) and _looks_like_xml_payload(val):
            has_xml = True
            fragments.append(f"{key}=<XML stripped len={len(val)}>")
            continue
        if isinstance(val, bool):
            fragments.append(f"{key}={str(val).lower()}")
        elif isinstance(val, (int, float)):
            fragments.append(f"{key}={val}")
        elif isinstance(val, str):
            short = val if len(val) <= 40 else val[:37] + "…"
            fragments.append(f'{key}="{short}"')
        elif isinstance(val, list):
            fragments.append(f"{key}=[{len(val)} items]")
        else:
            fragments.append(f"{key}={type(val).__name__}")
        if sum(len(f) for f in fragments) > 200:
            fragments.append("…")
            break
    label = "result " + " ".join(fragments)
    if has_xml:
        label += " (XML stripped)"
    return label


def _strip_xml_payloads(rendered: str) -> str:
    """Replace large XML/page-source content with a `{hash, len, hint}` stub (T024).

    Detection is intentionally permissive: any string field longer than 1200
    chars that starts with '<' (after whitespace) is treated as page-source
    and replaced. False positives are rare in tool-result JSON; false negatives
    leak prompt tokens, so we lean toward stripping.
    """
    # Cheap pre-check: if there's no plausibly large XML in the entire blob, exit.
    if "<" not in rendered or len(rendered) < _XML_STUB_THRESHOLD_CHARS:
        return rendered
    try:
        data = json.loads(rendered)
    except (TypeError, ValueError):
        # Not JSON — could be a raw XML body. If it looks like one, stub it.
        stripped = rendered.lstrip()
        if stripped.startswith("<") and len(rendered) > _XML_STUB_THRESHOLD_CHARS:
            digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:12]
            return (
                f"<XML stripped — hash={digest}, len={len(rendered)} chars; "
                f"call appium_get_page_source again if you need the latest tree>"
            )
        return rendered
    modified = _walk_and_stub(data)
    if modified:
        return json.dumps(data, default=str)
    return rendered


def _walk_and_stub(node: Any) -> bool:
    """Recursively replace large XML-looking strings inside a JSON-ish structure.

    Returns True if any replacement happened, so callers can re-serialise.
    """
    modified = False
    if isinstance(node, dict):
        for key, val in list(node.items()):
            if isinstance(val, str) and _looks_like_xml_payload(val):
                node[key] = _xml_stub_for(val, hint_field=key)
                modified = True
            elif isinstance(val, (dict, list)):
                if _walk_and_stub(val):
                    modified = True
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, str) and _looks_like_xml_payload(item):
                node[i] = _xml_stub_for(item, hint_field=None)
                modified = True
            elif isinstance(item, (dict, list)):
                if _walk_and_stub(item):
                    modified = True
    return modified


def _looks_like_xml_payload(s: str) -> bool:
    if len(s) < _XML_STUB_THRESHOLD_CHARS:
        return False
    head = s.lstrip()[:200]
    return head.startswith("<") or "<hierarchy" in head or "<?xml" in head


def _xml_stub_for(s: str, *, hint_field: Optional[str]) -> str:
    digest = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
    field_part = f" field={hint_field}" if hint_field else ""
    return (
        f"<XML stripped — hash={digest}, len={len(s)} chars{field_part}; "
        f"call appium_get_page_source again if you need the latest tree>"
    )


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
