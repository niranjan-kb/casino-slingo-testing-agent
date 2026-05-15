---
description: "Dependency-ordered tasks for Casino Game-Play & Verification Suite (005)"
---

# Tasks: Casino Game-Play & Verification Suite

**Input**: Design documents from `/specs/005-casino-game-play-suite/`
**Prerequisites**: `plan.md` ✅, `spec.md` ✅, `research.md` ✅, `data-model.md` ✅, `contracts/` ✅, `quickstart.md` ✅
**Tests**: Included — every user story has explicit "Independent Test" criteria in the spec, and FR-036 requires verifying optimizations every run.
**Organization**: Tasks grouped by user story so each can be implemented, tested, and demoed independently. P1 stories (US1, US2, US5, US7, US9, US10) form the MVP boundary.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no dependencies on incomplete tasks).
- **[Story]**: User-story label (US1–US10). Setup, Foundational, and Polish phases have no story label.

## Path Conventions

Single project at repo root: `intents/`, `goals/`, `tools/`, `activities/`, `workflows/`, `shared/`, `prompts/`, `scripts/`, `data/`, `game_kinds/`, `graphs/`, `tests/`. New paths added by this feature: `game_kinds/`, `graphs/`, `tools/registry/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New top-level dirs and env-var configuration.

- [X] T001 Create new top-level directories: `game_kinds/`, `graphs/`, `tools/registry/` with placeholder `.gitkeep` files
- [X] T002 [P] Add new env vars to `.env.example` documenting defaults: `MAX_LOSS_USD=10`, `SCREEN_MAP_STALENESS_DAYS=30`, `OUTCOME_DRIFT_THRESHOLD=0.30`, `PROPOSALS_PER_WEEK_BUDGET=50`, `BUILD_ENV=cert`
- [X] T003 [P] Update `CLAUDE.md` "Active Technologies" section to list `game_kinds/<kind>.md` and `graphs/casino_session.yaml` as new declarative-spec locations (already partially done by `/speckit.plan`)

**Checkpoint**: Directories and configuration ready. No behavior changes yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema migrations, planner-prompt overhaul, plan-graph wiring, and game-kind files. **No user-story work may begin until this phase completes.**

### Schema migrations (idempotent in `shared/screen_map_db.py::ensure_schema()`)

- [X] T004 Add `game_directory` table to `shared/screen_map_db.py::ensure_schema()` per data-model §1 (PK slug, kind/aliases/popularity/loaded_signature/build_env/app_version, indexes)
- [X] T005 Add `game_playbook` table to `shared/screen_map_db.py::ensure_schema()` per data-model §2 (PK slug FK, actions_json/balance_*/bonus_trigger_signatures/auto_dismiss_signatures/recovery_json/rules_*)
- [X] T006 Add `screen_action_frontier` table to `shared/screen_map_db.py::ensure_schema()` per data-model §3
- [X] T007 Add `transition_outcomes` table to `shared/screen_map_db.py::ensure_schema()` per data-model §4 + create `transition_top_outcome` SQL view returning top-`observed_count` end_sig per `(start_sig, action)` (named `transition_top_outcome` to avoid collision with the existing `screen_transitions` table; legacy callers migrate explicitly)
- [X] T008 Add `game_rounds` table to `shared/screen_map_db.py::ensure_schema()` per data-model §5 (with `bonus_round_id` self-link)
- [X] T009 Add `animation_timings` table to `shared/screen_map_db.py::ensure_schema()` per data-model §6 (PK includes build_env + app_version; Welford fields)
- [X] T010 Add `logical_screens` and `logical_elements` tables + `ALTER` on `screen_signatures` (`logical_id`, `parent_sig`, `deprecated_at`, `dom_skeleton_hash`) and `screen_elements` (`logical_id`, `risk_tier`, `side_effect`, `consecutive_failures`, `needs_review`) to `shared/screen_map_db.py::_ensure_spec_005_columns()` per data-model §7
- [X] T011 Add `transition_observations` append-only event log table to `shared/screen_map_db.py::ensure_schema()` per data-model §8
- [X] T012 `ALTER` `signature_proposals` to add `dom_skeleton_hash`, `cluster_id`, `rejected_cooldown_until`, `evidence_path` in `shared/screen_map_db.py::_ensure_spec_005_columns()` per data-model §9 (note: `status` column already existed from feature 004)

### Loaders, registries, declarative specs

- [X] T013 Implement `shared/runtime_facts.py` — `RuntimeFacts` dataclass + `load_runtime_facts()` + `lower_budget()` (FR-003 hard ceiling enforced). Validated: env build, select_device override, prod read-only, missing app_id raises (no hardcoded fallback)
- [X] T014 Author `graphs/casino_session.yaml` per `contracts/plan_graph.schema.json` (7 nodes: parse_session/authenticate/navigate_to_game/load_context/play_game/play_bonus/report; 4 guards; 2 recovery routes). Schema-validated.
- [X] T015 [P] Created `tools/registry/<ToolName>.yaml` side-cars for 9 existing tools (SmartTap, VerifyTap, LookupCoords, DetectScreen, SaveEvidence, FindElementWithFallback, WaitSeconds, TapCoordinate, GenerateReport) — per-tool platforms/intents/risk_tier/side_effects. All schema-validated.
- [X] T016 Extended `activities/intent_activity.py` (already existed from spec-004 — WF-3 compliant) with 3 spec-005 activities: `is_intent_reachable` (plan-graph guard), `load_runtime_facts_activity`, `record_intent_transition`. `activities/tool_activities.py` and `shared/mcp_client_manager.py` UNTOUCHED.

### Game-kind declarative files (≤400 tokens each, hand-authored)

- [X] T017 [P] Authored `game_kinds/slingo.md` — 478 tokens (over 400 target but under FR-010's combined-with-playbook ≤ 600 ceiling, since playbook averages ~120 tokens). Includes turn structure, sub-types (cash_out vs bonus_trigger), 5 special symbols (Joker / Super Joker / Free Spin / Coin / Devil), wild placement priority, key signatures, animation defaults, auto-dismiss modals, risk tiers, **buy-extra-spins HARD decline rule** (variable cost protects MAX_LOSS_USD), bonus exploration semantics. Slingo is the flagship kind and has more legitimate kind-level invariants than the simpler kinds.
- [X] T018 [P] Authored `game_kinds/slots.md` — 344 tokens. Same shape; autoplay-disabled constraint documented.
- [X] T019 [P] Authored `game_kinds/blackjack.md` — 393 tokens. Multi-hand turn structure + dealer-state polling rule. Decision policy specifics deferred to per-game playbook.
- [X] T020 [P] Authored `game_kinds/roulette.md` — 389 tokens. Time-constraints (`min_bet_window_ms=2000`, `safety_buffer_ms=1000`) baked into the kind so per-game playbooks inherit them.

### Path planner & screen-graph extensions

- [X] T021 Extended `shared/screen_graph.py::_decayed_transitions_from()` for per-surface decay via new `_load_staleness_overrides()` helper that reads `screen_signatures.staleness_days` (NULL → env `SCREEN_MAP_STALENESS_DAYS`). Threaded through `find_path` + `all_reachable`. Validated: auth-flow path planning unchanged (still 9 steps, conf 0.95).
- [X] T022 Added stochastic-outcomes parallel API in `shared/screen_graph.py`: `outcomes_for()`, `top_outcome()`, `distribution_shift()`. Reads from `transition_outcomes` table; doesn't entangle with `find_path` (which keeps using legacy logical-name `screen_transitions`). Validated: empty-on-unseen, top-by-observed-count, distribution shift math correct.
- [X] T023 Extended `shared/screen_graph.py` with edge filters: `exclude_destructive` (blacklist `deposit_submit`/`withdraw_submit`/`kyc_submit`/`account_close`/`promo_redeem`/`fancash_convert` via `_is_destructive_edge` — checks `side_effect` column when present, else infers from `intent_verb` substring) + `allowed_intent_verbs` whitelist. Both threaded through `find_path` and `all_reachable`. Added `evaluate_precondition()` evaluator for `transition_outcomes.precondition` JSON predicates over RuntimeFacts (logged_in / jurisdiction / build_env / platform / balance_gt / feature_flags). Fail-closed on unknown keys + on missing facts. Validated: 11 predicate cases pass; destructive edges blocked when filter active; non-destructive sibling still reachable.

### Planner prompt overhaul (cost optimizations FR-031..FR-036)

- [X] T024 Stripped raw page-source content from planner prompt in `prompts/generators.py` — `_strip_xml_payloads()` walks tool-result JSON, replaces any string >1200 chars starting with `<` (or containing `<hierarchy`/`<?xml`) with a `<XML stripped — hash=<sha256[:12]>, len=<N>, field=<key>>` stub. Older messages summarized via `_summarize_dict_keys()` describe by key shape only — never render values that could leak XML. The frozen `tool_activities.py` was NOT modified.
- [X] T025 Implemented intent-conditional tool filter in `prompts/generators.py::_format_tools()` — reads `tools/registry/*.yaml` (cached at module level), intersects `intents ∋ active_intent_id` and `platforms ∋ platform`. MCP tools (not in registry) pass through unfiltered. Validated: `SmartTap` allowed for `intent_authenticate`+android; `GenerateReport` filtered out for non-report intents; SmartTap blocked on iOS (registry says android-only).
- [X] T026 Added L4 game-knowledge layer in `prompts/generators.py::_format_game_knowledge()` — when caller passes `game_context={playbook, kind_name}`, injects salient playbook keys (slug, kind, balance_*, bonus_trigger_signatures, auto_dismiss_signatures, actions_json, rules_json, recovery_json) + the body of `game_kinds/<kind>.md`. Empty game_context yields no section.
- [X] T027 Implemented working-memory compactor in `prompts/generators.py::_format_history()` — last `_VERBATIM_RECENT_TURNS=2` (env-overridable) messages rendered verbatim with XML stripped; older messages collapse to `t-K [actor] tool=<name> next=<sig> screen=<sig>` (or key-shape summary if no tool/next/screen fields). Hardcoded `_MAX_HISTORY_MESSAGES=80` cap retained.
- [ ] T028 **DEFERRED**: Apply Anthropic `cache_control: ephemeral` on L0+L1 prefix. Requires touching `activities/tool_activities.py` (FROZEN per WF-3) at the `messages` construction site. Data-model.md anticipated this might need re-evaluation during implementation. T024+T025+T027 already deliver substantial token reduction from tool-list filtering + XML strip + history compaction; verify cost numbers from a real run before deciding whether the WF-3-allowed touch is load-bearing.

### Workflow extensions (allowed by WF-1 v3.0.0)

- [X] T029 Extended `workflows/agent_goal_workflow.py` with module-level `_PLAN_GRAPHS` dict — auto-discovers every `graphs/<name>.yaml` at worker startup (replay-safe; same files → same dict). Workflow `__init__` defaults `plan_graph=None`; `run()` sets `self.plan_graph` from `_PLAN_GRAPHS[goal_id]` when matched. Legacy goals stay in plan_graph=None mode → permissive guard (auth flow regression-free).
- [X] T030 Added workflow state `session_intent: Optional[Dict]`, `completed_nodes: List[str]` + two new `@workflow.query` handlers: `get_session_intent()` and `get_plan_graph_state()` (returns `{plan_graph_loaded, completed_nodes, current_intent}`). Per WF-2 (state via queries, not new signals).
- [X] T031 Added `_is_intent_reachable_guard()` helper that calls the `is_intent_reachable` activity (workflow history → replay-safe per FR-035); on `reachable=False` logs warning + falls back (does NOT update `self.active_intent`). Guard is permissive when `plan_graph=None`. Added `_mark_plan_node_completed()` that maps `intent_id` back to plan-graph node name on `next='done'` and appends to `completed_nodes`. **Validated**: workflow unit-test suite 8 passed / 1 failed (the 1 fail is the same pre-existing `test_validation_failure` from baseline). Full suite: 31 passed / 10 failed — identical to baseline.

**LIVE VALIDATION (post-restart)**: end-to-end run `988f50c8-231e-406b-8cf8-7e4321ca45fe` completed with status COMPLETED. **No functional regression.** Headline numbers vs baseline:

| Metric | Baseline | Spec-005 | Δ |
|---|---|---|---|
| Status | COMPLETED | COMPLETED | — |
| LLM calls | 59 | 60 | +1.7% (within ±10% tolerance) |
| Wall-clock duration | 425s | 258s | **−39.3%** (T024 page-source strip + T027 history compactor paying off) |
| Tool dispatches | 56 | 58 | +2 |
| Failed activities | 0 | 1 (`is_intent_reachable`, fell open per Constitution III; addressed below) | — |

**Mid-run hard fix (sandbox restriction)**: `prompts/generators.py` was calling `os.path.isdir`/`os.listdir`/`os.path.isfile`/`open()` from inside the workflow sandbox at runtime (T025 registry filter, T026 game-kind body load) → `RestrictedWorkflowAccessError`. Fix: split into `_build_tool_registry()` / `_build_game_kind_bodies()` invoked at module import (worker startup, BEFORE sandbox activates) populating `_TOOL_REGISTRY` + `_GAME_KIND_BODIES` dicts; runtime path reads from in-memory dicts only. See `prompts/generators.py:283-345`. Addendum to T025 + T026.

**Activity registration + first-turn correctness**: the post-run `is_intent_reachable` failure had two root causes: (a) the activity was not registered in `scripts/run_worker_android.py` worker startup, throwing `NotFoundError`; and (b) the plan graph's `authenticate` node requires `parse_session.success`, but legacy auth flows under `goal_casino_session` skip `intent_parse_session`, so the very first transition would be blocked. Both fixed:
  - Registered `is_intent_reachable` + `load_runtime_facts_activity` + `record_intent_transition` in `run_worker_android.py:135-151`. Added module-level `set_plan_graph()` call wired to `graphs/casino_session.yaml` at worker startup.
  - Added `_is_on_entry_path()` to `is_intent_reachable` activity: when `completed_nodes=[]` (truly fresh session), any candidate that lies on an entry path (transitive `requires` chain terminates at a node with no `requires`) is permitted with `reason=session_start_entry_path`. Quiet-case `active_intent=None` no longer returns `reachable=False` — it returns permissive `no_active_intent`. Validated: 9-case reachability matrix all pass; pytest workflow suite 8/9 pass (same as baseline).

**Checkpoint**: Foundation ready. Schema migrated, prompts overhauled, plan-graph live, game-kind files in place. User-story implementation can begin.

---

## Phase 3: User Story 1 — Spin to Win (Priority: P1) 🎯 MVP

**Goal**: Vague prompt `play fanatics spin to win` → ParseSessionIntent → authenticate (already locked) → navigate to game (recents/category/search/scroll) → load context → bounded play → report.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game spin_to_win --prompt "play fanatics spin to win" --timeout 600` reaches the loaded game, plays ≥1 round, terminates within `MAX_LOSS_USD=10` and default bounds, emits `reports/<id>.{json,md}`.

### Intent declarations (≤600 tokens each, declarative frontmatter only — Principle VI)

- [X] T032 [P] [US1] Author `intents/intent_parse_session.md` — id, allowed_tools=[ParseSessionIntent], end_state_signatures=session_intent_set, success_check, guardrails (one-shot, runs once at session start)
- [X] T033 [P] [US1] Author `intents/intent_navigate_to_game.md` — id, allowed_tools, sub_strategies (recents/category_jump/search/scroll_grid), end_state_signature=`game_directory.loaded_signature`, on_unresolved_query branch
- [X] T034 [P] [US1] Author `intents/intent_load_game_context.md` — id, allowed_tools=[ResolveDirectory, LookupCoords], end_state=context_injected, one-shot
- [X] T035 [P] [US1] Refine `intents/intent_play_game.md` — id, allowed_tools=[ReadBalance, BudgetCheck, SmartTap, VerifyTap, WaitForSignature, FindElementWithFallback, SaveEvidence], end_state=terminal_reached, repeat_until budget.terminal

### Local QA tools (per data-model + contracts)

- [X] T036 [P] [US1] Implement `tools/slingo_qa/ParseSessionIntent.py` — Anthropic tool-use forced classifier emitting `SessionIntent` per `contracts/session_intent.schema.json`; closed-set enums for flow/kind/terminal
- [X] T037 [P] [US1] Implement `tools/slingo_qa/ResolveDirectory.py` — pure SQLite (no LLM): exact slug → kind+LIKE+token-set ratio → popularity/recents rank; returns top match + alternatives + `unresolved` flag (research §R1)
- [X] T038 [P] [US1] Implement `tools/slingo_qa/ReadBalance.py` — page-source extract via `game_playbook.balance_signature` + `balance_regex`; retry up to `min(3, ceil(1/conf))` times before halt (gaps §A5); writes `game_rounds.balance_read_attempts`
- [X] T039 [P] [US1] Implement `tools/slingo_qa/BudgetCheck.py` — computes `effective_max_loss = min(env_max_loss, prompt_max_loss or env_max_loss)`; first-of `n_spins | max_minutes | max_loss_usd` terminal; never `max(...)`. Emits structured terminal reason
- [X] T040 [P] [US1] Implement `tools/slingo_qa/WaitForSignature.py` — read `animation_timings(game_slug, action, build_env, app_version)`; if `samples ≥ 5` use `p95 + 2σ`; else use kind-file `learned_default`; final fallback stable-UI detector (no DOM change for 800ms). Online-update samples via Welford's algorithm (research §R8)
- [X] T041 [P] [US1] Add `tools/registry/{ParseSessionIntent,ResolveDirectory,ReadBalance,BudgetCheck,WaitForSignature}.yaml` side-cars with `platforms`/`intents`/`risk_tier`/`schema_ref`/`side_effects`

### Worker wiring + observers

- [X] T042 [US1] Extended `scripts/run_worker_android.py` — registered 3 new spec-005 activities (`is_intent_reachable`, `load_runtime_facts_activity`, `record_intent_transition`); wired `set_plan_graph()` to load `graphs/casino_session.yaml` at startup. New tools (`ParseSessionIntent` / `ResolveDirectory` / `ReadBalance` / `BudgetCheck` / `WaitForSignature`) registered in `tools/__init__.py::get_handler` (dispatch path) AND in `tools/tool_registry.py` (`ToolDefinition` entries) AND wired into `goals/casino_session/__init__.py::_CASINO_SESSION_LOCAL_TOOLS` so the planner sees them. Final tool count: 13 local + 12 MCP appium tools.

**US1 implementation addendum (T032–T042 actual notes):**
- All 4 intent files under 600-token Constitution VI ceiling: parse_session 577, navigate_to_game 505, load_game_context 538, play_game 575.
- `ParseSessionIntent` is heuristic-first (regex extractor over `_KIND_KEYWORDS` / `_FLOW_KEYWORDS`), not LLM-driven — deterministic, replay-safe, and covers all 10 schema-validated test cases. LLM fallback intentionally deferred; current heuristic handles every prompt the spec exercises.
- `ResolveDirectory` is pure-SQL: exact_slug → kind+LIKE → alias_match → token-set ratio (Jaccard ≥ 0.3). NO LLM call, NO external fuzzy library. Empty directory → unresolved gracefully.
- `BudgetCheck` priority: `balance_unparseable` > `budget_exhausted` > `n_spins` > `max_minutes`. Env hard ceiling honoured at the call site (the workflow passes already-clamped `max_loss_usd`).
- `ReadBalance` `_parse_amount()` handles US `$1,234.56` and European `1.234,56` formats by separator-position inference — no locale hardcoded.
- `WaitForSignature` Welford-online stats persisted to `animation_timings`; build_env / app_version mismatch triggers fresh sampling (FR-021 verified — same `(game,action)` with different `app_version` gets `samples=0`).
- Defaults `_DEFAULT_MAX_SPINS=20` / `_DEFAULT_MAX_MINUTES=10` are env-overridable for tighter test runs without code changes.

- [X] T043 [US1] Extended `activities/observer_activity.py` with `_autorecord_frontier()` — every screen-revealing tool tick parses page-source via existing `parse_page_source()`, filters via new `extract_interactive_elements()` (clickable/focusable/Button/EditText/Switch/Checkbox/Tab/MenuItem) and INSERT-OR-IGNOREs into `screen_action_frontier`. Side-effect classifier (`idempotent` | `reversible` | `destructive`) mirrors `_DESTRUCTIVE_VERBS` from `screen_graph.py`. Per-turn input-token proxy emitted to `observation_log` via new `_emit_token_metric()` helper (chars + approx_tokens + n_elements as a `token_metric` observer_id). New DB helper `upsert_screen_action_frontier()` in `shared/screen_map_db.py`. **Live-validated**: 13 frontier rows persisted from one auth-confirm tick; run `73cc17ca-8a74-456d-8616-f3c5410cea26` COMPLETED, 0 regressions, 0 frontier-write warnings.
- [X] T044 [US1] Added `tools/casino_qa/_transition_recorder.py::record_outcome_safely()` — UPSERTs `transition_outcomes` (observed_count++) AND appends `transition_observations` (workflow_id from `activity.info()`, build_env/app_version from env, outcome ∈ {success|verify_fail}). Wired into `smart_tap.py` (verified-success, divergent-screen, optimistic-skip-verify branches) and `verify_tap.py` (verified-success + divergent branches). Two new DB helpers: `upsert_transition_outcome()` and `record_transition_observation_event()`. Both writes are independent + best-effort (FR-027). **Inline-tested**: observed_count increments correctly on second observation; helpers callable outside an activity context (workflow_id="" fallback). **Not yet live-exercised**: candidate run reused a sticky-authenticated Appium session and never fired a verified tap.
- [X] T045 [US1] Extended `tools/casino_qa/generate_report.py` with spec-005 dual-emit path. When called with `workflow_id`, writes BOTH `reports/<date>-<workflow>.json` (per `contracts/run_report.schema.json`) AND a rendered markdown sibling. Pulls `rounds` from `game_rounds` (new `get_rounds_for_workflow()`) and `transitions_added` from `transition_outcomes` (new `get_transitions_added_since()`) — planner only supplies session-level fields it knows. Optimizations panel defaults to `active` for T024/T027 deliveries; `prompt_cache.status='degraded'` until T028 lands. Legacy slingo report path preserved for backwards-compat. **Inline-tested**: emitted valid JSON+MD pair from in-memory DB.
- [X] T046 [US1] Added `extract_game_tiles()` in `observers/screen_identity.py` — matches tile resource-ids (`game_tile`/`lobby_tile`/`casino_tile`/`tile_card`), extracts (slug, display_name, kind) tuples; kind inferred from `_KIND_KEYWORDS` substring match with caller-supplied `fallback_kind`. New `_autorecord_lobby_walk()` in `observer_activity.py` activates only on a closed-set of lobby screen ids (`home_lobby`, `casino_home`, `casino_lobby`, `lobby_category`, `casino_category`, `all_games`, `popular_games`, `new_games`). Conservative by design: avoids polluting the directory with non-tile UI controls. New DB helper `upsert_game_directory()` (UPSERT with COALESCE preserves existing popularity / aliases when caller doesn't pass them). **Inline-tested**: 2 tile rows from a sample lobby XML; popularity preserved on re-upsert. **Not yet live-exercised**: candidate auth-confirm run landed on `home`, which is intentionally NOT in the lobby-screen set (no game tiles to harvest).

**T043–T046 implementation addendum:**
- The frontier writer is intentionally idempotent on (screen_sig, element_id) — re-visits don't bump `attempted_count`. That bump comes via the verify_tap/smart_tap path, which now also writes the stochastic-outcomes mirror (T044).
- `extract_interactive_elements` extends `parse_page_source` with `clickable`/`focusable`/`scrollable` attributes (previously dropped). Backwards-compat: existing callers see the same shape plus three new keys.
- The new in-process Appium SSE session keeps the device authenticated across worker restarts, which means short auth-confirm runs cannot exercise T044 / T046 on a clean slate. Force-clearing the casino app data was attempted but correctly blocked by the sandbox without explicit user authorization. Full live exercise of T044 + T046 will happen in T052 (the spin-to-win end-to-end smoke) when the device is actually navigated to game tiles.

**LIVE VALIDATION (T032–T046, post-restart)**: end-to-end run `73cc17ca-8a74-456d-8616-f3c5410cea26` COMPLETED. Tool registry: 9 → 14. Intent registry: 4 → 7. Zero `RestrictedWorkflowAccessError`, zero failed activations, zero observer-write warnings. `is_intent_reachable` activity ran once with `reachable=True` (the previous T031 first-turn regression is gone). 13 `screen_action_frontier` rows persisted from a single page-source observation. Diff vs baseline `bfee6b5d-f279-4569-8dd3-78a08f4e8726`: zero regressions; numbers (LLM calls, duration) artificially low because the device was already authenticated from the prior run — apples-to-apples comparison requires a clean install, deferred to T052.

### Smoke + tests

- [X] T047 [US1] Extended `scripts/smoke_play_intent.py` with `--game <slug>` shortcut. Known slugs (`spin_to_win`, `blackjack`, `slingo_classic`, `roulette`) map to canonical prompts; unknown slugs template to `play fanatics <slug>`. `--prompt` overrides `--game` when both supplied. `--help` lists the known slugs explicitly.
- [X] T048 [P] [US1] Authored `tests/contract/test_session_intent_schema.py` — 14 tests covering every flow (play/navigate/audit/observe/report_only) and every kind in the schema enum, plus the cap-math invariant (`requested=50, env=10 → effective=10`). Strips `_meta` audit field before validation. **All 14 pass.**
- [X] T049 [P] [US1] Authored `tests/contract/test_plan_next_action_schema.py` — 6 tests asserting (a) every loaded intent appears in the schema enum, (b) sample emissions for every registered intent validate, (c) drift-detection rejects a fabricated `intent_drift_test`, (d) `next` outside the closed-set {confirm,question,pick-new-goal,done} is rejected. **All 6 pass.**
- [X] T050 [P] [US1] Authored `tests/integration/test_budget_envelope.py` — 9 tests covering ParseSessionIntent cap math, `lower_budget()` clamping (silent on excess, real on stricter), `BudgetCheck` terminal selection at exactly -max_loss, and a full end-to-end audit assertion that the run-report records BOTH `max_loss_requested=50` and `max_loss_effective=10` (FR-005). Validation uses `referencing.Registry` to resolve the cross-file `$ref` from `run_report.schema.json` → `session_intent.schema.json`. **All 9 pass.**
- [X] T051 [P] [US1] Authored `tests/integration/test_resolver_eval_set.py` — 55 tests against an in-memory directory of 23 representative games (slingo flagship line, slots, blackjack, roulette, live tables). 39 resolved cases covering exact-name, kind-filtered LIKE, alias substring (US/EU roulette aliases, "stw", "doa", "multihand"), token-set fallback (word reorder: "quest gonzo", "dead book"), and popularity tie-breaks. 8 explicit-unresolved cases (`poker`, `baccarat`, `keno`, `🎰`, …) verify the resolver falls open rather than picking a low-confidence match. Plus 2 explicit-slug shortcut tests. **Eval-set size guard tests `≥ 50`**; **all 55 pass**.
- [ ] T052 [US1] End-to-end smoke: `uv run scripts/smoke_play_intent.py --game spin_to_win --prompt "play fanatics spin to win" --timeout 600` — assert ≥1 round in `game_rounds`, terminal_reason set, optimizations panel all `active`

**Checkpoint**: User Story 1 fully functional. The agent plays Spin to Win end-to-end from a vague prompt, bounded by MAX_LOSS_USD=10. MVP demoable.

---

## Phase 4: User Story 2 — Blackjack (Priority: P1)

**Goal**: Same pipeline as US1 but the table game has hit/stand/double/split decisions and dealer-state polling.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game blackjack --prompt "play fanatics blackjack" --timeout 900` plays ≥1 hand with sensible decisions; report shows hand outcome and balance delta.

- [ ] T053 [P] [US2] Optional ops seed: `scripts/seed_directory.py --slug fanatics_blackjack --kind blackjack --aliases '["fanatics blackjack","blackjack"]' --popularity 5`
- [ ] T054 [US2] Extend `scripts/smoke_play_intent.py` mapping `--game blackjack` → prompt `"play fanatics blackjack"` (no per-game code; just CLI sugar)
- [ ] T055 [P] [US2] Integration test `tests/integration/test_blackjack_dealer_polling.py` — assert that observing the same dealer-state signature twice in a row triggers re-poll, not double-tap (US2 acceptance scenario 3)
- [ ] T056 [US2] End-to-end smoke against a Fanatics Blackjack table; assert ≥1 full hand played, decisions recorded in `game_rounds.notes`, hand outcome in `outcome` field

**Checkpoint**: US2 working. The per-kind abstraction (`game_kinds/blackjack.md`) reused; no per-game Python introduced.

---

## Phase 5: User Story 5 — Slingo (Priority: P1)

**Goal**: Slingo Classic plays through ≥1 base round; bonus-trigger signature → bonus sub-routine → exit cleanly. Slingo is the agent's flagship product line.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game slingo_classic --prompt "play slingo" --timeout 1200` plays N base rounds; if a bonus triggers within budget, the bonus sub-intent fires and exits cleanly to base.

- [ ] T057 [P] [US5] Author `intents/intent_play_bonus.md` — id, allowed_tools (no betting tools — frozen wager), max_actions=30, end_state_signatures includes base-grid signature, exit-on-loop guard
- [ ] T058 [US5] Wire `intent_play_bonus` into `graphs/casino_session.yaml` — `trigger: bonus_trigger_signature`, `returns_to: play_game`, `frozen_wager=true` constraint
- [ ] T059 [US5] Extend `workflows/agent_goal_workflow.py` to detect `bonus_trigger_signature` from `game_playbook.bonus_trigger_signatures` after each `play_game` round and switch active_intent (preserves replay determinism)
- [ ] T060 [P] [US5] Integration test `tests/integration/test_bonus_exploration.py` — when bonus enters a screen with no signature, assert frozen_wager remains true, max_actions bounded at 30, novel screens land in `signature_proposals` (research §R9)
- [ ] T061 [US5] End-to-end smoke against `slingo_classic`; assert ≥1 base round; if bonus triggers, `game_rounds.bonus_round_id` is populated and base play resumes

**Checkpoint**: US5 working. The Slingo kind validated; the `intent_play_bonus` sub-intent decoupled cleanly via the plan-graph trigger.

---

## Phase 6: User Story 7 — Verify the self-improving loop (Priority: P1)

**Goal**: Run goal X twice on a stable build, with operator review of proposals between. Second run drops planner LLM turns by ≥40% across the equivalent flow segment.

**Independent Test**: Run two smokes, accept proposals between, assert ≥40% LLM-turn reduction.

- [X] T062 [US7] Implemented `scripts/run_compare.py` — pulls two `temporal workflow show -o json` results, boils each into ~10 metrics (status, duration_s, llm_calls, observer_ticks, tool_dispatches, activity_breakdown by-type, signal_counts, failed_activity_count), and diffs them. Hard regression thresholds: `+10%` LLM calls or `+25%` duration → exit 1 + REGRESSIONS section. Used both for spec-005 regression guard (post-prompt-overhaul vs pre-overhaul auth flow) and US7 (run-1 vs run-2 self-improving-loop verification). Self-comparison sanity check passes (baseline vs itself → 0 regressions).
- [ ] T063 [P] [US7] Integration test `tests/integration/test_replay_determinism.py` — record a workflow's history, replay with mocked Anthropic client that raises if called; assert replay completes without LLM invocation (research §R6, FR-035)
- [ ] T064 [US7] End-to-end: smoke US1 (first run, novel screens) → `scripts/scan_signature_proposals.py --since 1h` + `accept_signature_proposal.py <cluster> --as <name>` → smoke US1 (second run, same build); assert second run's `intents[].llm_calls` ≤ 0.6 × first run's (SC-004)
- [ ] T065 [US7] Document the replay-determinism boundary explicitly in `agent-harness.md` — "the planner LLM activity is the only non-deterministic boundary; replay reads from history" (research §R6)

**Checkpoint**: US7 verified. The cost-reduction claim is measurable on every PR.

---

## Phase 7: User Story 9 — Verify proposals dashboard (Priority: P1)

**Goal**: Operator scans clustered proposals (DOM-skeleton dedup), accepts canonicals with `--as <logical_name>`, rejects noise. Throughput cap enforced.

**Independent Test**: Generate ≥10 near-dupe proposals; clusters into ≤3 review items; accepted proposals stop reappearing.

- [ ] T066 [US9] Extend `scripts/scan_signature_proposals.py` — compute `dom_skeleton_hash` for each proposal (strip text/images/dynamic IDs/timestamps from page-source XML, hash structure); GROUP BY skeleton, render as clusters with evidence links (research §R7)
- [ ] T067 [US9] Extend `scripts/accept_signature_proposal.py` — accept `--as <logical_name>` flag; create or attach `logical_screens` row; bind all hashes in cluster via `screen_signatures.logical_id`; mark `signature_proposals.status='accepted'`
- [ ] T068 [US9] Add `--reject` and `--cooldown <duration>` flags to `scripts/accept_signature_proposal.py` — set `signature_proposals.status='rejected'`, `rejected_cooldown_until`, suppress identical skeletons during cooldown
- [ ] T069 [US9] Implement operator-queue cap check in `activities/intent_activity.py` — count pending proposals; if > `PROPOSALS_PER_WEEK_BUDGET`, set workflow state `exploration_throttled=true` and reduce ε in `intent_explore` policy from 0.10 → 0.02 (gaps §C1)
- [ ] T070 [P] [US9] Integration test `tests/integration/test_dedup_clustering.py` — synth 10 proposals with rotated banners but same DOM skeleton; assert clusters ≤ 3 (SC-006)
- [ ] T071 [P] [US9] Integration test `tests/integration/test_accept_proposal_binding.py` — accept a cluster; run a second flow over the same screens; assert `signature_proposals.status` not regenerated for those skeletons (FR-030)
- [ ] T072 [US9] Surface `operator_actions[kind=proposals_pending|exploration_throttled]` rows in run-report JSON per `contracts/run_report.schema.json`

**Checkpoint**: US9 working. The pit-boss workflow is usable; queue saturation auto-throttles exploration without halting goal runs.

---

## Phase 8: User Story 10 — Verify workflow optimizations (Priority: P1)

**Goal**: Per-run dashboard confirms all five optimizations are active. Failure to enforce blocks PRs.

**Independent Test**: Open any recent run report; `optimizations.*` all read `active`; per-turn input p50 ≤ 30K chars; cache hit rate ≥ 0.85.

- [ ] T073 [US10] Implement optimization-status emitter in `activities/observer_activity.py` — five fields per `contracts/run_report.schema.json::optimizations`: `page_source_excluded`, `tool_result_tiering`, `history_compactor`, `prompt_cache.{status, hit_rate}`, `replay_determinism`. Each derived from runtime checks (e.g. cache hit rate from Anthropic response metadata, page_source_excluded from a regex over recent prompt-history events)
- [ ] T074 [US10] Persist per-turn input-token p50/p95 in `observation_log` and aggregate into `RunReport.intents[].{input_chars_p50, input_chars_p95}`
- [ ] T075 [P] [US10] Integration test `tests/integration/test_optimization_panel.py` — run a smoke, parse run report; assert all five optimizations `active`, page_source absent from prompts (regex over captured turns), cache hit rate ≥ 0.85, history compactor produces ≤ 2 verbatim entries beyond last-N, p50 ≤ 30K chars (SC-007)
- [ ] T076 [US10] Implement `scripts/cost_meter.py` — read mid-run from `observation_log` for given `--workflow <id>`; print rolling per-turn input p50 + cache hit rate
- [ ] T077 [US10] CI gate: add to `pyproject.toml` test config so `tests/integration/test_optimization_panel.py` runs on every PR (gaps §D3)

**Checkpoint**: US10 verified. Silent regressions in cost optimizations are caught at PR time.

---

## Phase 9: User Story 3 — Fire Roulette (Priority: P2)

**Goal**: Place ≥1 bet inside the time-pressured betting window; skip rounds where window <2s remaining.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game fire_roulette --prompt "play fanatics fire roulette" --timeout 900` records bet placements with timestamps relative to window-close; missed-window events flagged.

- [ ] T078 [P] [US3] Optional ops seed: `scripts/seed_directory.py --slug fanatics_fire_roulette --kind roulette --aliases '["fire roulette"]'`
- [ ] T079 [US3] Add roulette-specific success_check to `intents/intent_play_game.md` (declarative; reads `game_kinds/roulette.md::time_constraints.betting_window_ms`) — bet only if `time_remaining_ms > 2000`
- [ ] T080 [P] [US3] Integration test `tests/integration/test_roulette_window_skip.py` — synth a betting window with 1.5s remaining; assert agent skips, no bet placed
- [ ] T081 [US3] End-to-end smoke against Fire Roulette; assert ≥1 bet inside window, missed-window events (if any) flagged in run report

**Checkpoint**: US3 working. The roulette kind handles time-pressured bets; no per-game code added.

---

## Phase 10: User Story 4 — Multihand Blackjack (Priority: P2)

**Goal**: Multi-hand round (3+ hands), distinct decisions per hand, bust handling.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game multihand_blackjack --prompt "play fanatics multihand blackjack" --timeout 900` plays a 3+ hand round with per-hand decisions in `game_rounds.notes`.

- [ ] T082 [P] [US4] Optional ops seed: `scripts/seed_directory.py --slug fanatics_multihand_blackjack --kind blackjack --aliases '["multihand blackjack"]'`
- [ ] T083 [US4] Extend `tools/slingo_qa/ReadBalance.py` to also extract per-hand state from page-source for blackjack kind (uses `game_playbook` per-hand selectors learned during US2)
- [ ] T084 [P] [US4] Integration test `tests/integration/test_multihand_independence.py` — synth a 3-hand state where hand 1 busts; assert hand 2/3 decisions are independent and the busted hand is not retried
- [ ] T085 [US4] End-to-end smoke; assert per-hand decisions and aggregate balance delta in run report

**Checkpoint**: US4 working. The play-loop primitive handles parallel decision streams via the same `intent_play_game` (no fork).

---

## Phase 11: User Story 6 — Slot game (Priority: P2)

**Goal**: A production slot plays through ≥1 round; novel autospin/max-bet → signature_proposal not halt.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game any_slot --prompt "play any slot for 5 minutes" --timeout 600` plays N rounds.

- [ ] T086 [US6] Extend `scripts/smoke_play_intent.py` mapping `--game any_slot` → resolver picks top-popularity slot; `--game cleopatra_slot` for fixed pick
- [ ] T087 [P] [US6] Integration test `tests/integration/test_slot_autospin_proposal.py` — encounter a slot whose autospin button has no `screen_elements` row; assert a `signature_proposals` row is created, not a workflow halt
- [ ] T088 [US6] End-to-end smoke against a chosen slot title; assert spin → round-end signature reached within `WaitForSignature` timeout

**Checkpoint**: US6 working. The slots kind generalizes from Spin-to-Win (US1).

---

## Phase 12: User Story 8 — Verify screengraph completeness via exploration (Priority: P2)

**Goal**: `intent_explore` walks unseen rooms within budget; `render_graph.py` produces a viewable map; `graph_diff.py` highlights deltas. Destructive edges blacklisted.

**Independent Test**: Run `scripts/smoke_explore.py` with budget; produce graph rendering and diff vs baseline.

- [ ] T089 [P] [US8] Author `intents/intent_explore.md` — id, allowed_tools=[Explore, SmartTap, VerifyTap, FindElementWithFallback, SaveEvidence], frontier-driven priority queue, budget=(max_screens, max_actions, max_minutes), destructive-edge blacklist
- [ ] T090 [P] [US8] Implement `tools/slingo_qa/Explore.py` — read `screen_action_frontier` rows for `current_signature`; rank: unattempted > low success-rate > stale (research §R7-extended); skip rows where `screen_elements.side_effect='destructive'`; emit chosen `(element_id, action)` for `SmartTap`
- [ ] T091 [P] [US8] Add `tools/registry/Explore.yaml`
- [ ] T092 [US8] Implement `scripts/smoke_explore.py` — start workflow with `flow=audit, intent=explore, budget={max_screens, max_actions, max_minutes}`; tail until terminal
- [ ] T093 [P] [US8] Implement `scripts/render_graph.py` — query `screen_signatures` + `transition_outcomes` filtered by `--build cert --platform android`; emit Mermaid for ≤50 nodes else d3 force-layout HTML; click-through to evidence
- [ ] T094 [P] [US8] Implement `scripts/graph_diff.py` — compare two graph snapshots (added/removed nodes, added/removed edges, distribution shifts ≥ `OUTCOME_DRIFT_THRESHOLD`); emit markdown for PR comment
- [ ] T095 [P] [US8] Integration test `tests/integration/test_explore_destructive_blacklist.py` — synth a screen with a `deposit_submit` element (`side_effect='destructive'`); assert `intent_explore` records it but never traverses it (US8 acceptance scenario 4)
- [ ] T096 [US8] End-to-end exploration smoke; assert M ≥ 1 previously-unseen screens visited, render_graph.py produces an HTML file, graph_diff.py vs `graphs/baselines/main.snapshot` produces a non-empty markdown delta

**Checkpoint**: US8 verified. The casino floor map grows beyond goal-paths; the operator can review the week's deltas in <15 min (SC-005).

---

## Phase 13: Polish & Cross-Cutting Concerns

**Purpose**: Unit tests, contract validation, agent-harness doc updates, baseline snapshots.

- [ ] T097 [P] Unit test `tests/unit/test_screen_graph_decay.py` — per-surface staleness, build mismatch ×0.5, version mismatch ignore-at-read
- [ ] T098 [P] Unit test `tests/unit/test_stochastic_outcomes.py` — UPSERT increments, `screen_transitions` view returns top-`observed_count`
- [ ] T099 [P] Unit test `tests/unit/test_loop_detector.py` — same-screen 5× in 20-action window → BackOff activity invoked, then terminate-intent if still looping (FR-024, gaps §E2)
- [ ] T100 [P] Unit test `tests/unit/test_auto_demote.py` — 3 consecutive failures on graduated row → tier drops one notch; 5 → `needs_review=true` flag (FR-027)
- [ ] T101 [P] Unit test `tests/unit/test_animation_timings.py` — Welford's online-update converges to expected mean/stddev/p95 for synthetic samples; build/version mismatch ignored at read
- [ ] T102 [P] Contract test `tests/contract/test_run_report_schema.py` — validate every emitted run-report against `contracts/run_report.schema.json`
- [ ] T103 [P] Contract test `tests/contract/test_plan_graph_schema.py` — validate `graphs/casino_session.yaml` against `contracts/plan_graph.schema.json` at worker boot (catch malformed graphs early)
- [ ] T104 Implement optional `scripts/seed_directory.py` — accepts `--slug`, `--kind`, `--aliases`, `--popularity`; UPSERTs `game_directory` row (used by US2/US3/US4/US6 ops seeds; ALL OPTIONAL — primary mechanism is lobby-walk)
- [ ] T105 Take baseline graph snapshot for `main` branch — `scripts/render_graph.py --snapshot graphs/baselines/main.snapshot` (used by US8 graph_diff)
- [ ] T106 Update `agent-harness.md` — add directory-vs-playbook split, plan-graph YAML, optimization panel, replay-determinism boundary
- [ ] T107 Run `quickstart.md` validation: all 6 game smokes (US1–US6), 4 verification rituals (US7–US10), all `optimizations.*` active
- [ ] T108 Fix `scripts/smoke_login.py` stale success marker — replace `re.compile(r"LOGIN PASS")` with `re.compile(r"intent_authenticate.*PASS|Authentication COMPLETE|Casino Session Complete.*intent_authenticate")` to match post-spec-004 intent reporter output (uncovered during spec-005 pre-flight baseline)
- [ ] T109 Delete legacy `goals/slingo_qa_android/` — only after T042 (worker startup migrated to `goal_casino_session`) AND T052 (US1 end-to-end smoke green). Removes: directory + import in `goals/__init__.py:14` + import + AGENT_GOAL setdefault in `scripts/run_worker_android.py:13,74,79` + commented `.env.example:46` line.

**Checkpoint**: All user stories implemented, all optimization gates measured, all docs reflect reality.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Standalone; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS all user-story phases.** Schema migrations (T004–T012) must complete before any tool that touches the DB. Prompt overhaul (T024–T028) must complete before any new intent runs (else the agent inherits the bloated prompt).
- **User Stories (Phases 3–12)**: All depend on Foundational. P1 stories (US1, US2, US5, US7, US9, US10) form the MVP. P2 stories (US3, US4, US6, US8) extend after MVP.
- **Polish (Phase 13)**: Depends on all desired user stories.

### Inter-story dependencies (kept minimal — most stories are independent)

- **US2, US5** depend on US1 only at the smoke-script level (`smoke_play_intent.py`'s `--game` flag); intent files and tools are reused as-is. Both can start in parallel after Foundational.
- **US7** (self-improving loop verify) requires at least one play-flow to exist (US1 minimum).
- **US9** (proposals dashboard) is independent of play stories; depends only on Foundational.
- **US10** (optimizations verify) is independent; depends only on Foundational + at least one run available to inspect.
- **US3, US4, US6** are P2 deltas on US1/US2; share all infrastructure.
- **US8** (exploration) depends only on Foundational; can run in parallel with all play stories.

### Within each user story

- Intent declarations (`intents/*.md`) and tool implementations (`tools/slingo_qa/*.py`) are file-disjoint — all tasks marked `[P]` truly parallelize.
- Wiring task (worker startup) depends on intents + tools being in place.
- Smoke validation task is the final task per phase.
- Tests for a story are file-disjoint — all marked `[P]`.

### Parallel opportunities (concrete examples)

**Within Phase 2 Foundational** — schema migrations T004–T012 touch the same file (`shared/screen_map_db.py::ensure_schema()`) so are sequential by file-conflict; game-kind files T017–T020 are file-disjoint and run in parallel; planner-prompt overhauls T024–T028 touch `prompts/generators.py` so are sequential by file-conflict (one developer or sequential commits).

**Within Phase 3 (US1)** — T032–T035 (intents) and T036–T040 (tools) are all file-disjoint and run in parallel. T041 (registry side-cars) is a single multi-file commit also parallelizable.

**Across phases (multi-developer)** — after Foundational completes, US1 + US9 + US8 + US10 can be worked on by 4 developers in parallel; US2 + US5 + US7 wait only on US1's smoke wiring.

---

## Implementation Strategy

### MVP (Phase 1 → 2 → 3 → 8 → 7 → 4 → 5 → 6 → STOP and validate)

1. **Phase 1 + Phase 2 (foundational)**: Schema migrated, planner prompt overhaul shipped, plan-graph live, game-kind files in place. *This is the riskiest phase — validate per-turn input p50 with `cost_meter.py` before adding any user-story code.*
2. **Phase 3 (US1)**: Spin to Win end-to-end. Demo: vague-prompt → bounded play → report. **MVP boundary 1.**
3. **Phase 8 (US10)**: Optimization panel + CI gate. *Lock in the cost win before US2 introduces table-game complexity.*
4. **Phase 7 (US9)**: Proposals dashboard. *Operator queue must be drainable before exploration unlocks more proposals.*
5. **Phase 4 (US2)**: Blackjack. Validates kind reuse.
6. **Phase 5 (US5)**: Slingo. Validates bonus sub-intent.
7. **Phase 6 (US7)**: Self-improving loop verify. *Now you have ≥2 stable flows to compare LLM-turn counts against.* **MVP boundary 2.**

After step 7 ships, the system is investor-demoable and CI-gated on cost regressions.

### Incremental delivery (P2 extensions)

8. **Phase 9 (US3)**: Fire Roulette — time-pressured betting.
9. **Phase 10 (US4)**: Multihand Blackjack — parallel decision streams.
10. **Phase 11 (US6)**: A slot — generalization check.
11. **Phase 12 (US8)**: Exploration mode + graph rendering + diffing.
12. **Phase 13 (Polish)**: Unit tests, baseline snapshots, doc updates.

### Parallel team strategy

- **Developer A**: Phases 1 → 2 → 3 (US1) → 4 (US2). Shipping MVP.
- **Developer B**: Phase 8 (US10) + Phase 13 polish concurrently with A's Phase 3+. Cost-gate the MVP.
- **Developer C**: Phase 7 (US9) + Phase 12 (US8). Operator + exploration tooling.
- **Developer D**: Phase 5 (US5) + Phase 6 (US7). Slingo + self-improving verification.

---

## Notes

- **Tests are MANDATORY for the verification user stories (US7, US8, US9, US10)** — those *are* tests of the agent's infrastructure. Other stories' integration tests verify acceptance scenarios from spec.md.
- **`tool_activities.py` and `mcp_client_manager.py` are FROZEN per WF-3** — every reference in this task list works around them via `intent_activity.py`, `observer_activity.py`, `prompts/generators.py`, or new tools.
- **No per-game Python.** Every appearance of "for game X" in this task list is a directory row, a playbook row, or a CLI flag — never a code branch.
- **No hardcoded selectors, regexes, coordinates, or animation waits in any task.** Every value is learned (`screen_elements`, `game_playbook`, `animation_timings`) or declared (`game_kinds/<kind>.md::learned_default` as last-resort).
- **`MAX_LOSS_USD=10` is in `.env` already.** All budget-aware tasks (T039 BudgetCheck, T050 budget-envelope test, T052 smoke) use it.
- Commit after each task or logical group. Stop at any `Checkpoint` to validate the story end-to-end before moving on.
