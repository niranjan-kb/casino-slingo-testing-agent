# Implementation Plan: Casino Game-Play & Verification Suite

**Branch**: `005-casino-game-play-suite` · **Date**: 2026-05-06 · **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `/Users/niranjan.kurambhatti/Projects/FBG/casino-slingo-testing-agent/specs/005-casino-game-play-suite/spec.md`

> **Operator mandate (from /speckit.plan invocation)**: "Absolutely no hardcoding at all. Think like a real casino player." The improving step is **per-action**: Play → improve → Navigate → improve → Search/Find → improve → Play → improve → unknown-screen/popup → improve. Encoded as constitution gates and design choices throughout.

## Summary

Extend the auth-only POC into a multi-game player + self-verifying QA harness for the Fanatics casino app on Android. Six target games (Spin to Win, Blackjack, Fire Roulette, Multihand Blackjack, Slingo, a slot) play end-to-end from vague prompts under a hard env loss ceiling, while four verification stories prove the self-improving infrastructure (loop, screen-graph completeness, proposals dashboard, workflow optimizations) is actually doing its job.

**Technical approach (uncompromising map-first)**:

1. **Nothing about a game lives in code.** Selectors, coordinates, balance regexes, animation waits, action sequences, bonus-trigger signatures, screen identifiers — all learned from observed play and written to `data/screen_map.db`. Adding a game = adding a directory row (auto via lobby-walk or ops seed) + auto-populated playbook on first launch. Adding a game *kind* = adding `game_kinds/<kind>.md` (≤400 tokens, hand-authored conceptual abstraction) once.

2. **The "improve" step is per-action.** Every successful tap upserts a `screen_transitions` row; every element resolution upserts a `screen_elements` row; every novel signature emits a `signature_proposals` row; every animation contributes a sample to `animation_timings`. Map-first lookup precedes the LLM on every turn.

3. **Vague-prompt → resolver → plan graph.** A new `intent_parse_session` compiles operator prompts to a structured `SessionIntent` via tool-use forcing (same pattern as the planner). The resolver walks the directory only — pure SQL, no LLM. The plan graph (`graphs/casino_session.yaml`) drives reachable-intent enforcement; per-turn the planner picks `active_intent` from the closed-set registry as today.

4. **Bounded play, replay-safe.** `MAX_LOSS_USD=10` (already in `.env`) is the hard env ceiling; vague prompts also get default `max_spins=20`/`max_minutes=10` (first terminal wins). The planner LLM call stays inside its existing single activity — replay reads the captured tool-use response from history; the cache discount is performance, not correctness.

5. **Verification stories are first-class user stories**, not afterthoughts. Run-report JSON, optimization-status panel, render_graph.py, graph_diff.py, dedup-clustered proposals dashboard. The agent verifies its own infrastructure on every run.

## Technical Context

**Language/Version**: Python 3.10 (`.venv` via `uv`).
**Primary Dependencies**: `temporalio` (durable spine, replay-deterministic), `litellm` → AWS Bedrock (`claude-sonnet-4-5` via `bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0`), `pyyaml` (intents, manifests, plan graph), `httpx` (MCP SSE). MCP layer: `appium-mcp@1.56.3` (PINNED per MCP-2) on port 3100, persistent SSE.
**Storage**: SQLite at `data/screen_map.db` is the runtime source of truth (Principle I). Tables added below in §"Project Structure → Data". Markdown files in `intents/` and `game_kinds/` are declarative spec only (≤600 / ≤400 tokens). No JSON seed files for game playbooks (the playbook auto-populates).
**Testing**: `uv run pytest --workflow-environment=time-skipping` for unit + workflow replay tests; `scripts/smoke_play_intent.py` for end-to-end on a real Android emulator. New per-game smoke variants: `--game spin_to_win`, `--game blackjack`, `--game fire_roulette`, `--game multihand_blackjack`, `--game slingo_classic`, `--game cleopatra_slot`.
**Target Platform**: Android only for this feature (cert build `com.betfanatics.casino.cert`, resolution discovered at `select_device` time, never pre-injected). iOS / web deferred per spec Assumptions.
**Project Type**: Single project (existing repo layout). No new top-level dirs except `game_kinds/` and `graphs/`.
**Performance Goals**:
- Per-turn planner input p50 ≤ 30K characters; p95 ≤ 45K (SC-007).
- Static-prelude prompt-cache hit rate ≥ 85% across cacheable turns (SC-007, FR-033).
- Second-run LLM-turn count drops ≥ 40% across the equivalent flow segment after operator review (SC-004, US7).
- 10+ near-duplicate proposals from a noisy run cluster into ≤ 3 review items (SC-006).
- Operator-review time ≤ 15 min for an exploration session graph + diff (SC-005).
**Constraints**:
- `MAX_LOSS_USD` env ceiling is **hard**; prompt budget can only lower it (FR-003, FR-004).
- All learned scalars keyed by `(build_env, app_version)` where applicable (FR-021).
- Map-first / LLM-fallback contract preserved on every action (Principle I, FR-018).
- WF-3: `activities/tool_activities.py` and `shared/mcp_client_manager.py` are FROZEN — extensions go in new activity files.
- MCP-2: `appium-mcp` pinned to 1.56.3.
- Replay determinism: planner LLM call lives in its single existing activity; replay reads from history (FR-035).
**Scale/Scope**: Six target games (US1–US6), four game kinds (slingo, slots, blackjack, roulette), ~200 screens at app maturity, ~50 elements/screen at the high-fanout lobby, single Android device per worker (SC-1).

