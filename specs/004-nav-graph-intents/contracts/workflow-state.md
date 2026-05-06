# Contract — Workflow State

**Owner**: `workflows/agent_goal_workflow.py`

## New state slots

Three new instance vars on `AgentGoalWorkflow`, set in `__init__`:

```python
self.session_prompt: str = ""                # captured from first user message of the workflow
self.active_intent: Optional[str] = None     # set from planner.tool_data["active_intent"] each turn
self.completed_intents: List[str] = []       # appended on intent-level next='done'
```

## State transitions

### `session_prompt`

```
WF init                          ── self.session_prompt = ""
First user_prompt that does
  NOT start with "###"           ── self.session_prompt = prompt   (set ONCE)
Subsequent non-"###" prompts     ── appended to conversation_history; session_prompt UNCHANGED
```

### `active_intent`

```
WF init                          ── self.active_intent = None
After planner activity returns,
  tool_data["active_intent"] is X ── self.active_intent = X
LLM emits next='done' for the
  active intent                  ── append X to completed_intents; self.active_intent = None
LLM switches active_intent
  mid-flow (X → Y)               ── self.active_intent = Y; X NOT added to completed_intents
                                    (the LLM has explicitly bailed; record as "interrupted" via observation)
```

### `completed_intents`

Append-only within a session. An intent appears at most once. Order reflects the sequence the LLM completed them.

## New `@workflow.query` handlers (WF-2)

```python
@workflow.query
def get_session_prompt(self) -> str:
    return self.session_prompt

@workflow.query
def get_active_intent(self) -> Optional[str]:
    return self.active_intent

@workflow.query
def get_completed_intents(self) -> List[str]:
    return list(self.completed_intents)
```

## Modifications to the existing workflow loop

Two surgical edits, both in the planner-result handling block:

### 1. Capture session_prompt on the first non-tagged user message

Existing code in the main loop:

```python
if self.is_user_prompt(prompt):
    self.add_message("user", prompt)
```

Becomes:

```python
if self.is_user_prompt(prompt):
    self.add_message("user", prompt)
    if not self.session_prompt:
        self.session_prompt = prompt
```

### 2. Read `active_intent` from planner result; update completed_intents on intent-done

Existing code:

```python
tool_data["force_confirm"] = self.show_tool_args_confirmation
self.tool_data = tool_data

next_step = tool_data.get("next")
current_tool = tool_data.get("tool")
```

Adds:

```python
new_active_intent = tool_data.get("active_intent")
if new_active_intent and new_active_intent != self.active_intent:
    workflow.logger.info(
        f"intent transition: {self.active_intent} -> {new_active_intent}"
    )
    self.active_intent = new_active_intent

# Intent-level done: LLM signals an intent is complete (not the session)
if next_step == "done" and self.active_intent:
    if self.active_intent not in self.completed_intents:
        self.completed_intents.append(self.active_intent)
    workflow.logger.info(f"intent completed: {self.active_intent}")
    # Don't end the workflow — clear active intent and let the LLM pick the next one
    self.active_intent = None
    # Convert intent-level done into a re-prompt so the LLM picks the next intent
    self.prompt_queue.append(
        f"### Intent '{self.completed_intents[-1]}' marked complete. "
        f"Pick the next active_intent from the registry, or emit next='done' "
        f"with active_intent=None to end the session."
    )
    continue                                          # skip the existing done-handler
```

The existing `next_step == "done"` handler (which ends the workflow) only fires when `self.active_intent is None` — i.e., session-level done.

## Determinism notes (WF-1)

- All three new state slots are written from activity results (planner returns) or from inputs already in workflow history (`prompt`). Replay is identity-safe.
- Query handlers do NOT mutate state — read-only per Temporal contract.
- The new `prompt_queue.append` for the intent-completion re-prompt is deterministic (always fires in the same order during replay).
- No new signals introduced (WF-2).

## Constitutional compliance summary

| Rule | How this contract complies |
|---|---|
| **WF-1** | All new state set deterministically from activity results / known prompts. |
| **WF-2** | New state surfaces via 3 `@workflow.query` handlers; no new signal types. |
| **WF-3** | Zero edits to `tool_activities.py` or `mcp_client_manager.py`. The planner-result schema extension is parameterized through the existing `_build_plan_next_action_tool(allowed_tool_names, allowed_intent_ids)` signature. |
