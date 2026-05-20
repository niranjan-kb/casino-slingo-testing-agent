# User stories — spec 006 + immediate spec 007 runway

**Last updated**: 2026-05-20
**Companion to**: [`master_tasklist.md`](master_tasklist.md) (the operational task list this groups)
**Purpose**: organize the outstanding work into discrete user-story buckets so progress can be tracked per story, not just per task.

Personas referenced:

- **Danny Ocean** — the runtime agent (a casino game player who happens to be an AI). Plays, navigates, reports.
- **Operator** — the human running the agent and supplying ground-truth knowledge (screenshots, walkthroughs, validation).
- **Developer** — anyone maintaining the agent code, prompts, schema, tests.

Stories are sized by the master tasklist's task IDs, NOT by re-estimating effort.

---

## US-01 — End-to-end blackjack run

> **As Danny Ocean, I want to play a hand of any blackjack game end-to-end (auth → navigate → play → report) without getting stuck mid-flow, so that I produce a real session report on disk every run.**

**Acceptance criteria:**
- A `play any blackjack` workflow reaches `intent_report` and a markdown report lands at `reports/<date>-<run_id>.md`.
- `game_directory` and `game_playbook` have at least one row each for the played game.
- `game_rounds` has ≥1 row.
- No infinite ReadBalance loop (terminal-by-retry-budget kicks in within 3 emissions).
- No `plan-graph guard blocked` warning during the happy path.

**Tasks in this story** (from master_tasklist):

| ID | Task | Status |
|---|---|---|
| T-201 | NEW `UpsertGameDirectory` activity | ⏳ |
| T-202 | NEW `UpsertGamePlaybook` activity | ⏳ |
| T-203 | Wire post-navigate auto-seed in workflow | ⏳ |
| T-204 | Wire `game_context` into `generate_genai_prompt` | ⏳ |
| T-205 | ReadBalance retry-budget enforcement | ⏳ |
| T-301 | intent_play_game first-launch bootstrap path | ⏳ |
| T-302 | intent_play_game end_state_signatures + exit semantics | ⏳ |
| T-303 | intent_play_game playbook-absent escape hatch | ⏳ |
| T-310 | intent_report robustness against bad upstream state | ⏳ |
| T-320 | intent_navigate_to_game — prefer SmartTap over raw appium_click for tile taps | ⏳ |
| T-701 | Round 5 regression run | ⏳ |

**Effort**: ~half a day (the critical path).

---

## US-02 — Organic recovery from unexpected app states

> **As Danny Ocean, I want to recover from unexpected screens (login mid-navigation, session timeout, deep-link bounce) by switching active_intent based on what I see — not by carrying per-intent recovery rules — so that my behavior matches what a real player would naturally do.**

**Acceptance criteria:**
- The LLM picks `active_intent` based on screen evidence each turn.
- The workflow allows re-entry to nodes that match the YAML's `recovery.<name>.intent` declarations (or whose preconditions are still satisfied).
- An organic transition like `intent_navigate_to_game -> intent_authenticate` is logged without a `guard blocked` warning.
- No per-intent recovery rule duplication across intent bodies.

**Tasks in this story** — almost entirely **shipped in Phase 0**:

| ID | Task | Status |
|---|---|---|
| P0-07 | `any_terminal` predicate fix in `is_intent_reachable` | ✅ |
| P0-08 | Screen-driven intent-selection rule in system prompt | ✅ |
| P0-09 | `recovery_reentry` tracking in reachability function | ✅ |
| P0-10 | Organic recovery validated live (Round 4) | ✅ |
| T-105b | Rewrite `goals/casino_session/prompts/user.md` — currently still says "you cannot re-pick an intent that's already in completed_intents" (contradicts Path A) | ⏳ |

**Effort**: ~30 min remaining (just the user.md rewrite + API rebuild).

---

## US-03 — Lean, accurate intent registry

