---
id: intent_load_game_context
end_state_signatures:
  - game_context_loaded
success_check: "the game_playbook row for the current slug is present (auto-created on first launch) and the game_kinds/<kind>.md body has been injected into the prompt's L4 layer"
guardrails:
  - "ONE-SHOT: this intent runs exactly once per game-launch (per loaded-signature detection)"
  - "if no playbook row exists for this slug+build_env+app_version, INSERT an empty row — auto-population happens during play, never via inferred prose"
  - "do not start playing — the next intent (`intent_play_game`) drives rounds"
  - "context budget: combined playbook+kind ≤ 600 tokens (FR-010); injection is verified by the prompt assembler before call"
risk_tier: LOW
notes: "Spec 005 T034. Wires automatic context injection on the loaded-game signature. Replaces hand-authored per-game prose."
---

# intent_load_game_context

You are entering a freshly-loaded game and need its context injected before play begins. The combination of `game_playbook` (per-game knowledge: action map, balance regex, bonus signatures) + `game_kinds/<kind>.md` (per-category abstraction: turn structure, animation defaults, risk tiers) is the *L4 game-knowledge layer* in the planner prompt.

## How to proceed

1. Read the current `loaded_signature` and resolve the slug + kind from `game_directory`.
2. Look up `game_playbook` for this `(slug, build_env, app_version)`. If absent, INSERT an empty row — auto-population fills `actions_json`, `balance_signature`, `balance_regex`, `bonus_trigger_signatures` during the play loop as the agent observes them.
3. Confirm the prompt assembler has loaded `game_kinds/<kind>.md` (it caches these at module import). If `kind_name` is unknown — i.e. no kind file on disk — log to observation_log and continue with kind=null; the play loop will rely entirely on the playbook + LLM reasoning.
4. Emit `next='done'` with `active_intent=intent_load_game_context`. The next turn's prompt will include the L4 game-knowledge layer automatically.

## Scope

Context preparation only. NO bets, NO stake adjustments, NO `info` / `paytable` traversal. The play loop handles all of those if/when needed. If the agent finds itself accidentally inside paytable / settings during this intent, back out to `loaded_signature` before completing.