## Constitution Check

*Gate: must pass before Phase 0 research; re-evaluated after Phase 1.*

| Principle / Rule | This feature's compliance |
|---|---|
| **I. Map-first; LLM is fallback** | ✅ All game knowledge (directory, playbook, signatures, transitions, animations) lives in `data/screen_map.db`. Markdown is declarative-only, ≤600 tokens, no per-game prose. New tables (`game_directory`, `game_playbook`, `transition_outcomes`, `screen_action_frontier`, `animation_timings`, `game_rounds`, `transition_observations`, `logical_screens`, `logical_elements`) extend SQLite, do not introduce JSON seed for runtime data. |
| **II. One agent, intents at runtime** | ✅ Six new intents (`intent_parse_session`, `intent_navigate_to_game`, `intent_load_game_context`, `intent_play_bonus`, `intent_explore`) — *not* per-game files. The planner picks `active_intent` per turn from the closed-set registry. New games are directory + playbook rows, never new intents or goals. |
| **III. Observers never halt the loop** | ✅ Auto-recorders for transitions, elements, animations, rounds wrap writes in try/except (FR-027 reinforces this for graduated-row failures: auto-demote, not halt). |
| **IV. Self-healing non-negotiable** | ✅ FR-024 (loop detector with back-off), FR-027 (auto-demote on graduated-row failure), FR-014 (bonus exploration on novelty), spec edge cases (modal interrupts, hangs, build version drift). No `next='question'` for routine recovery. |
| **V. Risk tiers gate confidence promotion** | ✅ All new HIGH-tier elements (spin_button, place_bet, deposit_confirm equivalents) NEVER graduate. MEDIUM/LOW thresholds inherit from constitution V. Single failure on graduated row → reset (existing rule preserved). |
| **VI. Operational soul only in runtime prompts** | ✅ Each new intent file ≤600 tokens, declarative-only frontmatter (`id`, `allowed_tools`, `end_state_signatures`, `success_check`, `guardrails`, `risk_tier`). No prose phases, no example conversations, no Python-described loops. Per-kind files ≤400 tokens. |
| **VII. Human approval at financial boundaries** | ✅ Bets in cert respect `SHOW_CONFIRM=False` for autonomous smoke; in `prod-debug`/`prod` `SHOW_CONFIRM=True` is required (existing). `MAX_LOSS_USD=10` env ceiling is the additional safety cap. |
| **PT-1..PT-5** (platform topology) | ✅ Android worker on macOS outside Docker (PT-2). One worker = one platform = one device = one MCP = one session (PT-5). |
| **MCP-1..MCP-3** | ✅ All device interaction stays MCP (`appium-mcp@1.56.3`). No direct ADB. |
| **SC-1..SC-3** (scalability) | ✅ Task queue stays `casino-qa-android` (derived from `RuntimeFacts.platform`, not hardcoded). Workers stateless; state in Temporal + SQLite. |
| **WF-1..WF-3** (workflow contract) | ✅ `agent_goal_workflow.py` extended (allowed by WF-1 v3.0.0); replay determinism preserved; new state via `@workflow.query` (WF-2); `tool_activities.py` + `mcp_client_manager.py` UNTOUCHED — new activities live in `activities/observer_activity.py` (extended) and `activities/intent_activity.py` (new). |
| **MW-1..MW-4** (map writeback) | ✅ Every verified tap → `screen_transitions` (MW-1). Every `FindElementWithFallback` hit → `screen_elements` (MW-2). Read-time-decayed confidence (MW-3); never destructively modified. Unknown screens ≥3× / ≥2 runs → `signature_proposals`; auto-promotion FORBIDDEN (MW-4). |
| **No-hardcoding mandate (operator)** | ✅ Concrete forbidden-list documented in §"Anti-hardcoding inventory" below. Every item has its non-hardcoded counterpart. |

