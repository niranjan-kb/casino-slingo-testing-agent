from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Literal, Optional, Union

from models.tool_definitions import AgentGoal


@dataclass
class AgentGoalWorkflowParams:
    conversation_summary: Optional[str] = None
    prompt_queue: Optional[Deque[str]] = None


@dataclass
class CombinedInput:
    tool_params: AgentGoalWorkflowParams
    agent_goal: AgentGoal


Message = Dict[str, Union[str, Dict[str, Any]]]
ConversationHistory = Dict[str, List[Message]]
NextStep = Literal["confirm", "question", "pick-new-goal", "done"]


@dataclass
class ToolPromptInput:
    prompt: str
    context_instructions: str
    # Names of every tool the agent is allowed to invoke. Used to constrain
    # plan_next_action's `tool` field to a JSON Schema enum, so the model
    # cannot hallucinate tool names like "ToolActivities.agent_toolPlanner".
    # Passing None or [] means no enum is applied (free-form string).
    allowed_tool_names: Optional[List[str]] = None
    # Closed-set enum for plan_next_action's `active_intent` field (feature 004).
    # When non-empty, the planner schema gains `active_intent` constrained to
    # this list so the LLM cannot hallucinate an unregistered intent id.
    # None / [] means no active_intent field on the schema (back-compat).
    allowed_intent_ids: Optional[List[str]] = None


@dataclass
class ValidationInput:
    prompt: str
    conversation_history: ConversationHistory
    agent_goal: AgentGoal


@dataclass
class ValidationResult:
    validationResult: bool
    validationFailedReason: dict = None

    def __post_init__(self):
        # Initialize empty dict if None
        if self.validationFailedReason is None:
            self.validationFailedReason = {}


@dataclass
class EnvLookupInput:
    show_confirm_env_var_name: str
    show_confirm_default: bool


@dataclass
class EnvLookupOutput:
    show_confirm: bool
    multi_goal_mode: bool
