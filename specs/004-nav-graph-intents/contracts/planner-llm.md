# Contract — Planner LLM I/O

**Owner**: `activities/tool_activities.py:_build_plan_next_action_tool` (FROZEN body — schema function takes new arg) + `activities/tool_activities.py:agent_toolPlanner` (FROZEN — passes through `active_intent`)

## Input (per planner turn)

The workflow assembles a `ToolPromptInput` with:

```python
ToolPromptInput(
    prompt: str,                              # the user's most recent message OR an LLM-tagged "###" prompt
    context_instructions: str,                # assembled goal description (operational soul + identity + tools + ACTIVE INTENT body)
    allowed_tool_names: List[str],            # closed-set enum for `tool` (existing)
    allowed_intent_ids: List[str],            # NEW: closed-set enum for `active_intent`
)
```

`context_instructions` adds an "Active intent" section per turn — the body of the currently-active intent file (no other intent bodies). This keeps per-call token cost flat.

## Output (per planner turn)

The `plan_next_action` synthetic tool's JSON Schema gets one new top-level field:

```jsonc
{
  "type": "function",
  "function": {
    "name": "plan_next_action",
    "parameters": {
      "type": "object",
      "properties": {
        "active_intent": {
          "type": ["string", "null"],
          "enum": [null, "intent_authenticate", "intent_navigate_to_screen", "intent_play_game", "intent_report"],
          "description": "Which intent is active for this turn. Null only when next='done' or 'pick-new-goal'."
        },
        "next": { "type": "string", "enum": ["confirm", "question", "pick-new-goal", "done"] },
        "tool": { "type": ["string", "null"], "enum": [null, /* allowed_tool_names */] },
        "args": { "type": "object" },
        "response": { "type": "string" }
      },
      "required": ["active_intent", "next", "response"]
    }
  }
}
```

The enum on `active_intent` is rebuilt per call from `allowed_intent_ids`. **The model literally cannot emit an unregistered intent id** — same trick as `tool`.

## Semantics

- `active_intent` is the SINGLE source of truth for which intent is active this turn. The workflow stores it in `self.active_intent`.
- The LLM may switch the active intent on any turn (e.g., advance from `intent_authenticate` to `intent_navigate_to_screen` once the home screen is reached, or fall back to `intent_authenticate` if the session unexpectedly logs out).
- When `next='done'` is emitted with an active intent, the workflow appends the intent id to `self.completed_intents` AND clears `self.active_intent` for the next turn. The session is NOT terminated by intent-level done — only `intent_report` completion (or explicit user end-chat) terminates the session.
- `next='pick-new-goal'` is repurposed: the LLM uses it ONLY when no further intent is appropriate (e.g., session goal achieved, or the user prompt is genuinely ambiguous and needs goal-selection). In v1 with one goal (`goal_casino_session`), this is rare.

## Failure modes

- **`active_intent` returns null when not expected**: workflow logs a warn observation, retains the previous active intent, continues. Per FR-027.
- **LLM emits `next='confirm'` with `active_intent=None`**: same — workflow uses last-known active intent, continues.
- **LLM emits an `active_intent` id not registered**: impossible at the API level (closed-set enum). If somehow it leaks (e.g., schema misconfig), workflow ignores it, logs warn, continues.
