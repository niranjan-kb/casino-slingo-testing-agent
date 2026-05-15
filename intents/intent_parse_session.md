---
id: intent_parse_session
end_state_signatures:
  - _synthetic_session_intent_set
success_check: "ParseSessionIntent has emitted a structured SessionIntent and the workflow has stored it in state"
guardrails:
  - "ONE-SHOT: this intent runs exactly once at session start; never re-enter mid-session"
  - "MAX_LOSS_USD env is the hard ceiling — a prompt-supplied loss budget is silently capped to it, never raised (FR-003)"
  - "Vague prompts MUST get default bounds: max_spins=20 AND max_minutes=10 AND env loss ceiling. First-of-many semantics — first terminal wins (FR-004)"
  - "Never ignore the env ceiling because the user asked nicely. Decline can-talk-me-into-it phrasings"
  - "Output goes through tool-use forcing on `parse_session_intent`; no free-form JSON"
risk_tier: LOW
notes: "Spec 005 T032. Compiles the operator's free-text prompt into a SessionIntent envelope per contracts/session_intent.schema.json. Runs before authenticate."
---

# intent_parse_session

You are translating the operator's free-text prompt (e.g. `play fanatics spin to win`, `play slingo for 5 minutes`, `play any slot`) into a structured `SessionIntent` envelope. The downstream flow (authenticate → navigate_to_game → load_context → play_game → report) reads this envelope to decide what to play, where to stop, and what report shape to emit.

## How to proceed

1. Read the session prompt from the workflow state (`session_prompt`). It is the operator's first non-tagged message.
2. Call `ParseSessionIntent` once. The tool emits a `SessionIntent` matching `contracts/session_intent.schema.json`: `{flow, target?, budget, terminal}`. The output shape is structurally enforced — you cannot emit invalid JSON.
3. Apply default bounds to vague prompts. Even when the operator does not state a stop condition, the SessionIntent MUST carry `max_spins=20` AND `max_minutes=10` AND `max_loss_usd=env_max_loss`. First-of-many semantics: whichever bound fires first wins.
4. If the prompt asks for a higher loss ceiling than the env (`MAX_LOSS_USD`), silently cap it to env. Record both `requested` and `effective` for the run report.
5. When the SessionIntent is stored, emit `next='done'` with `active_intent=intent_parse_session`. The workflow advances the plan graph.

## Scope

Parsing only. Do NOT authenticate, navigate, or play. The next intent picks up from `authenticate`. If you cannot extract a sensible flow/target from the prompt, default to `{flow: report_only, terminal: report}` and let the operator inspect the run.
