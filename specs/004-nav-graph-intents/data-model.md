# Phase 1 Data Model — Navigation Graph & Intent Layer

**Feature**: `004-nav-graph-intents` · **Date**: 2026-05-05

## Overview

This feature touches:

- **Existing tables** (in `data/screen_map.db`): `screen_signatures`, `screen_elements`, `screen_transitions`, `game_catalog`, `observation_log` — three of these get new columns to support build-aware decay (R6).
- **New table**: `signature_proposals` — the unknown-screen → known-screen feedback loop (R4).
- **Workflow state**: three new slots on `AgentGoalWorkflow` and the planner-result schema, exposed via three new query handlers (R7).
- **Filesystem**: `intents/` registry (markdown files with YAML frontmatter, R2).

No new database is introduced. SQLite remains the single runtime source of truth (Principle I).

---

## Entities

### Screen — already exists

A unique state of the app's UI, identified by a name and one or more matched signatures.

- `screen_name: str` (PK in `screen_signatures.screen_name`) — e.g. `fanatics_one_email`, `home`, `loyalty_bottom_sheet`.
- `app_context: str` — `'platform'` (native) or game-specific (e.g. `'slingo_cash_eruption'`).
- Has zero-or-more **Signatures** (rows in `screen_signatures`) that identify it from page-source.
- Has zero-or-more **Elements** (rows in `screen_elements`) keyed by `(device_profile_id, screen_name, element_name)`.
- Has zero-or-more outbound **Transitions** in `screen_transitions`.

### Signature — already exists

A matchable pattern (text or resource-id) that identifies a screen.

- Fields: `(id, screen_name, app_context, signature_type, signature_value, priority)`
- `signature_type ∈ {element_text, element_id}`.
- **NEW columns** (this feature): `build_env: str DEFAULT 'unknown'`, `app_package: str DEFAULT 'unknown'` for read-time decay (R6).

### Element — already exists

A tappable / readable UI element on a screen, with cached coordinates per device.

- Fields: `(id, device_profile_id, app_context, screen_name, element_name, x, y, element_type, intent, confidence, times_used, times_succeeded, last_verified, source)`.
- **NEW columns**: `build_env`, `app_package` (R6).
- **Auto-recorded by**: `FindElementWithFallback` on hit (FR-019, R8).

### Transition — already exists (added in feature 003's commit)

A directed edge `from_screen --[verb,target,args]--> to_screen` with confidence.

- Fields: `(id, from_screen, intent_verb, intent_target, intent_args_json, to_screen, app_context, confidence, times_used, times_succeeded, last_verified, source)`.
- `intent_verb ∈ {launch, tap, fill_and_continue, fill_and_login, fill_otp_and_submit, ...}` — composite verbs are first-class.
- **UNIQUE** `(from_screen, intent_verb, intent_target, to_screen, app_context)` — branching paths are first-class (same from + verb + target may have multiple to_screen rows with different confidences).
- **NEW columns**: `build_env`, `app_package` (R6).
- **Auto-recorded by**: `SmartTap` / `VerifyTap` (FR-017, FR-018, R8).

### Game catalog entry — already exists (added in feature 003's commit)

A casino game the agent has seen, with metadata for navigation and play.

- Fields: `(id, slug, name, category, provider, loaded_signature, min_bet_usd, max_bet_usd, play_loop_json, last_seen, confidence)`.
- `slug` is unique (e.g. `slingo_cash_eruption`).
- `loaded_signature` references `screen_signatures.screen_name` of the game-loaded state (informal — no FK).
- **`play_loop_json` schema** (R3): JSON object with keys `type`, `stake_strategy`, `actions_per_round`, `win_signals`, `exit_conditions`. v1 schema is informal; tightened in v2 if shape stabilizes.
- **Auto-populated by**: `intent_navigate_to_screen` on first encounter (FR-010, Story 4 scenario 2).

### Signature proposal — NEW

An advisory artifact emitted when an unknown screen recurs across runs. Used by the human/LLM-with-context review step to grow the signature catalog.