> **As a Developer maintaining the agent, I want the intent registry to reflect only intents we actually use today (no stubs, no inert ceremonial passes), so that the LLM's choice surface stays small and the architecture stays understandable.**

**Acceptance criteria:**
- Closed-set `active_intent` enum has exactly 6 intents (parse_session, authenticate, navigate_to_screen, navigate_to_game, play_game, report).
- `intent_play_bonus.md` and `intent_load_game_context.md` are removed from disk.
- Plan graph, schemas, tool registries, and goal description are all consistent at 6 intents.
- Contract tests assert the new registry shape.
- Any future bonus-round handling routes through `intent_play_game` (inline branch) until/unless a real bonus surface requires its own intent.

**Tasks in this story:**

| ID | Task | Status |
|---|---|---|
| T-101 | Delete `intents/intent_play_bonus.md` | ⏳ |
| T-102 | Remove `play_bonus` node from `graphs/casino_session.yaml` | ⏳ |
| T-103 | Drop `intent_play_bonus` from schema enum | ⏳ |
| T-104 | Strip `intent_play_bonus` from `tools/registry/*.yaml` | ⏳ |
| T-105 | Strip play_bonus refs from `goals/casino_session/__init__.py` + game_kinds files | ⏳ |
| T-106 | Update contract tests for new intent count | ⏳ |
| T-110 | Delete `intents/intent_load_game_context.md` (after T-201) | ⏳ |
| T-111 | Remove `load_context` node; rewrite `play_game.requires` to `navigate_to_game.success` | ⏳ |
| T-112 | Drop `intent_load_game_context` from schema enum | ⏳ |
| T-113 | Strip `intent_load_game_context` from tool registries | ⏳ |
| T-114 | Update `CLAUDE.md` + `all-prompts.md` — 8 → 6 intents | ⏳ |

**Effort**: ~1 hour total (mostly mechanical cleanup).

---

## US-04 — Auto-discovered game catalog

> **As the Operator, I want the lobby walk to auto-discover games into `game_directory` on every home visit, so that subsequent `play <game>` runs don't depend on manual seeding and we accumulate a real catalog across sessions.**

**Acceptance criteria:**
- After a single workflow that crosses the lobby, `game_directory` has ≥1 row per visible tile.
- Tiles with generic rids (`casino_game_component_tile` etc.) yield display-name-derived slugs (no collisions).
- The observer's `compute_identity` agrees with the DetectScreen tool on lobby surfaces (both return `home` with ≥0.6 confidence).
- Closes spec-006 success criterion #1.

**Tasks in this story:**

| ID | Task | Status |
|---|---|---|
| P0-01 | DB-driven lobby (logical_screens.role, lobby_tile_patterns) | ✅ |
| P0-05 | Anchor screens seeded (lobby + destructive + account + daily_bonus) | ✅ |
| P0-06 | `get_logical_screen_role` accessor + `is_lobby_screen` + lobby pattern queries | ✅ |
| P0-11 | fancash_prompt over-eager signature deleted | ✅ |
| T-401 | Diagnose observer-vs-DetectScreen divergence | ⏳ |
| T-402 | Lobby-walk fires + populates `game_directory` | ⏳ |
| T-702 | Round 6 regression run | ⏳ |

**Effort**: ~half a day for the diagnostic + fix (Phase 4 is medium-effort).

---

## US-05 — Faithful app mental model

> **As the Operator, I want `app_structure.md` to reflect the actual app — every screen Danny might encounter, with its components, tap targets, and gotchas — so that the agent's prompt has the context to navigate efficiently without reverse-engineering page-source every turn.**

**Acceptance criteria:**
- Per-screen sections populated with operator-confirmed content (no agent-invented details).
- Cat Nav category pills, search-bar interaction model, sushi menu, bottom-nav, universal modals all documented.
- The `## Screens (filled in iteratively)` section has entries for: Home (done), Profile, Settings, Search results, Category screen, Game-loaded surface, Account screen.
- The DB has Fanatics-specific signatures (not "Hollywood Casino") for `home_lobby`.
- Real casino search-bar resource-id seeded; agent stops guessing.