**Verdict**: All gates pass. No violations to justify in Complexity Tracking.

### Anti-hardcoding inventory (operator mandate)

The following are **forbidden in code** for this feature; each maps to its data-driven source:

| Forbidden | Lives in |
|---|---|
| Selectors (`accessibility-id`, `xpath`, `uiautomator2`) per game | `screen_elements` rows, learned via `FindElementWithFallback` + auto-recorder |
| Coordinates (x, y) | `screen_elements.coords` (caller-supplied, observed) |
| Balance regex per game (`\$([0-9.,]+)`) | `game_playbook.balance_regex`, discovered on first info-screen visit via OCR/LLM |
| Animation waits (`time.sleep(5)`, `WaitSeconds(5)`) | `animation_timings(game_slug, action, build_env, app_version) → p95`; learned-default in `game_kinds/<kind>.md` until samples accumulate |
| Action sequences (search-bar → type → result-tap) | `screen_transitions` rows with parameterized `action_template` |
| Phase prose (Phase 0 / Phase 1 / Phase 2 in goal markdown) | `graphs/casino_session.yaml` plan graph + reachable-intent enforcement |
| Credentials, OTP, app pkg, resolution | `RuntimeFacts` JSON loaded at workflow start (creds via `account_ref` → secret store; OTP via `otp_source: static:...|imap:...`; pkg + resolution via `select_device` MCP call) |
| Game name → kind mapping | `game_directory.kind` column |
| Bonus trigger / loaded-game signatures per game | `game_playbook.bonus_trigger_signatures`, `game_directory.loaded_signature` |
| Tool descriptions in goal prompt prose | tool registry; per-intent `allowed_tools` filter feeds Anthropic `tool_choice` enum |
| Risk-tier classification per element | `screen_elements.risk_tier` (operator-set on promotion); the *gate logic* (HIGH never graduates, MEDIUM 90+5, LOW 80+3) is policy, not data |

The only hand-authored content allowed under this mandate:
1. Intent declarations (≤600 tokens each, declarative frontmatter only).
2. Per-kind conceptual abstractions (`game_kinds/<kind>.md`, ≤400 tokens).
3. Plan graph YAML (`graphs/casino_session.yaml`).
4. Tool registry metadata (`tools/registry/<tool>.yaml` or in-code `@register_tool` decorators).

Anything per-game, per-build, per-resolution, per-jurisdiction, per-account is **data**, not code.

## Project Structure

### Documentation (this feature)

```text
specs/005-casino-game-play-suite/
├── plan.md                                          # this file
├── spec.md                                          # ratified
├── research.md                                      # Phase 0 output
├── data-model.md                                    # Phase 1 output
├── quickstart.md                                    # Phase 1 output
├── contracts/                                       # Phase 1 output
│   ├── session_intent.schema.json
│   ├── plan_next_action.schema.json
│   ├── run_report.schema.json
│   └── plan_graph.schema.json
├── checklists/requirements.md                       # already created
└── (background)
    ├── setup-before-scalling-to-game-plays-search.md
    ├── scaling-to-game-plays-and-search.md
    ├── self-improving-loop.md
    ├── complete-screengraph.md
    ├── gaps-and-guardrails.md
    └── manual-intervention-and-maintenance.md
```

### Source code (repository root)

