from collections import deque
from datetime import timedelta
from typing import Any, Deque, Dict, List, Optional, TypedDict, Union

from temporalio import workflow
from temporalio.common import RetryPolicy

from models.data_types import (
    ConversationHistory,
    EnvLookupInput,
    EnvLookupOutput,
    NextStep,
)
from models.tool_definitions import AgentGoal
from workflows import workflow_helpers as helpers
from workflows.workflow_helpers import (
    LLM_ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
    LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT,
    MCP_TOOL_ACTIVITY_START_TO_CLOSE_TIMEOUT,
)

with workflow.unsafe.imports_passed_through():
    from activities.intent_activity import (
        is_intent_reachable,
        load_game_context_activity,
        upsert_game_directory_activity,
        upsert_game_playbook_activity,
    )
    from activities.observer_activity import run_observers
    from activities.tool_activities import ToolActivities, mcp_list_tools
    from goals import goal_list
    from intents import load_registry as _load_intent_registry
    from models.data_types import CombinedInput, ToolPromptInput
    from prompts.generators import generate_genai_prompt
    from tools.tool_registry import create_mcp_tool_definitions

# Loaded once per worker process at module import (mirrors goal_list pattern).
# Replay-safe: same files on disk → same registry → same allowed_intent_ids.
_INTENT_REGISTRY = _load_intent_registry()


def _load_plan_graphs() -> Dict[str, Dict[str, Any]]:
    """Load all plan graphs at module import (spec 005 T029).

    Workflow code cannot do file I/O at runtime — that's a Temporal
    determinism rule (WF-1). Module-level loading is fine because it
    happens once per worker process startup before any workflow runs.
    The same files on disk produce the same dicts deterministically, so
    replay is safe.

    Maps goal_id → parsed YAML dict. Goals without a plan-graph file
    (e.g. legacy goal_slingo_qa_android) get no entry → workflow stays
    in legacy mode, reachability guard is permissive.
    """
    out: Dict[str, Dict[str, Any]] = {}
    try:
        import os
        import yaml

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Conventional path: graphs/<goal_id>.yaml — new goals are a file, not code.
        graphs_dir = os.path.join(repo_root, "graphs")
        if not os.path.isdir(graphs_dir):
            return out
        for fname in os.listdir(graphs_dir):
            if not fname.endswith(".yaml"):
                continue
            stem = fname[:-5]  # drop .yaml
            path = os.path.join(graphs_dir, fname)
            try:
                with open(path) as f:
                    parsed = yaml.safe_load(f)
                if isinstance(parsed, dict) and parsed.get("nodes"):
                    out[f"goal_{stem}"] = parsed  # graphs/casino_session.yaml → goal_casino_session
            except Exception:
                continue
    except Exception:
        pass
    return out


_PLAN_GRAPHS = _load_plan_graphs()

# Constants
MAX_TURNS_BEFORE_CONTINUE = 250


# ToolData as part of the workflow is what's accessible to the UI - see LLMResponse.jsx for example
class ToolData(TypedDict, total=False):
    next: NextStep
    tool: str
    args: Dict[str, Any]
    response: str
    force_confirm: bool  # default applied at write site, not in TypedDict