**Tasks in this story:**

| ID | Task | Status |
|---|---|---|
| P0-04 | app_structure.md scaffold + Home walkthrough applied | ✅ |
| T-501 | Profile screen walkthrough | ⏳ 👤 |
| T-502 | Settings screen walkthrough | ⏳ 👤 |
| T-503 | Category screen walkthrough | ⏳ 👤 |
| T-504 | Search results screen walkthrough | ⏳ 👤 |
| T-505 | Game-loaded surface walkthrough (blackjack at minimum) | ⏳ 👤 |
| T-506 | Account screen walkthrough | ⏳ 👤 |
| T-510 | Page-source dump of home + search → extract real search-bar rid | ⏳ 👤 |
| T-511 | Confirm category-pill labels on Fanatics test build | ⏳ 👤 |
| T-512 | Confirm tile-rid patterns still match on current build | ⏳ 👤 |
| T-513 | Page-source of real FanCash modal (for proper signature seed) | ⏳ 👤 |
| T-514 | Replace home_lobby "Hollywood Casino" signatures with Fanatics text | ⏳ 👤 |

**Effort**: per operator-screenshot session (each screen ≈ 5–15 min of walkthrough; total ≈ 1–2 hr).

---

## US-06 — Clean, current documentation

> **As a Developer / new team member, I want documentation (`CLAUDE.md`, `all-prompts.md`, `prompts/README.md`, intent files) to accurately describe what's shipped — not stub statements or contradicting outdated claims — so that I can ramp onto the codebase without tripping on lies.**

**Acceptance criteria:**
- `CLAUDE.md` "Recent Changes" reflects Phase 1 cleanup + Path A + spec 006 completion.
- `all-prompts.md` lists `app_structure.md` in L0, lists the correct 6 intents, uses `__init__.py` not `init.py`, reframes `fancash_spins.md` as consumed-by-app_structure.
- `prompts/README.md` Layout block lists `app_structure.md`; Modules section notes `soul_and_identity()` composes 3 files.
- `goals/casino_session/prompts/user.md` "7-intent journey" rewritten as 6-intent + screen-driven recovery model.
- No intent body references tools, fields, or behaviors that don't exist.

**Tasks in this story:**

| ID | Task | Status |
|---|---|---|
| T-114 | `CLAUDE.md` + `all-prompts.md` 8 → 6 intents | ⏳ |
| T-105b | Rewrite `user.md` goal-overview block | ⏳ |
| T-607 | `all-prompts.md` polish (init.py → __init__.py, fancash framing, etc.) | ⏳ |
| T-608 | `prompts/README.md` refresh | ⏳ |
| T-703 | `CLAUDE.md` "Recent Changes" update post-validation | ⏳ |

**Effort**: ~1 hour total (documentation sweep).

---

## US-07 — Validated ship + handoff to spec 007

> **As the Operator, I want spec 006 closed with a passing validation run and a clean opening of spec 007, so that the team has a clear next-delivery decision (per-game play deepening? iOS? cert/prod? multi-state?) instead of drifting.**

**Acceptance criteria:**
- Round 5 (Phase 1+2+3) green: full chain to report.
- Round 6 (Phase 4) green: game_directory populates from lobby walk.
- `specs/006-app-navigation/results.md` written with run ids, success-criteria check, screenshots, and known gaps deferred to 007.
- Operator answers the open-questions block (see master_tasklist) so spec 007 has scope.

**Tasks in this story:**

| ID | Task | Status |
|---|---|---|
| T-701 | Round 5 regression run | ⏳ |
| T-702 | Round 6 regression run | ⏳ |
| T-703 | `CLAUDE.md` post-validation update | ⏳ |
| T-704 | Close spec 006, open spec 007 | ⏳ |
| — | Answer 5 operator open questions (cadence, geo-override intent, bonus handling, iOS, cert/prod) | ⏳ 👤 |

