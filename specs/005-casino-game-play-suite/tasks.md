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

- [ ] T013 Implement `shared/runtime_facts.py` — `RuntimeFacts` dataclass + `load_runtime_facts()` that fuses env (`BUILD_ENV`, `MAX_LOSS_USD`, etc.) with `select_device` MCP result; emits JSON for L3 prompt layer
- [ ] T014 Author `graphs/casino_session.yaml` per `contracts/plan_graph.schema.json` (nodes: parse_session, authenticate, navigate_to_game, load_context, play_game, play_bonus, report; guards: budget, stuck, panic; recovery: reauth, evidence)
- [ ] T015 [P] Create `tools/registry/<ToolName>.yaml` side-cars for existing tools (SmartTap, VerifyTap, LookupCoords, DetectScreen, SaveEvidence, FindElementWithFallback, WaitSeconds, TapCoordinate) — each declares `platforms`, `intents`, `risk_tier`, `schema_ref`, `side_effects` per research §R2
- [ ] T016 Create `activities/intent_activity.py` (NEW per WF-3) — exposes `is_reachable(active_intent, current_state, plan_graph)`, `load_runtime_facts_activity()`, `record_intent_transition()`. **Do NOT touch** `activities/tool_activities.py` or `shared/mcp_client_manager.py` (FROZEN per WF-3)

### Game-kind declarative files (≤400 tokens each, hand-authored)

- [ ] T017 [P] Author `game_kinds/slingo.md` (turn_structure, key_signatures, typical_animations.spin_to_idle_ms learned_default, recoverable_modals)
- [ ] T018 [P] Author `game_kinds/slots.md` (turn_structure: bet_set/spin/round_end, key_signatures: spin_idle/wallet_strip/paytable, typical_animations.spin_to_idle_ms learned_default)
- [ ] T019 [P] Author `game_kinds/blackjack.md` (turn_structure: bet/deal/player_action/dealer_action/settle, key_signatures: dealer_action_pending/hand_settled, recoverable_modals: insurance_offer)
- [ ] T020 [P] Author `game_kinds/roulette.md` (turn_structure: betting_window_open/place_bet/window_close/wheel_result, key_signatures: betting_window/wheel_idle, time_constraints.betting_window_ms)

### Path planner & screen-graph extensions

- [ ] T021 Extend `shared/screen_graph.py::_effective_confidence()` for per-surface decay using `screen_signatures.staleness_days` (null → env `SCREEN_MAP_STALENESS_DAYS`) per research §R4
- [ ] T022 Extend `shared/screen_graph.py` path planner to read from `transition_outcomes` (1-to-N edges) preferring highest `observed_count`, exposing alternatives in plan output, per research §R5
- [ ] T023 Extend `shared/screen_graph.py` to filter edges by `edge_kind`, `side_effect`, and `precondition` predicate evaluated against `RuntimeFacts` per gaps-and-guardrails §A4

### Planner prompt overhaul (cost optimizations FR-031..FR-036)

- [ ] T024 Strip raw page-source content from planner prompt in `prompts/generators.py` — when a tool result has `page_source` or `xml`/`tree` payload, replace with `{success, hash, summary, len, path}` structured stub (FR-031). Apply at the prompt-assembly callers; do not touch the frozen `tool_activities.py` directly
- [ ] T025 Implement intent-conditional tool filter in `prompts/generators.py` — read `tools/registry/*.yaml`, intersect `tools.intents ∋ active_intent` × `tools.platforms ∋ RuntimeFacts.platform`, emit filtered enum into Anthropic `tool_choice.tools` per research §R2
- [ ] T026 Add L4.5 game-knowledge layer in `prompts/generators.py` — when active_intent is one of `intent_load_game_context`/`intent_play_game`/`intent_play_bonus` and a `game_directory.loaded_signature` matches `current_screen_signature`, inject `game_playbook` row + `game_kinds/<kind>.md` content (combined ≤600 tokens) per spec FR-009/FR-010
- [ ] T027 Implement working-memory compactor in `prompts/generators.py` — keep last `N=2` tool results verbatim, summarize older to single line `t-K: <tool>(<args_brief>) → <screen_sig>|<conf>` per setup-doc §4
- [ ] T028 Apply Anthropic `cache_control: {type: "ephemeral"}` to L0+L1 prefix (persona + filtered tool registry) in `prompts/generators.py` per FR-033 / research §R10

### Workflow extensions (allowed by WF-1 v3.0.0)

- [ ] T029 Extend `workflows/agent_goal_workflow.py` to load `graphs/casino_session.yaml` at workflow start as workflow input (replay-safe); store in workflow state
- [ ] T030 Extend `workflows/agent_goal_workflow.py` with `SessionIntent` workflow state field; expose via new `@workflow.query` handler `get_session_intent()` per WF-2
- [ ] T031 Extend `workflows/agent_goal_workflow.py` to call `intent_activity.is_reachable()` after each `plan_next_action`; on unreachable pick, save evidence + fall back to last-known reachable intent (per research §R3); preserve replay determinism (FR-035)

**Checkpoint**: Foundation ready. Schema migrated, prompts overhauled, plan-graph live, game-kind files in place. User-story implementation can begin.

---

## Phase 3: User Story 1 — Spin to Win (Priority: P1) 🎯 MVP

**Goal**: Vague prompt `play fanatics spin to win` → ParseSessionIntent → authenticate (already locked) → navigate to game (recents/category/search/scroll) → load context → bounded play → report.