```sql
CREATE TABLE signature_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    signature_hash TEXT NOT NULL UNIQUE,            -- the unk:<hash> from observer
    occurrence_count INTEGER NOT NULL,              -- total fires across runs
    distinct_runs INTEGER NOT NULL,                 -- distinct workflow run ids
    candidate_name TEXT,                            -- best-guess screen name
    top_text_signals_json TEXT,                     -- top-5 text strings from page-source
    top_id_signals_json TEXT,                       -- top-5 resource-ids
    last_seen_run_id TEXT,                          -- newest contributing run
    status TEXT NOT NULL DEFAULT 'pending',         -- pending | accepted | rejected
    accepted_screen_name TEXT,                      -- set on accept
    accepted_at TIMESTAMP,
    rejected_reason TEXT
);

CREATE INDEX idx_proposals_status ON signature_proposals(status, proposed_at);
```

**Validation rules**:

- A row may be inserted only when `occurrence_count ≥ 3` AND `distinct_runs ≥ 2` (FR-021, FR-023).
- `status` transitions: `pending → accepted` (sets `accepted_screen_name`, `accepted_at`) or `pending → rejected` (sets `rejected_reason`). No transitions back from terminal states.
- Auto-promotion forbidden — `status='accepted'` MUST be set by an explicit operator action (FR-022).

**State diagram**:

```
        proposed_at set, status='pending'
             │
             ▼
       ┌──────────┐
       │ pending  │
       └────┬─────┘
            │
   ┌────────┴────────┐
   ▼                 ▼
accepted          rejected
   │
   └─→ promote into screen_signatures
       (separate operator action, not automatic)
```

### Intent — NEW (filesystem entity, no DB row)

A declarative unit defining a desired end-state, success check, and guardrails. Loaded at worker startup from `intents/*.md`.

**Schema (YAML frontmatter)**:

```yaml
id: intent_authenticate              # unique; matches filename
end_state_signatures:                # list of screen_signatures.screen_name values
  - home
  - home_lobby
success_check: "balance text visible OR header logo visible"
guardrails:                          # free-text rules the LLM enforces
  - "never echo password or OTP"
  - "OTP follows OTP_POLICY"
risk_tier: HIGH                      # HIGH | MEDIUM | LOW (advisory; map promotion is per-element)
notes: "..."                          # optional, free-form
```

**Schema (markdown body)**:

The body is the LLM-facing instruction set. ≤ 600 tokens (SC-012). MUST NOT contain selectors, fallback candidate lists, or wait-time tables (Principle VI).

**Validation rules**:

- `id` MUST match the filename stem.
- `id` MUST be unique across the registry.
- `end_state_signatures` MUST contain at least one entry.
- Each entry in `end_state_signatures` MUST exist in `screen_signatures.screen_name` (informal — checked at startup, warning if missing).
- `risk_tier ∈ {HIGH, MEDIUM, LOW}`.

### Workflow state slots — NEW

Three new state slots on `AgentGoalWorkflow` (R7):

```python
self.session_prompt: str = ""                # captured from first user message of the workflow
self.active_intent: Optional[str] = None     # set from planner activity result
self.completed_intents: List[str] = []       # ordered ids; appended when LLM marks done
```

**Validation rules**:

- `session_prompt` is set exactly once per workflow lifecycle (the first non-`###`-prefixed user message). Subsequent user messages are appended to `conversation_history` but do NOT overwrite.
- `active_intent` MUST be a member of the registered intent ids OR `None`. Enforced by the closed-set enum on `plan_next_action.active_intent` (R1).
- `completed_intents` is append-only within a session; an intent appears at most once. The workflow appends an entry when the LLM emits `next='done'` for the active intent (signaling intent completion, not session completion).

**Surfaced via**:

- `@workflow.query get_session_prompt() -> str`
- `@workflow.query get_active_intent() -> Optional[str]`
- `@workflow.query get_completed_intents() -> List[str]`

### Planner-output schema — EXTENDED

The existing `plan_next_action` synthetic tool gets one additional field. New full shape:

```json
{
  "active_intent": "intent_navigate_to_screen",   // NEW: closed-set enum at call time
  "next": "confirm",
  "tool": "SmartTap",                             // existing closed-set enum
  "args": { "...": "..." },
  "response": "..."
}
```

The `active_intent` enum is built per-call from the registered intent registry (`allowed_intent_ids`), parallel to `allowed_tool_names` for `tool`. The model literally cannot emit an unregistered intent id.