@workflow.defn
class AgentGoalWorkflow:
    """Workflow that manages tool execution with user confirmation and conversation history."""

    def __init__(self) -> None:
        self.conversation_history: ConversationHistory = {"messages": []}
        self.prompt_queue: Deque[str] = deque()
        self.conversation_summary: Optional[str] = None
        self.chat_ended: bool = False
        self.tool_data: Optional[ToolData] = None
        self.confirmed: bool = (
            False  # indicates that we have confirmation to proceed to run tool
        )
        self.tool_results: List[Dict[str, Any]] = []
        self.goal: AgentGoal = {"tools": []}
        self.show_tool_args_confirmation: bool = (
            True  # set from env file in activity lookup_wf_env_settings
        )
        self.multi_goal_mode: bool = (
            False  # set from env file in activity lookup_wf_env_settings
        )
        self.mcp_tools_info: Optional[dict] = None  # stores complete MCP tools result
        # Tool-result count at the moment we last switched goals.
        # Used to guard against an LLM that emits `pick-new-goal` immediately
        # after a `ChangeGoal` switch, before any of the new goal's phases
        # have actually executed.
        self.tool_results_count_at_last_goal_change: int = 0

        # Observer framework state (specs/003-observer-framework). Phase 1
        # populates observation_log via the run_observers activity firing
        # after each tool result (FR-006, FR-018). pending_observations is
        # reserved for sub-flow suggestions wired in phase 2+ (FR-013).
        self.observation_log: List[Dict[str, Any]] = []
        self.pending_observations: List[Dict[str, Any]] = []
        self.seen_signatures: List[str] = []  # per-run novelty cache

        # Intent layer state (specs/004-nav-graph-intents).
        # session_prompt = the user's first non-tagged message (the high-level
        # ask that drove this session). active_intent is set from each planner
        # turn's tool_data. completed_intents grows when the LLM emits
        # next='done' while an intent is active (intent-level done, not
        # session-level).
        self.session_prompt: str = ""
        self.active_intent: Optional[str] = None
        self.completed_intents: List[str] = []

        # Spec 005 state (T029, T030, T031).
        # plan_graph is set during run() when the goal id maps to a graph file.
        # session_intent is the parsed prompt envelope (from intent_parse_session)
        # threaded through the play flow. completed_nodes tracks plan-graph
        # progression for the reachability guard (T031). All replay-safe:
        # plan_graph is module-level; session_intent and completed_nodes are
        # workflow state mutated only via deterministic in-workflow logic.
        self.plan_graph: Optional[Dict[str, Any]] = None
        self.session_intent: Optional[Dict[str, Any]] = None
        self.completed_nodes: List[str] = []

        # Spec 006 T203/T204 state — post-navigate auto-seed + L4 game-knowledge.
        # `game_context` is the {playbook, kind_name} envelope injected into
        # the L4 prompt layer once intent_navigate_to_game completes. It
        # replaces the work the deleted `intent_load_game_context` did. The
        # `last_resolved_*` fields cache ResolveDirectory + DetectScreen
        # outputs so the auto-seed call has the slug/kind/loaded_signature
        # without re-querying the planner.
        self.game_context: Optional[Dict[str, Any]] = None
        self.last_resolved_slug: Optional[str] = None
        self.last_resolved_kind: Optional[str] = None
        self.last_loaded_signature: Optional[str] = None

        # Spec 006 T205 state — ReadBalance retry budget enforcement. Counts
        # consecutive ReadBalance results where `found` is False; reset on a
        # successful read. When it hits 3, the workflow appends a strong
        # directive prompt that nudges the LLM to invoke BudgetCheck with
        # this counter so the `balance_unparseable` terminal fires there.
        self.balance_consecutive_failures: int = 0
        self._balance_terminal_directive_emitted: bool = False

    # see ../api/main.py#temporal_client.start_workflow() for how the input parameters are set
    @workflow.run
    async def run(self, combined_input: CombinedInput) -> str:
        """Main workflow execution method."""
        # setup phase, starts with blank tool_params and agent_goal prompt as defined in tools/goal_registry.py
        params = combined_input.tool_params
        self.goal = combined_input.agent_goal

        # Spec 005 T029: pick the plan graph for this goal, if any. Module-level
        # _PLAN_GRAPHS was loaded once at worker startup (replay-safe). Goals
        # without a graph stay in legacy mode — reachability guard is permissive.
        goal_id = getattr(self.goal, "id", None)
        if goal_id and goal_id in _PLAN_GRAPHS:
            self.plan_graph = _PLAN_GRAPHS[goal_id]
            workflow.logger.info(
                f"plan_graph loaded for {goal_id}: {len(self.plan_graph.get('nodes', {}))} nodes"
            )

        await self.lookup_wf_env_settings(combined_input)

        # If the goal has an MCP server definition, dynamically load MCP tools
        if self.goal.mcp_server_definition:
            await self.load_mcp_tools()

        # add message from sample conversation provided in tools/goal_registry.py, if it exists
        if params and params.conversation_summary:
            self.add_message("conversation_summary", params.conversation_summary)
            self.conversation_summary = params.conversation_summary

        if params and params.prompt_queue:
            self.prompt_queue.extend(params.prompt_queue)

        waiting_for_confirm = False
        current_tool = None

        # This is the main interactive loop. Main responsibilities:
        #   - Selecting and changing goals as directed by the user
        #   - reacting to user input (from signals)
        #   - validating user input to make sure it makes sense with the current goal and tools
        #   - calling the LLM through activities to determine next steps and prompts
        #   - executing the selected tools via activities
        while True:
            # wait indefinitely for input from signals - user_prompt, end_chat, or confirm as defined below
            await workflow.wait_condition(
                lambda: bool(self.prompt_queue) or self.chat_ended or self.confirmed
            )

            # handle chat should end. When chat ends, push conversation history to workflow results.
            if self.chat_should_end():
                return f"{self.conversation_history}"

            # Execute the tool
            if self.ready_for_tool_execution(waiting_for_confirm, current_tool):
                waiting_for_confirm = await self.execute_tool(current_tool)
                continue

            # process forward on the prompt queue if any
            if self.prompt_queue:
                # get most recent prompt
                prompt = self.prompt_queue.popleft()
                workflow.logger.info(
                    f"workflow step: processing message on the prompt queue, message is {prompt}"
                )

                # Record user-provided prompts.
                # Validator (agent_validatePrompt) is ARCHIVED as of 2026-04-29 —
                # adds an LLM round-trip per user message for low ROI.
                # The toolPlanner LLM handles off-topic input via next='question'.
                # Re-enable by restoring the agent_validatePrompt call here.
                if self.is_user_prompt(prompt):
                    self.add_message("user", prompt)
                    # First user message of the session drives intent decomposition.
                    # Captured exactly once; subsequent prompts append to history
                    # but do NOT overwrite the session goal (per spec R10).
                    if not self.session_prompt:
                        self.session_prompt = prompt

                # If valid, proceed with generating the context and prompt
                active_intent_body = (
                    _INTENT_REGISTRY[self.active_intent].body_md
                    if self.active_intent and self.active_intent in _INTENT_REGISTRY
                    else None
                )
                context_instructions = generate_genai_prompt(
                    agent_goal=self.goal,
                    conversation_history=self.conversation_history,
                    multi_goal_mode=self.multi_goal_mode,
                    raw_json=self.tool_data,
                    mcp_tools_info=self.mcp_tools_info,
                    active_intent_id=self.active_intent,
                    active_intent_body=active_intent_body,
                    completed_intents=self.completed_intents,
                    session_prompt=self.session_prompt,
                    game_context=self.game_context,
                )

                # Build the per-call enum of valid tool names so the model
                # cannot hallucinate (see plan_next_action enum constraint).
                allowed_tool_names = sorted({tool.name for tool in self.goal.tools})
                if self.mcp_tools_info and self.mcp_tools_info.get("success"):
                    allowed_tool_names = sorted(
                        set(allowed_tool_names)
                        | set((self.mcp_tools_info.get("tools") or {}).keys())
                    )

                # Spec 005 T052 follow-up: exclude already-completed intents from
                # the planner's active_intent enum so the LLM cannot loop on a
                # finished phase. intent_report is the canonical session terminator
                # so we keep it visible even after it has fired (no-op since the
                # done handler ends the workflow when intent_report completes).
                allowed_intent_ids = sorted(
                    i for i in _INTENT_REGISTRY.keys()
                    if i == "intent_report" or i not in self.completed_intents
                )

                prompt_input = ToolPromptInput(
                    prompt=prompt,
                    context_instructions=context_instructions,
                    allowed_tool_names=allowed_tool_names,
                    allowed_intent_ids=allowed_intent_ids,
                )

                # connect to LLM and execute to get next steps
                tool_data = await workflow.execute_activity_method(
                    ToolActivities.agent_toolPlanner,
                    prompt_input,
                    schedule_to_close_timeout=LLM_ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
                    start_to_close_timeout=LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT,
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=5), backoff_coefficient=1
                    ),
                )

                tool_data["force_confirm"] = self.show_tool_args_confirmation
                self.tool_data = tool_data

                # process the tool as dictated by the prompt response - what to do next, and with which tool
                next_step = tool_data.get("next")
                current_tool = tool_data.get("tool")

                # Intent layer (specs/004-nav-graph-intents): the planner's
                # active_intent is the authoritative source of which intent is
                # active this turn. Update workflow state so queries reflect it.
                new_active_intent = tool_data.get("active_intent")
                if new_active_intent and new_active_intent in _INTENT_REGISTRY:
                    if new_active_intent != self.active_intent:
                        # Spec 005 T031: plan-graph reachability guard. Active
                        # only when a plan graph is loaded for this goal; legacy
                        # goals without a graph (goal_slingo_qa_android et al.)
                        # always pass. The activity is replay-safe — its result
                        # is captured in workflow history (FR-035).
                        allowed = await self._is_intent_reachable_guard(
                            new_active_intent
                        )
                        if not allowed:
                            workflow.logger.warning(
                                f"plan-graph guard blocked intent transition "
                                f"{self.active_intent} -> {new_active_intent}; "
                                f"completed_nodes={self.completed_nodes}; "
                                f"keeping previous intent"
                            )
                            # Fall back: don't update self.active_intent. The
                            # planner sees the same intent context next turn and
                            # should re-plan. Save evidence is best-effort —
                            # observers never halt the run (Constitution III).
                        else:
                            workflow.logger.info(
                                f"intent transition: {self.active_intent} -> {new_active_intent}"
                            )
                            self.active_intent = new_active_intent

                # Spec 005 T031: when an intent emits next='done', mark its
                # plan-graph node as completed so subsequent reachability checks
                # see it satisfied. This is the linkage between the intent layer
                # and the plan graph; both layers stay correct independently.
                if (
                    self.plan_graph is not None
                    and tool_data.get("next") == "done"
                    and self.active_intent
                ):
                    self._mark_plan_node_completed(self.active_intent)

                # Spec 006 T203 — once intent_navigate_to_game says done, fire
                # the auto-seed (game_directory + game_playbook) + load the L4
                # game-knowledge envelope into self.game_context. Replaces
                # the work the deleted `intent_load_game_context` did.
                if (
                    tool_data.get("next") == "done"
                    and self.active_intent == "intent_navigate_to_game"
                ):
                    await self._auto_seed_game_context()

                workflow.logger.info(
                    f"next_step: {next_step}, current tool is {current_tool}"
                )

                # make sure we're ready to run the tool & have everything we need
                if next_step == "confirm" and current_tool:
                    args = tool_data.get("args", {})
                    # if we're missing arguments, ask for them
                    if await helpers.handle_missing_args(
                        current_tool, args, tool_data, self.prompt_queue
                    ):
                        continue

                    waiting_for_confirm = True

                    # We have needed arguments, if we want to force the user to confirm, set that up
                    if self.show_tool_args_confirmation:
                        self.confirmed = False  # set that we're not confirmed
                        workflow.logger.info("Waiting for user confirm signal...")
                    # if we have all needed arguments (handled above) and not holding for a debugging confirm, proceed:
                    else:
                        self.confirmed = True
                # else if the next step is to pick a new goal, set that to be the goal
                elif next_step == "pick-new-goal":
                    # Guard: reject pick-new-goal if no tools from the current
                    # goal have run since the last switch. The LLM occasionally
                    # emits pick-new-goal right after ChangeGoal lands ("yay, I
                    # switched!"), which is wrong — the new goal's phases have
                    # not yet started.
                    progress = (
                        len(self.tool_results)
                        - self.tool_results_count_at_last_goal_change
                    )
                    if progress < 1 and self.goal.id != "goal_choose_agent_type":
                        workflow.logger.warning(
                            f"Suppressing pick-new-goal: 0 tools from {self.goal.id} "
                            f"have run since switch. Re-prompting LLM to start the "
                            f"goal's phases instead."
                        )
                        self.prompt_queue.append(
                            "### Correction: do NOT emit `pick-new-goal` yet. You just "
                            "switched into this goal and have not run any of its phases. "
                            "Read the goal description's first phase and emit "
                            "`next='confirm'` with that phase's tool."
                        )
                    else:
                        workflow.logger.info("All steps completed. Resetting goal.")
                        self.change_goal("goal_choose_agent_type")

                # else if the next step is to be done with the conversation such as if the user requests it via asking to "end conversation"
                elif next_step == "done":
                    self.add_message("agent", tool_data)

                    # Spec 005 T052 follow-up: if the planner re-emitted `done`
                    # for an intent that's already completed (and the plan-graph
                    # guard correctly kept self.active_intent at None), do NOT
                    # fall through to session-end. Re-prompt with a stronger
                    # directive so the LLM advances to the next intent.
                    claimed = tool_data.get("active_intent")
                    if (
                        self.active_intent is None
                        and claimed
                        and claimed in self.completed_intents
                    ):
                        remaining = [
                            i for i in _INTENT_REGISTRY.keys()
                            if i not in self.completed_intents
                        ]
                        workflow.logger.info(
                            f"planner re-emitted done for already-completed '{claimed}'; "
                            f"re-prompting with remaining={remaining}"
                        )
                        self.prompt_queue.append(
                            f"### '{claimed}' is already complete and CANNOT be re-emitted. "
                            f"Pick the next active_intent from this list: {remaining}. "
                            f"Or emit next='done' with active_intent=intent_report to wrap up."
                        )
                        await helpers.continue_as_new_if_needed(
                            self.conversation_history,
                            self.prompt_queue,
                            self.goal,
                            MAX_TURNS_BEFORE_CONTINUE,
                            self.add_message,
                        )
                        continue

                    # Intent-level done: an intent reports completion; the session
                    # continues until either intent_report is the completing one
                    # OR no intent is active (session-level done).
                    if self.active_intent and self.active_intent != "intent_report":
                        if self.active_intent not in self.completed_intents:
                            self.completed_intents.append(self.active_intent)
                        completed = self.active_intent
                        workflow.logger.info(f"intent completed: {completed}")
                        self.active_intent = None
                        # Re-prompt the LLM to pick the next active_intent. This
                        # lands as a "###"-tagged message so it does not become
                        # part of the user-visible conversation history.
                        self.prompt_queue.append(
                            f"### Intent '{completed}' marked complete. "
                            f"Pick the next active_intent from the registry, or emit "
                            f"next='done' with active_intent=intent_report (or null) "
                            f"to wrap up the session."
                        )
                        await helpers.continue_as_new_if_needed(
                            self.conversation_history,
                            self.prompt_queue,
                            self.goal,
                            MAX_TURNS_BEFORE_CONTINUE,
                            self.add_message,
                        )
                        continue

                    # Session-level done: no active intent OR intent_report just
                    # completed. End the workflow and return history.
                    if self.active_intent == "intent_report":
                        if self.active_intent not in self.completed_intents:
                            self.completed_intents.append(self.active_intent)
                        self.active_intent = None
                    return str(self.conversation_history)

                self.add_message("agent", tool_data)
                await helpers.continue_as_new_if_needed(
                    self.conversation_history,
                    self.prompt_queue,
                    self.goal,
                    MAX_TURNS_BEFORE_CONTINUE,
                    self.add_message,
                )

    # Signal that comes from api/main.py via a post to /send-prompt
    @workflow.signal
    async def user_prompt(self, prompt: str) -> None:
        """Signal handler for receiving user prompts."""
        workflow.logger.info(f"signal received: user_prompt, prompt is {prompt}")
        if self.chat_ended:
            workflow.logger.info(f"Message dropped due to chat closed: {prompt}")
            return
        self.prompt_queue.append(prompt)

    # Signal that comes from api/main.py via a post to /confirm
    @workflow.signal
    async def confirm(self) -> None:
        """Signal handler for user confirmation of tool execution."""
        workflow.logger.info("Received user signal: confirmation")
        self.confirmed = True

    # Signal that comes from api/main.py via a post to /end-chat
    @workflow.signal
    async def end_chat(self) -> None:
        """Signal handler for ending the chat session."""
        workflow.logger.info("signal received: end_chat")
        self.chat_ended = True

    # Signal that can be sent from Temporal Workflow UI to enable debugging confirm and override .env setting
    @workflow.signal
    async def enable_debugging_confirm(self) -> None:
        """Signal handler for enabling debugging confirm UI & associated logic."""
        workflow.logger.info("signal received: enable_debugging_confirm")
        self.enable_debugging_confirm = True

    # Signal that can be sent from Temporal Workflow UI to disable debugging confirm and override .env setting
    @workflow.signal
    async def disable_debugging_confirm(self) -> None:
        """Signal handler for disabling debugging confirm UI & associated logic."""
        workflow.logger.info("signal received: disable_debugging_confirm")
        self.enable_debugging_confirm = False

    @workflow.query
    def get_conversation_history(self) -> ConversationHistory:
        """Query handler to retrieve the full conversation history."""
        return self.conversation_history

    @workflow.query
    def get_agent_goal(self) -> AgentGoal:
        """Query handler to retrieve the current goal of the agent."""
        return self.goal

    @workflow.query
    def get_summary_from_history(self) -> Optional[str]:
        """Query handler to retrieve the conversation summary if available.
        Used only for continue as new of the workflow."""
        return self.conversation_summary

    @workflow.query
    def get_latest_tool_data(self) -> Optional[ToolData]:
        """Query handler to retrieve the latest tool data response if available."""
        return self.tool_data

    @workflow.query
    def get_observation_log(self) -> List[Dict[str, Any]]:
        """Query handler: every observer observation emitted in this run.

        See specs/003-observer-framework/spec.md (FR-021). Returns [] in
        phase 0 (registry empty); phase 1+ populates per-tick.
        """
        return list(self.observation_log)

    @workflow.query
    def get_session_prompt(self) -> str:
        """Query handler: the user's first non-tagged prompt of the session.

        Drives intent decomposition. Captured exactly once at the start of the
        workflow; subsequent user messages do not overwrite it (specs/004 R10).
        """
        return self.session_prompt

    @workflow.query
    def get_active_intent(self) -> Optional[str]:
        """Query handler: the currently-active intent id, or None.

        Set from each planner turn's tool_data["active_intent"]. None means
        either the session has just started, an intent just completed, or the
        LLM emitted active_intent=null.
        """
        return self.active_intent

    @workflow.query
    def get_completed_intents(self) -> List[str]:
        """Query handler: ordered list of intent ids the LLM has marked complete.

        Append-only within a session; an intent appears at most once.
        """
        return list(self.completed_intents)

    @workflow.query
    def get_session_intent(self) -> Optional[Dict[str, Any]]:
        """Query handler (spec 005 T030): the parsed `SessionIntent` envelope.

        Set once at session start by intent_parse_session (US1) and threaded
        through navigate_to_game / play_game. None until the planner emits a
        SessionIntent or for legacy flows that don't run intent_parse_session.
        Shape per `contracts/session_intent.schema.json`.
        """
        return dict(self.session_intent) if self.session_intent else None

    @workflow.query
    def get_plan_graph_state(self) -> Dict[str, Any]:
        """Query handler (spec 005 T030): plan-graph progression for this run.

        Surfaces:
            plan_graph_loaded:  bool — whether a plan graph guides this goal
            completed_nodes:    list — node names whose intent has succeeded
            current_intent:     str  — active_intent (mirrors get_active_intent)

        Used by the React UI / run-report to render the plan-graph DAG with
        completed nodes highlighted.
        """
        return {
            "plan_graph_loaded": self.plan_graph is not None,
            "completed_nodes": list(self.completed_nodes),
            "current_intent": self.active_intent,
        }

    @workflow.query
    def get_pending_observations(self) -> List[Dict[str, Any]]:
        """Query handler: observations queued for the next planner turn.

        Cleared after each planner LLM call consumes them (phase 1+).
        """
        return list(self.pending_observations)

    @workflow.query
    def get_session_summary(self) -> Dict[str, Any]:
        """Query handler: rolled-up session view for the React UI / GitHub bot.

        Lists the goal, observer hits, max severity, and feature spec ids
        verified so far. Phase 0 returns the goal id and empty rollups.
        """
        observer_hits: List[str] = []
        feature_specs_verified: List[str] = []
        severity_max = "info"
        severity_rank = {"info": 0, "warn": 1, "bug": 2}
        for obs in self.observation_log:
            oid = obs.get("observer_id")
            if oid and oid not in observer_hits:
                observer_hits.append(oid)
            spec = obs.get("spec_link")
            if spec and spec not in feature_specs_verified:
                feature_specs_verified.append(spec)
            sev = obs.get("severity", "info")
            if severity_rank.get(sev, 0) > severity_rank.get(severity_max, 0):
                severity_max = sev
        return {
            "goal_id": getattr(self.goal, "id", None),
            "observer_hits": observer_hits,
            "severity_max": severity_max,
            "feature_specs_verified": feature_specs_verified,
            "observation_count": len(self.observation_log),
            "pending_count": len(self.pending_observations),
        }

    def add_message(self, actor: str, response: Union[str, Dict[str, Any]]) -> None:
        """Add a message to the conversation history.

        Args:
            actor: The entity that generated the message (e.g., "user", "agent")
            response: The message content, either as a string or structured data
        """
        if isinstance(response, dict):
            response_str = str(response)
            workflow.logger.debug(f"Adding {actor} message: {response_str[:100]}...")
        else:
            workflow.logger.debug(f"Adding {actor} message: {response[:100]}...")

        self.conversation_history["messages"].append(
            {"actor": actor, "response": response}
        )

    def change_goal(self, goal: str) -> None:
        """Change the goal (usually on request of the user).

        Args:
            goal: goal id to change to (e.g. 'goal_casino_session')
        """
        if not goal:
            workflow.logger.warning("change_goal called with empty/None goal id")
            return

        for listed_goal in goal_list:
            if listed_goal.id == goal:
                self.goal = listed_goal
                # Snapshot tool-result count so we can detect "the LLM emitted
                # pick-new-goal but didn't actually run any of the new goal's
                # phases" (see the pick-new-goal handler in run()).
                self.tool_results_count_at_last_goal_change = len(self.tool_results)
                workflow.logger.info(
                    f"Changed goal to {goal} "
                    f"(tool_results_at_switch={self.tool_results_count_at_last_goal_change})"
                )
                return

        workflow.logger.warning(
            f"change_goal: '{goal}' not found in goal_list; current goal unchanged"
        )

    # workflow function that defines if chat should end
    def chat_should_end(self) -> bool:
        if self.chat_ended:
            workflow.logger.info("Chat-end signal received. Chat ending.")
            return True
        else:
            return False

    # ── Spec 005 T031: plan-graph reachability + node completion ──────────

    async def _is_intent_reachable_guard(self, candidate_intent: str) -> bool:
        """Return True if the candidate intent is reachable per the plan graph.

        Permissive when no plan graph is loaded (legacy goals — auth flow path
        is unaffected). Calls the `is_intent_reachable` activity so the result
        is captured in workflow history (FR-035 replay determinism).
        """
        if self.plan_graph is None:
            return True
        try:
            result = await workflow.execute_activity(
                is_intent_reachable,
                {
                    "active_intent": candidate_intent,
                    "completed_nodes": list(self.completed_nodes),
                    "current_node": self.active_intent,
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_attempts=2,
                    backoff_coefficient=1.0,
                ),
            )
        except Exception as e:
            # Activity failure → permissive. Constitution III: observers/guards
            # never halt the goal loop. The failure shows up in the run report.
            workflow.logger.warning(f"reachability guard failed open: {e}")
            return True
        return bool(result.get("reachable", True))

    # ── Spec 006 T203/T204/T205: post-tool capture + auto-seed + retry budget ─

    def _capture_tool_result(self, current_tool: Optional[str]) -> None:
        """Snapshot fields from the latest tool result into workflow state.

        Replay-safe — tool_results is itself recorded in workflow history. We
        only mirror values the workflow needs out-of-band: the resolved game
        slug/kind/loaded_signature (for the post-navigate auto-seed), the
        SessionIntent envelope (for downstream activities), and the
        consecutive-failure count on ReadBalance (for the retry-budget
        terminal directive in T205). Unknown tools are no-ops.
        """
        if not current_tool or not self.tool_results:
            return
        last: Dict[str, Any] = (
            self.tool_results[-1] if isinstance(self.tool_results[-1], dict) else {}
        )

        if current_tool == "ParseSessionIntent":
            # ParseSessionIntent emits the full SessionIntent envelope.
            if last.get("flow") and last.get("budget") and last.get("terminal"):
                self.session_intent = {k: v for k, v in last.items() if k != "tool"}

        elif current_tool == "ResolveDirectory" and last.get("resolved"):
            self.last_resolved_slug = last.get("slug") or self.last_resolved_slug
            self.last_resolved_kind = last.get("kind") or self.last_resolved_kind
            self.last_loaded_signature = (
                last.get("loaded_signature") or self.last_loaded_signature
            )

        elif current_tool == "DetectScreen":
            # DetectScreen returns {screen, confidence, ...}. We record the
            # screen name as a candidate loaded_signature; ResolveDirectory's
            # value (when available) wins because it matches the catalog.
            screen = last.get("screen") or last.get("screen_id")
            if screen and not self.last_loaded_signature:
                self.last_loaded_signature = screen

        elif current_tool == "ReadBalance":
            # T205 — enforce the retry budget. The tool itself never raises;
            # `found: False` is the failure signal. Reset on a hit.
            if last.get("found"):
                if self.balance_consecutive_failures != 0:
                    workflow.logger.info(
                        f"ReadBalance succeeded; resetting "
                        f"balance_consecutive_failures from "
                        f"{self.balance_consecutive_failures} to 0"
                    )
                self.balance_consecutive_failures = 0
                self._balance_terminal_directive_emitted = False
            else:
                self.balance_consecutive_failures += 1
                workflow.logger.warning(
                    f"ReadBalance miss "
                    f"(reason={last.get('reason')}, retries={self.balance_consecutive_failures})"
                )
                if (
                    self.balance_consecutive_failures >= 3
                    and not self._balance_terminal_directive_emitted
                ):
                    self._balance_terminal_directive_emitted = True
                    self.prompt_queue.append(
                        "### ReadBalance has returned not-found "
                        f"{self.balance_consecutive_failures} times in a row. "
                        "Call BudgetCheck NOW with "
                        f"balance_consecutive_failures={self.balance_consecutive_failures} "
                        "to fire the `balance_unparseable` terminal. Then transition "
                        "active_intent to intent_report and emit `next='done'`."
                    )

    async def _auto_seed_game_context(self) -> None:
        """Fire T201/T202/T204 after intent_navigate_to_game completes.

        Best-effort by design (Constitution III — observers/auto-seed never
        halt the goal loop). Without a resolved slug we skip silently; the
        play loop falls back to LLM-only reasoning (no L4 layer).
        """
        slug = self.last_resolved_slug or self._slug_from_session_intent()
        if not slug:
            workflow.logger.info(
                "auto-seed skipped: no resolved slug from ResolveDirectory or "
                "session_intent.target"
            )
            return
        kind = self.last_resolved_kind or self._kind_from_session_intent()
        loaded_signature = self.last_loaded_signature
        workflow.logger.info(
            f"auto-seed firing: slug={slug}, kind={kind}, "
            f"loaded_signature={loaded_signature}"
        )

        # T201 — refresh directory row (idempotent; lobby walk may already
        # have populated everything except loaded_signature).
        await workflow.execute_activity(
            upsert_game_directory_activity,
            {
                "slug": slug,
                "kind": kind,
                "loaded_signature": loaded_signature,
                "seen_in_lobby": False,
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_attempts=2,
                backoff_coefficient=1.0,
            ),
        )

        # T202 — INSERT-OR-PRESERVE empty playbook row. Subsequent calls from
        # intent_play_game's first-launch bootstrap fill the signature fields.
        await workflow.execute_activity(
            upsert_game_playbook_activity,
            {"slug": slug},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_attempts=2,
                backoff_coefficient=1.0,
            ),
        )

        # T204 — load the L4 envelope into workflow state. The next planner
        # turn picks it up via generate_genai_prompt(game_context=...).
        ctx_result = await workflow.execute_activity(
            load_game_context_activity,
            {"slug": slug},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_attempts=2,
                backoff_coefficient=1.0,
            ),
        )
        ctx = ctx_result.get("game_context") if isinstance(ctx_result, dict) else None
        if ctx:
            self.game_context = ctx
            workflow.logger.info(
                f"auto-seed loaded L4 game_context: "
                f"slug={slug}, kind_name={ctx.get('kind_name')}"
            )
        else:
            workflow.logger.warning(
                f"auto-seed: load_game_context returned no row for slug={slug} "
                f"(reason={ctx_result.get('reason') if isinstance(ctx_result, dict) else 'unknown'})"
            )

    def _slug_from_session_intent(self) -> Optional[str]:
        if not self.session_intent:
            return None
        target = self.session_intent.get("target") or {}
        slug = target.get("slug")
        return slug if isinstance(slug, str) and slug.strip() else None

    def _kind_from_session_intent(self) -> Optional[str]:
        if not self.session_intent:
            return None
        target = self.session_intent.get("target") or {}
        kind = target.get("kind")
        if isinstance(kind, str) and kind.strip() and kind != "any":
            return kind
        return None

    def _mark_plan_node_completed(self, intent_id: str) -> None:
        """Map an intent id back to its plan-graph node name and record completion.

        The plan graph nodes use names like `authenticate`, `navigate_to_game`,
        `play_game`. Intents are `intent_authenticate`, `intent_navigate_to_game`,
        etc. We search for the node whose `intent` matches and add its name to
        `completed_nodes`. Idempotent — a node appears at most once.
        """
        if self.plan_graph is None:
            return
        nodes = self.plan_graph.get("nodes") or {}
        for node_name, defn in nodes.items():
            if defn.get("intent") == intent_id and node_name not in self.completed_nodes:
                self.completed_nodes.append(node_name)
                workflow.logger.info(
                    f"plan_graph: node '{node_name}' completed via {intent_id}"
                )
                return

    # define if we're ready for tool execution
    def ready_for_tool_execution(
        self, waiting_for_confirm: bool, current_tool: Any
    ) -> bool:
        if self.confirmed and waiting_for_confirm and current_tool and self.tool_data:
            return True
        else:
            return False

    # LLM-tagged prompts start with "###"
    # all others are from the user
    def is_user_prompt(self, prompt) -> bool:
        if prompt.startswith("###"):
            return False
        else:
            return True

    # look up env settings in an activity so they're part of history
    async def lookup_wf_env_settings(self, combined_input: CombinedInput) -> None:
        env_lookup_input = EnvLookupInput(
            show_confirm_env_var_name="SHOW_CONFIRM",
            show_confirm_default=True,
        )
        env_output: EnvLookupOutput = await workflow.execute_activity_method(
            ToolActivities.get_wf_env_vars,
            env_lookup_input,
            start_to_close_timeout=LLM_ACTIVITY_START_TO_CLOSE_TIMEOUT,
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5), backoff_coefficient=1
            ),
        )
        self.show_tool_args_confirmation = env_output.show_confirm
        self.multi_goal_mode = env_output.multi_goal_mode

    # execute the tool - return False if we're not waiting for confirm anymore (always the case if it works successfully)
    #
    async def execute_tool(self, current_tool: str) -> bool:
        workflow.logger.info(
            f"workflow step: user has confirmed, executing the tool {current_tool}"
        )
        self.confirmed = False
        waiting_for_confirm = False
        confirmed_tool_data = self.tool_data.copy()
        confirmed_tool_data["next"] = "user_confirmed_tool_run"
        self.add_message("user_confirmed_tool_run", confirmed_tool_data)

        # execute the tool by key as defined in tools/__init__.py
        await helpers.handle_tool_execution(
            current_tool,
            self.tool_data,
            self.tool_results,
            self.add_message,
            self.prompt_queue,
            self.goal,
            self.multi_goal_mode,
        )

        # Spec 006 — capture downstream-relevant tool outputs from the latest
        # result. Cheap O(1) inspection of tool_results[-1]; lets us auto-seed
        # game_context after navigate (T203/T204) and enforce the ReadBalance
        # retry budget (T205) without re-querying the planner.
        self._capture_tool_result(current_tool)

        # set new goal if we should
        if len(self.tool_results) > 0:
            if (
                "ChangeGoal" in self.tool_results[-1].values()
                and "new_goal" in self.tool_results[-1].keys()
            ):
                new_goal = self.tool_results[-1].get("new_goal")
                self.change_goal(new_goal)
            elif (
                "ListAgents" in self.tool_results[-1].values()
                and self.goal.id != "goal_choose_agent_type"
            ):
                self.change_goal("goal_choose_agent_type")

        # Observer framework tick (specs/003-observer-framework, FR-006).
        # Per FR-027 this MUST NEVER halt the goal loop — any failure is
        # caught here and the run continues. The activity itself also
        # swallows internal failures; this is belt-and-suspenders.
        await self._run_observer_tick(current_tool)

        return waiting_for_confirm

    async def _run_observer_tick(self, current_tool: Optional[str]) -> None:
        """Fire run_observers for the latest tool result. Never raises."""
        try:
            last_result: Dict[str, Any] = (
                self.tool_results[-1] if self.tool_results else {}
            )
            if not isinstance(last_result, dict):
                last_result = {"raw": str(last_result)}
            last_args = (
                self.tool_data.get("args", {}) if isinstance(self.tool_data, dict) else {}
            )
            last_success = bool(last_result.get("success", True))
            last_error = last_result.get("error")
            obs_payload = {
                "run_id": workflow.info().run_id,
                "goal_id": getattr(self.goal, "id", "") or "",
                "last_tool_name": current_tool,
                "last_tool_args": last_args,
                "last_tool_result": last_result,
                "last_tool_success": last_success,
                "last_tool_error": last_error,
                "seen_signatures": list(self.seen_signatures),
            }
            obs_out = await workflow.execute_activity(
                run_observers,
                obs_payload,
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    maximum_attempts=2,
                ),
            )
            new_obs = obs_out.get("observations") or []
            if new_obs:
                self.observation_log.extend(new_obs)
                workflow.logger.info(
                    f"observer tick: {len(new_obs)} observation(s) from tool={current_tool}"
                )
            new_sig = obs_out.get("new_signature")
            if new_sig and new_sig not in self.seen_signatures:
                self.seen_signatures.append(new_sig)
        except Exception as e:                                          # noqa: BLE001
            # FR-027: observer machinery must never halt the goal.
            workflow.logger.warning(f"observer tick swallowed failure: {e}")

    # debugging helper - drop this in various places in the workflow to get status
    # also don't forget you can look at the workflow itself and do queries if you want
    def print_useful_workflow_vars(self, status_or_step: str) -> None:
        print(f"***{status_or_step}:***")
        if self.goal:
            print(f"current goal: {self.goal.id}")
        if self.tool_data:
            print(f"force confirm? {self.tool_data['force_confirm']}")
            print(f"next step: {self.tool_data.get('next')}")
            print(f"current_tool: {self.tool_data.get('tool')}")
        else:
            print("no tool data initialized yet")
        print(f"self.confirmed: {self.confirmed}")

    async def load_mcp_tools(self) -> None:
        """Load MCP tools dynamically from the server definition"""
        if not self.goal.mcp_server_definition:
            return

        workflow.logger.info(
            f"Loading MCP tools from server: {self.goal.mcp_server_definition.name}"
        )

        # Get the list of tools to include (if specified)
        include_tools = self.goal.mcp_server_definition.included_tools

        # Call the MCP list tools activity
        mcp_tools_result = await workflow.execute_activity(
            mcp_list_tools,
            args=[self.goal.mcp_server_definition, include_tools],
            start_to_close_timeout=MCP_TOOL_ACTIVITY_START_TO_CLOSE_TIMEOUT,
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5), backoff_coefficient=1
            ),
            summary=f"{self.goal.mcp_server_definition.name}",
        )

        if mcp_tools_result.get("success", False):
            tools_info = mcp_tools_result.get("tools", {})
            workflow.logger.info(f"Successfully loaded {len(tools_info)} MCP tools")

            # Store complete MCP tools result for use in prompt generation
            self.mcp_tools_info = mcp_tools_result

            # Convert MCP tools to ToolDefinition objects and add to goal
            mcp_tool_definitions = create_mcp_tool_definitions(tools_info)
            self.goal.tools.extend(mcp_tool_definitions)

            workflow.logger.info(f"Added {len(mcp_tool_definitions)} MCP tools to goal")
        else:
            error_msg = mcp_tools_result.get("error", "Unknown error")
            workflow.logger.error(f"Failed to load MCP tools: {error_msg}")
            # Continue execution without MCP tools