**Independent Test**: `uv run scripts/smoke_play_intent.py --game spin_to_win --prompt "play fanatics spin to win" --timeout 600` reaches the loaded game, plays ≥1 round, terminates within `MAX_LOSS_USD=10` and default bounds, emits `reports/<id>.{json,md}`.

### Intent declarations (≤600 tokens each, declarative frontmatter only — Principle VI)

- [ ] T032 [P] [US1] Author `intents/intent_parse_session.md` — id, allowed_tools=[ParseSessionIntent], end_state_signatures=session_intent_set, success_check, guardrails (one-shot, runs once at session start)
- [ ] T033 [P] [US1] Author `intents/intent_navigate_to_game.md` — id, allowed_tools, sub_strategies (recents/category_jump/search/scroll_grid), end_state_signature=`game_directory.loaded_signature`, on_unresolved_query branch
- [ ] T034 [P] [US1] Author `intents/intent_load_game_context.md` — id, allowed_tools=[ResolveDirectory, LookupCoords], end_state=context_injected, one-shot
- [ ] T035 [P] [US1] Refine `intents/intent_play_game.md` — id, allowed_tools=[ReadBalance, BudgetCheck, SmartTap, VerifyTap, WaitForSignature, FindElementWithFallback, SaveEvidence], end_state=terminal_reached, repeat_until budget.terminal

### Local QA tools (per data-model + contracts)

- [ ] T036 [P] [US1] Implement `tools/slingo_qa/ParseSessionIntent.py` — Anthropic tool-use forced classifier emitting `SessionIntent` per `contracts/session_intent.schema.json`; closed-set enums for flow/kind/terminal
- [ ] T037 [P] [US1] Implement `tools/slingo_qa/ResolveDirectory.py` — pure SQLite (no LLM): exact slug → kind+LIKE+token-set ratio → popularity/recents rank; returns top match + alternatives + `unresolved` flag (research §R1)
- [ ] T038 [P] [US1] Implement `tools/slingo_qa/ReadBalance.py` — page-source extract via `game_playbook.balance_signature` + `balance_regex`; retry up to `min(3, ceil(1/conf))` times before halt (gaps §A5); writes `game_rounds.balance_read_attempts`
- [ ] T039 [P] [US1] Implement `tools/slingo_qa/BudgetCheck.py` — computes `effective_max_loss = min(env_max_loss, prompt_max_loss or env_max_loss)`; first-of `n_spins | max_minutes | max_loss_usd` terminal; never `max(...)`. Emits structured terminal reason
- [ ] T040 [P] [US1] Implement `tools/slingo_qa/WaitForSignature.py` — read `animation_timings(game_slug, action, build_env, app_version)`; if `samples ≥ 5` use `p95 + 2σ`; else use kind-file `learned_default`; final fallback stable-UI detector (no DOM change for 800ms). Online-update samples via Welford's algorithm (research §R8)
- [ ] T041 [P] [US1] Add `tools/registry/{ParseSessionIntent,ResolveDirectory,ReadBalance,BudgetCheck,WaitForSignature}.yaml` side-cars with `platforms`/`intents`/`risk_tier`/`schema_ref`/`side_effects`

### Worker wiring + observers

- [ ] T042 [US1] Extend `scripts/run_worker_android.py` — register new intents (US1 set), inject `tools/registry/` loader, pass `graphs/casino_session.yaml` as workflow input, register `intent_activity.py` activities. Depends on T032–T041
- [ ] T043 [US1] Extend `activities/observer_activity.py` — auto-recorder writes `screen_action_frontier` rows on every screen visit (enumerate page-source interactive elements, INSERT-OR-IGNORE with attempted_count=0); emit per-turn input-token metrics into `observation_log`
- [ ] T044 [US1] Extend `activities/observer_activity.py` — auto-record `transition_observations` event + UPSERT `transition_outcomes` on every verified tap (preserves MW-1)
- [ ] T045 [US1] Implement run-report emission in `intents/intent_report.md` driver — produce `reports/<run>.json` per `contracts/run_report.schema.json` AND rendered markdown sibling
- [ ] T046 [US1] Add lobby-walk auto-discovery hook in `activities/observer_activity.py` — when on a lobby/category screen, parse visible game tiles → UPSERT `game_directory` rows (slug from accessibility-id, display_name from text, kind from category context)

### Smoke + tests

- [ ] T047 [US1] Extend `scripts/smoke_play_intent.py` — accept `--game <slug>` and `--prompt <text>` flags; route through `start-workflow` API + `send-prompt`; wait for terminal; print summary
- [ ] T048 [P] [US1] Contract test `tests/contract/test_session_intent_schema.py` — feed sample prompts to `ParseSessionIntent` and validate output against `contracts/session_intent.schema.json`
- [ ] T049 [P] [US1] Contract test `tests/contract/test_plan_next_action_schema.py` — assert `active_intent` field is constrained to the 10-intent enum across all turns
- [ ] T050 [P] [US1] Integration test `tests/integration/test_budget_envelope.py` — assert prompt-supplied `max_loss_usd > env_ceiling` is silently capped; report records both values (FR-005)
- [ ] T051 [P] [US1] Integration test `tests/integration/test_resolver_eval_set.py` — 50+ canonical query→slug pairs; `pytest` on every PR (gaps §D1)
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

- [ ] T062 [US7] Implement `scripts/run_compare.py` — read two run JSONs, compute LLM-turn delta, transitions added, signatures proposed, balance delta; emit markdown comparison
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