```text
intents/                                             # ≤600 tokens each, declarative frontmatter
├── base.py                                          # existing dataclass + registry loader
├── intent_authenticate.md                           # existing, locked
├── intent_parse_session.md                          # NEW — vague-prompt → SessionIntent
├── intent_navigate_to_game.md                       # NEW — recents/category/search/scroll fallback chain
├── intent_load_game_context.md                      # NEW — pull playbook + kind file on game_loaded
├── intent_play_game.md                              # existing draft, refined
├── intent_play_bonus.md                             # NEW — frozen-wager bonus sub-intent
├── intent_explore.md                                # NEW — coverage-driven exploration with budget
├── intent_navigate_to_screen.md                     # existing — wraps to intent_navigate_to_game when target is a game
└── intent_report.md                                 # existing

game_kinds/                                          # NEW — ≤400 tokens, per-category, hand-authored
├── slingo.md
├── slots.md
├── blackjack.md
└── roulette.md

graphs/                                              # NEW
└── casino_session.yaml                              # plan graph: nodes/edges/guards

goals/casino_session/                                # existing, minimal edits
├── __init__.py                                      # extended to load graphs/casino_session.yaml at boot
└── prompts/                                         # operational soul + tool registry, no creds

shared/
├── screen_map_db.py                                 # extended: 9 new tables (see data-model.md)
├── screen_graph.py                                  # extended: per-surface decay, edge_kind/side_effect/precondition, stochastic outcomes
└── runtime_facts.py                                 # NEW — RuntimeFacts envelope loader (env + select_device → JSON)

tools/slingo_qa/
├── ParseSessionIntent.py                            # NEW — tool-use-forced classifier
├── ResolveDirectory.py                              # NEW — pure SQL, no LLM
├── ReadBalance.py                                   # NEW — page-source extract via playbook regex, retries
├── BudgetCheck.py                                   # NEW — balance_now vs session_start vs MAX_LOSS_USD
├── WaitForSignature.py                              # NEW — learned-wait via animation_timings p95+2σ + stable-UI fallback
├── Explore.py                                       # NEW — frontier-driven (screen, untried_action) selector
├── SmartTap.py                                      # existing
├── VerifyTap.py                                     # existing
├── LookupCoords.py                                  # existing
├── DetectScreen.py                                  # existing
├── SaveEvidence.py                                  # existing
├── FindElementWithFallback.py                       # existing
├── _deps.py                                         # existing
└── registry.yaml                                    # NEW — tool metadata for per-intent filtering

tools/registry/                                      # NEW (alternative to in-tool yaml — TBD in research)
└── (one file per tool with platforms[], intents[], risk_tier, schema_ref)

activities/
├── tool_activities.py                               # FROZEN per WF-3
├── observer_activity.py                             # extended: round telemetry, animation samples, frontier upserts
└── intent_activity.py                               # NEW — plan-graph reachable-intent guard, RuntimeFacts loader

workflows/
└── agent_goal_workflow.py                           # extended (allowed by v3.0.0 WF-1): SessionIntent state, plan-graph guard, intent transitions

prompts/
├── persona/soul.md                                  # existing
└── generators.py                                    # extended: L4.5 game-knowledge layer, intent.allowed_tools filter, T0 page-source strip in _normalize_result, history compactor

scripts/
├── run_worker_android.py                            # extended: load plan graph + new intent registry
├── smoke_login.py                                   # existing
├── smoke_play_intent.py                             # extended: --game CLI flag (6 targets)
├── scan_signature_proposals.py                      # extended: dom_skeleton clustering
├── accept_signature_proposal.py                     # extended: --as <logical_name>, attach-or-create logical
├── render_graph.py                                  # NEW — Mermaid + d3 HTML output, filter by build/conf/age
├── graph_diff.py                                    # NEW — added/removed nodes & edges, distribution-shift detection
└── seed_login_signatures.py / seed_login_transitions.py / scan_signature_proposals.py / accept_signature_proposal.py / accept_skill_proposal.py (DELETED — skills primitive dropped)

data/
└── screen_map.db                                    # runtime source of truth — schema migrations applied via inline ALTER

reports/                                             # already exists; JSON + MD per run
└── <date>-<run_id>.{json,md}

.env                                                 # contains MAX_LOSS_USD=10 (added by operator)

tests/
├── contract/
│   ├── test_session_intent_schema.py                # NEW — validate ParseSessionIntent output against contract
│   ├── test_plan_next_action_schema.py              # extended for active_intent enum
│   ├── test_run_report_schema.py                    # NEW
│   └── test_plan_graph_schema.py                    # NEW
├── integration/
│   ├── test_resolver_eval_set.py                    # NEW — 50+ canonical queries (gaps-and-guardrails D1)
│   ├── test_replay_determinism.py                   # NEW — verify workflow replay never re-invokes Anthropic
│   ├── test_budget_envelope.py                      # NEW — prompt budget can never raise env ceiling
│   ├── test_dedup_clustering.py                     # NEW — 10 near-dupes → ≤3 clusters
│   └── test_optimization_panel.py                   # NEW — page-source absent, cache hit ≥85%, history compactor active
└── unit/
    ├── test_screen_graph_decay.py                   # extended: per-surface, build mismatch, version mismatch
    ├── test_stochastic_outcomes.py                  # NEW
    ├── test_loop_detector.py                        # NEW — same-screen-5×-in-20-actions backoff
    ├── test_auto_demote.py                          # NEW
    └── test_animation_timings.py                    # NEW
```