---

## Relationships

```
                              ┌──────────────────────┐
                              │  Intent (markdown)   │
                              │  end_state_sigs ─────┼──┐
                              └──────────────────────┘  │  refs
                                       ▲                 │ (informal)
                            picked     │                 ▼
                            per turn   │       ┌─────────────────┐
                                       │       │ Signature       │
   ┌─────────────────┐                 │       │ (screen_name)   │
   │  Workflow state │                 │       └────────┬────────┘
   │  - session_prompt                 │                │
   │  - active_intent ─────────────────┘                │ identifies
   │  - completed_intents                                ▼
   └────────┬────────┘                          ┌─────────────────┐
            │ surfaces                          │ Screen          │
            ▼                                   │ (logical)       │
   ┌─────────────────┐                          └────┬──────┬─────┘
   │  @workflow.query │                              │      │
   │  - get_*()      │                       has-many│      │ has-many
   └─────────────────┘                              ▼      ▼
                                       ┌─────────────────┐  ┌─────────────────┐
                                       │ Element         │  │ Transition      │
                                       │ (screen_elements)│ │ (screen_trans-  │
                                       └─────────────────┘  │  itions)        │
                                                            └─────────────────┘
                                                                     │ writes back
                                                                     ▼
                              ┌──────────────────────┐     ┌────────────────────┐
                              │ Game Catalog Entry   │     │ Auto-record from   │
                              │ - loaded_signature ──┼─────│ SmartTap / FEWFB   │
                              │ - play_loop_json     │     └────────────────────┘
                              └──────────────────────┘

                              ┌──────────────────────┐
                              │ Signature Proposal   │ ◄── observer.unknown_screen
                              │ status: pending →    │     ≥3 hits in ≥2 runs (FR-021)
                              │   accepted (manual)  │
                              └──────────────────────┘
                                       │ on accept
                                       ▼ promotes
                              ┌─────────────────┐
                              │ Signature       │
                              └─────────────────┘
```

---

## Migration plan

1. **Schema migration** (idempotent — `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE IF NOT EXISTS` patterns):
   - `ALTER TABLE screen_signatures ADD COLUMN build_env TEXT DEFAULT 'unknown'`
   - `ALTER TABLE screen_signatures ADD COLUMN app_package TEXT DEFAULT 'unknown'`
   - Same two columns on `screen_elements` and `screen_transitions`.
   - `CREATE TABLE signature_proposals (...)`.
   - SQLite doesn't support `ALTER TABLE IF NOT COLUMN EXISTS`; we use a `PRAGMA table_info` check + conditional ALTER, wrapped in the schema-init function.

2. **Backfill** (`scripts/backfill_transition_build_meta.py`):
   - For all rows currently with `build_env='unknown'`, set them to the active worker's `BUILD_ENV` and `APP_PACKAGE` if and only if `last_verified` is recent (within the staleness window). Rows untouched by recent runs keep `'unknown'` and are treated as exploratory by the decay model.

3. **Intents registry**:
   - Create `intents/` directory.
   - Author 4 markdown files: `authenticate.md`, `navigate_to_screen.md`, `play_game.md`, `report.md`. Each has frontmatter + ≤ 600-token body.
   - Author `intents/__init__.py` with `load_registry()` returning `{id: IntentDeclaration}`.

4. **Workflow extension**:
   - Add 3 state slots to `AgentGoalWorkflow.__init__`.
   - Add 3 `@workflow.query` methods.
   - In the planner-result handler, extract `active_intent` from `tool_data` and update state. Append to `completed_intents` when `next='done'` is emitted while an intent is active.

5. **Auto-record hooks** in `tools/slingo_qa/`:
   - `smart_tap.py`: call `record_transition_observation` after VerifyTap.
   - `verify_tap.py`: extend return shape with `(from_screen, to_screen)`.
   - `find_element_with_fallback.py`: call `upsert_element` on hit.

6. **Tests**:
   - Unit: new schema columns; `signature_proposals` CRUD; intent registry loader (frontmatter parse, validation rules).
   - Integration: `goal_login` smoke continues to PASS under the new intent layer (Story 1).
   - Integration: novel prompt (Story 3 scenario 4) reaches a terminal state.