**Effort**: ~1–2 hours (validation + writing).

---

## US-08 — Tech-debt cleanup

> **As a Developer, I want legacy and contradictory artifacts pruned (dead tables, name-collisions, overlapping flags, stale signatures, flaky pre-existing tests), so that the codebase doesn't slow future work with confusion.**

**Acceptance criteria:**
- `game_catalog` dropped after columns migrated onto `game_directory`.
- `screen_elements.intent` renamed to `purpose` (no name-collision with intent_*).
- `logical_screens.is_hub` and `logical_screens.role` unified into one flag.
- `run_observations` dropped (superseded by `observation_log`).
- `transition_outcomes` populating again (autorecord wired or diagnosed if broken).
- The 10 pre-existing Temporal-harness test failures fixed (or marked xfail with clear reasoning).

**Tasks in this story:**

| ID | Task | Status |
|---|---|---|
| T-601 | Deprecate + drop `game_catalog` (after migrating min/max columns) | ⏳ |
| T-602 | Rename `screen_elements.intent` → `purpose` | ⏳ |
| T-603 | Unify `logical_screens.is_hub` with `role` | ⏳ |
| T-604 | Drop `run_observations` | ⏳ |
| T-605 | Investigate `transition_outcomes` empty despite observer fires | ⏳ |
| T-606 | Fix 10 pre-existing test failures | ⏳ |

**Effort**: ~1 day. Parallel-safe; can run any time after Phase 1+2.

---

## Story-by-status summary

| Story | Title | Done | Pending | Critical-path? |
|---|---|---|---|---|
| US-01 | End-to-end blackjack run | 0/11 | 11 | **yes** — half-day |
| US-02 | Organic recovery | 4/5 | 1 | one task left (user.md rewrite) |
| US-03 | Lean intent registry | 0/11 | 11 | **yes** — ~1 hour |
| US-04 | Auto-discovered catalog | 4/7 | 3 | parallel-safe |
| US-05 | Faithful app mental model | 1/12 | 11 👤 | operator-bound |
| US-06 | Clean documentation | 0/5 | 5 | follows Phase 1 |
| US-07 | Validated ship + 007 handoff | 0/5 | 5 | last |
| US-08 | Tech-debt cleanup | 0/6 | 6 | parallel-safe, low priority |

**Critical-path stories**: US-01, US-03, US-06, US-07 (in roughly that order).
**Parallel-safe**: US-02 (one task), US-04, US-05, US-08.

---

## Suggested sprint ordering

If working iteratively, one cohesive sprint at a time:

| Sprint | Stories advanced | Outcome |
|---|---|---|
| Sprint A — "Lean registry + plumbing" | US-03 (Phase 1 tasks) + US-01 (Phase 2 tasks) + US-02 (last task) | 6 intents, L4 wired, auto-seeded directory + playbook. Worker restart required mid-sprint. |
| Sprint B — "Play loop polish" | US-01 (Phase 3 tasks) + US-06 (documentation refresh) | intent_play_game tightened, docs current. |
| Sprint C — "Validate + ship" | US-01 / US-07 (Round 5) | First successful end-to-end blackjack run with report. |
| Sprint D — "Lobby auto-discovery" | US-04 (Phase 4) + US-07 (Round 6) | Spec-006 criterion #1 closed. |
| Sprint E — "Operator walkthroughs" | US-05 (in any order, 1 screen at a time) | App mental model converges to reality. |
| Sprint F — "Cleanup" | US-08 (any order) | Tech debt resolved. |
| Sprint G — "Open spec 007" | US-07 (T-704) | Define next delivery scope. |

Sprints A–C are the critical path. D, E, F, G are parallel-safe afterthoughts.
