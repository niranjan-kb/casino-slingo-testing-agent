# Phase 0 Research — Navigation Graph & Intent Layer

**Feature**: `004-nav-graph-intents` · **Date**: 2026-05-05

## R1 — How does the LLM pick an intent each turn?

**Decision**: Extend the existing `plan_next_action` synthetic tool (used for tool-use forcing in `activities/tool_activities.py`) with a new top-level field `active_intent`. The field's JSON Schema is a closed enum constrained to the registered intent ids at planner-call time.

The full per-turn output shape becomes:

```json
{
  "active_intent": "intent_navigate_to_screen",
  "next": "confirm",
  "tool": "SmartTap",
  "args": { "...": "..." },
  "response": "..."
}
```

**Rationale**:

- Reuses the per-call enum mechanism we already use for `tool` (which prevents tool hallucination per the existing pipeline). Same trick on `active_intent` prevents intent hallucination.
- No new LLM round-trip — the existing planner call returns the intent.
- Determinism preserved: intent enum is built deterministically from the registry at planner-call time.
- WF-1/WF-2 compatible — the workflow stores the returned `active_intent` in workflow state via the existing `tool_data` slot, exposed via a new `@workflow.query`.

**Alternatives considered**:

- *Upfront LLM decomposition.* One extra LLM call at session start that emits the full intent sequence as a list. Rejected — commits to a plan that often needs replanning (game not found, branching reality). Adds a round-trip and a planning artifact that diverges from runtime.
- *Hand-coded prompt parser (regex).* Rejected directly by FR-014 and the spec amendment we just made — this is the trap we explicitly closed.
- *Separate "intent selector" LLM tool.* Rejected — duplicates the planner machinery; one tool, one shape is cleaner.

## R2 — Intent file format

**Decision**: Markdown with YAML frontmatter. Loaded by `intents/__init__.py` at worker startup.

```markdown
---
id: intent_authenticate
end_state_signatures:
  - home
  - home_lobby
success_check: "balance text visible OR header logo visible"
guardrails:
  - "never echo password or OTP"
  - "OTP follows OTP_POLICY (AUTO-OTP or ASK-USER-OTP)"
risk_tier: HIGH
---

# intent_authenticate

You are completing the casino-app authentication flow. Reach a logged-in
home/lobby state. Walk the seeded screen graph (`app_launch → home`); when
the planner returns no path, reason from the current page-source toward
the end-state signatures listed above. Auto-record observations as you go.
```

**Rationale**:

- Frontmatter gives structured metadata (end-state list, success check, risk tier) the workflow consumes deterministically — no LLM-parsing needed.
- Markdown body is the LLM-facing instructions, ≤ 600 tokens (SC-012). Operational only — no selectors, no fallback candidate lists, no wait-time tables (Principle VI).
- Same loader pattern as `prompts/persona/` — uses `pyyaml` (already a dep) for the frontmatter and stdlib for the body.
- Adding an intent = drop a `.md` file. No Python edit. Symmetric to how observer YAMLs were envisioned in 003.

**Alternatives considered**:

- *Pure markdown without frontmatter.* Workflow would have to parse end-state from prose. Brittle and expensive. Rejected.
- *YAML-only file.* Loses the rich LLM-facing prose; markdown is what the planner consumes anyway. Rejected.
- *Python class per intent.* Reintroduces the goal-per-task code structure. Rejected (Principle II).

## R3 — `intent_play_game` strategy: per-game data, not per-game code

**Decision**: `game_catalog.play_loop_json` carries a per-game play strategy as opaque JSON. `intent_play_game` reads the strategy and the budget, drives a generic spin-loop, terminates on the budget condition. Schema (informal v1):

```json
{
  "type": "spin_slot" | "spin_slingo" | "decision_blackjack" | "spin2win_daily",
  "stake_strategy": "min" | "fixed:0.10" | "table_min",
  "actions_per_round": ["spin"] or ["hit", "stand"] or ["spin", "collect_bonus"],
  "win_signals": [ {"sig_match": "<screen_signature>", "behavior": "save_evidence"} ],
  "exit_conditions": ["budget_bound", "loss_streak:5", "session_seconds:600"]
}
```

**Rationale**:

- Avoids per-game Python files (Principle II / Constitution V replacement).
- Generic loop in `intent_play_game.md` body + Python helper (`activities/intent_activity.py:run_play_loop`) reads the JSON.
- New game = new catalog row + recorded play loop. Zero code change for the common case.

**Alternatives considered**:

- *Per-game intent file (e.g. `intent_play_slingo.md`)*. Rejected — that's per-task markdown, the same trap we just walked away from.
- *LLM reasons the play loop ad-hoc each spin*. Workable on novel games (LLM fallback per FR-016) but expensive in steady state. Use as fallback, not default.