**Structure Decision**: Single-project layout (existing). New game support is data-only (`game_directory` + `game_playbook` rows). New intents go in `intents/` (≤600 tokens each). New per-category abstractions go in `game_kinds/`. New scripts in `scripts/`. New tables migrated inline at worker boot via idempotent `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` (already the existing pattern). No new top-level dirs beyond `game_kinds/` and `graphs/`.

## Phase 0 — Research & unknown resolution

See `research.md` for full content. Topics resolved:

1. **Resolver design** — pure SQL with `LIKE` + token-set ratio + popularity + recents bias; no LLM. Eval set in `tests/integration/test_resolver_eval_set.py`.
2. **Tool registry shape** — per-tool YAML side-cars under `tools/registry/`, loaded at worker boot, used to filter `tool_choice.tools` per active intent (FR-007, gaps §4 D1).
3. **Plan-graph guard** — workflow rejects `active_intent` not reachable from current node in `graphs/casino_session.yaml`; reachability re-checked after each transition.
4. **Per-surface decay** — `screen_signatures.staleness_days` nullable; falls back to env `SCREEN_MAP_STALENESS_DAYS`. Operator sets at promotion; defaults to surface-class defaults via prefix matching on logical name (gaps A2).
5. **Stochastic outcomes migration** — additive table `transition_outcomes(start_sig, action, end_sig, observed_count, last_seen)`; `screen_transitions` becomes a view (UNION over outcomes' top picks) until callers migrate.
6. **Replay determinism** — planner LLM call already lives in single activity; document explicitly in `agent-harness.md`. Replay test asserts no Anthropic API call during replay (mock client raises if called).
7. **DOM-skeleton dedup** — page-source with text/images stripped, hashed; clusters in proposals dashboard. Validated by 10-near-dupe → ≤3-cluster integration test.
8. **Animation-timing learned-wait** — `WaitForSignature(action, timeout=p95+2σ if samples≥5 else kind_default)`; stable-UI detector (no DOM change for 800ms) as final fallback.
9. **Bonus novelty exploration** — `intent_play_bonus` runs with `frozen_wager=true`, max 30 actions, exits on base-grid signature. New screens land in proposals.
10. **Cache invalidation policy** — worker restart (any soul/registry/tool change ships new bytes → process restart) busts the Anthropic ephemeral cache automatically. No explicit invalidation API.

**Output**: `research.md` resolves all 10 items; no `NEEDS CLARIFICATION` markers remain.

## Phase 1 — Design & contracts

See:
- **`data-model.md`** — full schema for the 9 new/extended tables, FK relationships, write paths, decay/precondition semantics.
- **`contracts/`** — 4 JSON-schemas: `session_intent.schema.json`, `plan_next_action.schema.json` (extended `active_intent` enum + `tool` enum), `run_report.schema.json`, `plan_graph.schema.json`.
- **`quickstart.md`** — three-process boot, env vars (`MAX_LOSS_USD=10`), 6 smoke commands per game, optimization-panel inspection commands, render_graph.py usage.

**Agent context update**: `.specify/scripts/bash/update-agent-context.sh claude` runs after artifacts land (refreshes `CLAUDE.md` "Active Technologies" and "Recent Changes" with the directory/playbook/kind data layout, plan-graph file, and 6 new intents).

## Post-Phase-1 Constitution re-check

After data-model + contracts + quickstart are written, re-evaluating:
- All 13 gates from the initial Constitution Check still pass (no design choice violates).
- The 4 contract schemas are operational-only (no prose), reinforcing Principle VI.
- The data-model.md write paths preserve MW-1..MW-4 (every verified tap → transition row; every find → element row; never destructive on confidence; ≥3×/≥2 runs gate proposals).
- WF-3 frozen files remain untouched; new logic isolated to `intent_activity.py` and extended `observer_activity.py`.

**Verdict**: clean.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *(none)* | — | — |

No constitutional violations require justification. The "no hardcoding" mandate is structurally easier (less code), not harder.

## Out of scope (re-stated for the planner)

iOS / web / desktop drivers, compliance/a11y/localization audits, live-dealer (network-time-pressured) games, auto-promotion of any proposals, multi-account orchestration. Deferred per spec Assumptions.

## Phase 2 (NOT this command)

`/speckit.tasks` will produce `tasks.md` with dependency-ordered work items mapped to user stories US1–US10 and the phase plan in `scaling-to-game-plays-and-search.md` §11.