## R4 — Signature proposal storage

**Decision**: New `signature_proposals` table in `screen_map_db.py`. One row per recurring unknown signature, with status `pending|accepted|rejected`.

```sql
CREATE TABLE signature_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signature_hash TEXT NOT NULL UNIQUE,           -- the unk:<hash> from observer
    occurrence_count INTEGER NOT NULL,
    distinct_runs INTEGER NOT NULL,
    candidate_name TEXT,                           -- heuristic guess
    top_text_signals_json TEXT,                    -- top-N text from page-source
    top_id_signals_json TEXT,                      -- top-N resource-ids
    status TEXT NOT NULL DEFAULT 'pending',
    accepted_screen_name TEXT,                     -- set when accepted
    accepted_at TIMESTAMP
);
```

A small CLI script (`scripts/scan_signature_proposals.py`) sweeps `observation_log` for `unk:` hashes meeting the FR-021 threshold (≥3 occurrences across ≥2 runs), upserts proposal rows, and prints a review feed. Acceptance flows promote the proposal into `screen_signatures` via a second CLI step.

**Rationale**:

- Same DB as the rest of the map (no new persistence layer).
- Sweeping is offline / on-demand — no runtime cost; FR-021 does not require real-time proposal generation.
- Status field supports human/LLM-assisted review without schema churn.

**Alternatives considered**:

- *Markdown files in `data/proposals/`.* Workable but harder to query ("show me pending proposals from the last week"). Rejected.
- *Auto-promote above some confidence.* Forbidden by FR-022. Not considered.

## R5 — Confidence decay parameters

**Decision**:

- **Build-mismatch decay factor**: `0.5` (multiplied at read time when `BUILD_ENV` or `APP_PACKAGE` of the row differs from the worker's current env).
- **Staleness window**: `30 days` (configurable via `SCREEN_MAP_STALENESS_DAYS` env var). Beyond this window, effective confidence is multiplied by `max(0.5, 1.0 - (days_stale / 90))` — a soft linear ramp until 90 days, where it floors at 0.5.
- **Read-time only**: stored confidence is NOT modified by decay (FR-026). The next successful verification resets effective = stored.

**Rationale**:

- 0.5 build-mismatch is aggressive enough to push the planner toward LLM exploration on a new build, soft enough that a still-valid row has a chance of being walked (and verified, restoring effective confidence).
- 30 days reflects typical Fanatics Casino release cadence (per-build invalidation); apps don't sit static longer than that in test/cert.
- Linear ramp avoids a cliff that would cause a planner regression at exactly 30+1 days.

**Alternatives considered**:

- *Hard expiry at 30 days.* Rejected — cliff causes spurious regressions.
- *Per-row TTL stored at write time.* Rejected — couples too tightly to write semantics; read-time decay is uniform and easy to tune.

## R6 — Where do `build_env` and `app_package` get attached to rows?

**Decision**: Add `build_env` and `app_package` columns to `screen_signatures`, `screen_elements`, and `screen_transitions` (defaults `'unknown'` for backfill rows). Populated at write time from the worker's `os.environ`. Decay (R5) compares row.build_env / app_package to the current worker's; mismatch triggers the 0.5 factor.

**Rationale**:

- Cheap migration (3 columns × 3 tables). Backfilled with `'unknown'` so existing rows are treated as "valid for this build" until next verification (intentional — keeps existing seeded data usable).
- Fits MW-3 (read-time decay) without changing the writeback path's semantics.

**Alternatives considered**:

- *Separate `build_profiles` table joined at read time.* Over-engineered for v1 with one live build env.
- *Single `build_key` string.* Less queryable than two columns; rejected.

## R7 — Workflow integration: where intent state lives

**Decision**: Three new state slots on `AgentGoalWorkflow`:

- `self.session_prompt: str` — the user's verbatim natural-language prompt that drove the session.
- `self.active_intent: Optional[str]` — id of the currently-active intent, set from the planner's `active_intent` field.
- `self.completed_intents: List[str]` — ordered ids of intents the LLM has marked complete in this session.

Three new queries:

- `get_active_intent() -> Optional[str]`
- `get_completed_intents() -> List[str]`
- `get_session_prompt() -> str`

The planner activity (`agent_toolPlanner` in the FROZEN `tool_activities.py`) already returns `tool_data` as a dict; it will now include `active_intent`. The workflow reads it from `tool_data` and updates state — no edit to the activity required.

**Rationale**:

- WF-1 / WF-2 compliant: state is replay-safe (set from activity result), surfaced via queries.
- WF-3 compliant: we extend the schema the activity already passes through; we don't edit the activity. The schema lives in `_build_plan_next_action_tool` which is in the activity module — this would normally be a WF-3 violation. **Resolved**: the schema function is small, already takes `allowed_tool_names` as a per-call argument; we add `allowed_intent_ids` as another per-call argument so the schema-shape change is parameterized rather than hand-coded into the activity. The activity body is unchanged.

**Alternatives considered**:

- *Workflow signal to push intent decisions in.* Rejected — adds a signal type (FR / WF-2 prefers query handlers).
- *Separate intent-decision activity.* Rejected — costs an extra LLM round-trip per turn. R1 is cheaper.

## R8 — Auto-record contract details

**Decision**: Three localized changes in `tools/slingo_qa/` (which is NOT frozen by WF-3):

1. **`smart_tap.py`** — at the end of a successful tap-and-verify, call `screen_db.record_transition_observation(from, verb, target, to, success=True)`. On verified divergence (`expected_screen` mismatch), call with `success=False` AND a separate call with the actual `to_screen` (the competing edge).
2. **`verify_tap.py`** — extend the return shape to include the verified `(from_screen, to_screen)` pair so callers (SmartTap) can record the transition. Existing callers ignoring the new fields continue to work.
3. **`find_element_with_fallback.py`** — on hit, call `screen_db.upsert_element` with `(current_screen, intent_target, x, y, source="element", confidence=0.6)`. `intent_target` is passed in by the caller; when the caller doesn't have a semantic name (raw exploration), the matched `f"{strategy}:{selector}"` is the fallback label.

All three writebacks are wrapped in try/except — failures log a warn observation but never raise (FR-027 carries through).

**Rationale**:

- Localized to non-frozen files (WF-3 compliant).
- Minimal surface change — extends existing tool returns with optional fields.
- Failure-tolerant per the run-continuity invariant.

**Alternatives considered**:

- *Auto-record from inside the workflow.* Cleaner separation but reintroduces non-determinism into workflow code (DB write). Rejected.
- *Auto-record from `dynamic_tool_activity` in the FROZEN `tool_activities.py`.* WF-3 violation. Rejected.

## R9 — Migration strategy for existing seeded transitions

**Decision**: The 10 seeded login transitions in `data/screen_map.db` get backfilled with `build_env='test'`, `app_package='com.betfanatics.casino.test'` via a one-shot script (`scripts/backfill_transition_build_meta.py`). Rows currently labeled `source='seed'` retain their 0.95 confidence; subsequent observations bump them per the existing logic.

**Rationale**:

- Avoids re-running the seed script (which would reset confidence).
- Backfill is data, not behavior — runtime semantics unchanged for the active build.

**Alternatives considered**:

- *Re-seed with explicit build values.* Rejected — would lose any post-seed observations.
- *Default `'unknown'` build values forever.* Rejected — they'd never trigger build-mismatch decay even on a new build, which is wrong.

## R10 — How the workflow knows the user's "session prompt" vs an LLM-tagged prompt

**Decision**: The first message on `prompt_queue` that does not start with `"###"` (the existing `is_user_prompt` check) AND that arrives BEFORE any tool result is recorded is captured as `self.session_prompt`. Subsequent user messages are conversational (queued via `user_prompt` signal) but do NOT overwrite `session_prompt`.

**Rationale**:

- Reuses the existing `is_user_prompt` heuristic (no new mechanism).
- Captures the session-driving prompt at the natural boundary (first user message of the workflow).
- Preserves multi-turn conversation: subsequent prompts can still nudge the agent without rewriting the session goal.

**Alternatives considered**:

- *New API endpoint `/start-session`* with explicit prompt. Rejected — duplicates `/start-workflow` + first prompt.
- *Always overwrite on each user message.* Rejected — the session goal should be stable across recovery prompts.

---

## Summary

All design questions resolved. **No NEEDS CLARIFICATION markers remain.**

Decisions taxonomy:

- **Reuse**: existing tool-use forcing (R1), persona loader pattern (R2), screen_map_db (R4, R6), `is_user_prompt` heuristic (R10).
- **Extend**: `plan_next_action` schema (R1), `tools/slingo_qa/*` writebacks (R8), workflow state slots + queries (R7).
- **Add**: `intents/` registry (R2), `signature_proposals` table (R4), build_env/app_package columns (R6), three small scripts (R4 scan, R9 backfill, R7 smoke).
- **Defer**: cross-session semantic memory (mem0-class) — out of scope per spec.

Ready for Phase 1 (data-model.md, contracts/, quickstart.md).
