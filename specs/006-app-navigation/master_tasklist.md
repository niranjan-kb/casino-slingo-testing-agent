# Master task list — spec 006 + immediate spec 007 runway

**Last updated**: 2026-05-20
**Owner**: Casino QA Agent (Danny Ocean) team
**Goal**: Land a full `play any blackjack` run end-to-end (parse → auth → navigate → play → report), and produce a real report on disk.

Legend: ✅ done · ⏳ pending · 🔴 blocked · 👤 operator · 🤖 coding agent · 🤝 either

---

## Phase 0 — Shipped (tracked for reference, not to do)

| ID | Item | Status |
|---|---|---|
| P0-01 | Spec 006 Phase A — DB-driven lobby (logical_screens.role, lobby_tile_patterns table) | ✅ |
| P0-02 | Spec 006 Phase A — intent_navigate_to_game rewrite (no short-circuit, ≥1-tap rule, search-pill clarification, target stickiness, search-bar selector quality, re-find pattern) | ✅ |
| P0-03 | Spec 006 Phase A — intent_navigate_to_screen tightening (anchor list, back-to-home recovery) | ✅ |
| P0-04 | Spec 006 Phase A — app_structure.md scaffold (operator walkthrough: Home, Cat Nav, Lobby widgets, sushi menu, bottom nav, modals, safety, deposit avoidance, jurisdiction guard) | ✅ |
| P0-05 | Spec 006 Phase A — anchor screens seeded (debug_menu='capability', quick_deposit_sheet='destructive', profile='account', fancash_spins_daily='daily_bonus') | ✅ |
| P0-06 | Spec 006 Phase A — get_logical_screen_role accessor + is_lobby_screen + lobby pattern queries | ✅ |
| P0-07 | Path A — `any_terminal` predicate fix in `is_intent_reachable` (unblocks intent_report transition) | ✅ |
| P0-08 | Path A — screen-driven intent-selection rule added to system prompt | ✅ |
| P0-09 | Path A — recovery_reentry tracking in reachability function | ✅ |
| P0-10 | Path A — `intent_navigate_to_game -> intent_authenticate` organic recovery validated live (Round 4) | ✅ |
| P0-11 | fancash_prompt over-eager signature deleted; agent no longer false-positives on home lobby | ✅ |

---

## Phase 1 — Cleanup (intent-registry simplification)

| ID | Item | Owner | Effort | Blocks |
|---|---|---|---|---|
| T-101 | Delete `intents/intent_play_bonus.md` | 🤖 | XS | T-102, T-103 |
| T-102 | Remove `play_bonus` node + `returns_to: play_game` from `graphs/casino_session.yaml` | 🤖 | XS | T-103 |
| T-103 | Drop `intent_play_bonus` from `plan_next_action.schema.json` enum | 🤖 | XS | T-104 |
| T-104 | Strip `intent_play_bonus` from 13 `tools/registry/*.yaml` files | 🤖 | XS | T-105 |
| T-105 | Strip play_bonus references from `goals/casino_session/__init__.py` + `game_kinds/slingo.md` + `game_kinds/live_show.md` | 🤖 | XS | T-106 |
| T-105b | **Rewrite `goals/casino_session/prompts/user.md`** — currently says "SEVEN intents" + "you cannot re-pick an intent that's already in completed_intents" (BOTH contradicted by Phase 1 removals + Path A recovery re-entry). Update to 6-intent journey + screen-driven recovery model. Rebuild API after. | 🤖 | S | rebuilds API |
| T-106 | Update tests/contract/test_plan_next_action_schema.py + any test that hard-counts 8 intents | 🤖 | XS | — |
| T-110 | Delete `intents/intent_load_game_context.md` | 🤖 | XS | T-111 (needs T-201 first) |
| T-111 | Remove `load_context` node from `graphs/casino_session.yaml`; rewrite `play_game.requires` to `navigate_to_game.success` | 🤖 | XS | — |
| T-112 | Drop `intent_load_game_context` from `plan_next_action.schema.json` enum | 🤖 | XS | — |
| T-113 | Strip `intent_load_game_context` from `tools/registry/*.yaml` files | 🤖 | XS | — |
| T-114 | Update `CLAUDE.md` and `all-prompts.md`: 8 → 6 intents, dedupe Cat Nav, refresh `app_structure.md` ref | 🤖 | XS | — |

**Phase 1 net effect**: closed-set enum 8 → 6 intents. 4 wasted LLM turns/session removed (the inert load_game_context window). Cleaner registry.

---

## Phase 2 — Foundational fixes (workflow-side wiring)

| ID | Item | Owner | Effort | Blocks |
|---|---|---|---|---|
| T-201 | **NEW `UpsertGameDirectory` activity** — writes a `game_directory` row from (loaded_signature, slug-hint-from-page-source, kind-from-SessionIntent). Idempotent. | 🤖 | S | T-110, T-202, T-203 |
| T-202 | **NEW `UpsertGamePlaybook` activity** — writes/updates a `game_playbook` row. Called once on first launch (empty row), then again from intent_play_game's first-launch bootstrap when fields are seeded. | 🤖 | S | T-203 |
| T-203 | **Wire post-navigate auto-seed in workflow**: after `intent_navigate_to_game` completes (success), workflow calls `UpsertGameDirectory` + `UpsertGamePlaybook` from observed page-source. Replaces the work that `intent_load_game_context` was supposed to do. | 🤖 | M | T-204, T-301 |
| T-204 | **Wire `game_context` into `generate_genai_prompt`** — workflow populates `{playbook, kind_name}` after the upserts in T-203 and passes it to every subsequent planner call. Activates the L4 layer that `_format_game_knowledge` already implements. | 🤖 | S | T-301 |
| T-205 | **ReadBalance retry-budget enforcement** — workflow counts ReadBalance-without-progress emissions and emits `terminal=balance_unparseable` after 3 in a row. Prevents the Round-4 "25× ReadBalance no-op" loop. | 🤖 | S | T-301 |

**Phase 2 net effect**: the data plumbing that spec 005 designed actually wires up. play_game's prompt has L4. Playbook fields become readable + writable.

---

## Phase 3 — Play-intent tightening

| ID | Item | Owner | Effort | Blocks |
|---|---|---|---|---|
| T-301 | **intent_play_game.md — first-launch bootstrap path** explicit: "If playbook.balance_signature is NULL (first launch), step 0: observe via `appium_get_page_source` → identify balance element → emit `UpsertGamePlaybook(balance_signature=..., balance_regex=...)`. THEN proceed to step 1 (ReadBalance)." | 🤖 | S | T-302, T-303 |
| T-302 | **intent_play_game.md — end_state_signatures + exit semantics** — currently allows `next=done` from any of `home, home_lobby, lobby_home`. Add explicit "if you're NOT on a lobby signature when terminal fires, BACK out first; don't emit done from a game screen". | 🤖 | XS | — |
| T-303 | **intent_play_game.md — playbook-absent escape hatch** — if `UpsertGamePlaybook` fails repeatedly or kind file is missing, SaveEvidence(label=playbook_seed_failed), emit done with terminal=playbook_uninitialized. | 🤖 | XS | — |
| T-310 | **intent_report.md — robustness against bad upstream state** — if play_game emitted done from a non-lobby screen, report writer should tolerate it (don't crash; flag in the report's `operator_action_queue`). | 🤖 | XS | — |
| T-320 | **intent_navigate_to_game.md — prefer SmartTap over raw appium_click for tile taps** — current intent uses raw `appium_click` which doesn't auto-record. SmartTap writes to `screen_transitions` (closes spec-006 success criterion #4). | 🤖 | XS | — |

---

## Phase 4 — Observer / lobby-walk gap (closes spec-006 success criterion #1)

| ID | Item | Owner | Effort | Notes |
|---|---|---|---|---|
| T-401 | **Diagnose why `compute_identity` returns "unknown" for lobby screens** when DetectScreen says `home` with 0.6+ confidence. Two functions, two thresholds. Either share matching code or relax observer threshold. | 🤖 | M | Blocks `game_directory` auto-discovery |
| T-402 | **Once T-401 lands, lobby-walk auto-discovery should fire on every home visit** and populate `game_directory` per-tile. Validate via Round-N regression. | 🤖 | XS | Depends on T-401 |

---

## Phase 5 — Operator inputs (blocks deeper per-screen knowledge)

These can't be done without operator screenshots / live walkthroughs. The agent CANNOT invent screen-specific content (per session memory).

| ID | Item | Owner | Effort | Notes |
|---|---|---|---|---|
| T-501 | **Profile screen walkthrough** — prompt + screenshot. Already partially documented; expand with component list + tap targets. | 👤 | S | High leverage |
| T-502 | **Settings screen walkthrough** — prompt + screenshot. | 👤 | S | |
| T-503 | **Category screen walkthrough** (the surface that appears after tapping a category pill — Slots, Table & Card, Live Dealer). What's the grid layout? Sticky filters? | 👤 | S | Unblocks sub-strategy 2 reliability |
| T-504 | **Search results screen walkthrough** — confirmed: pre-typing shows trending pills (casino1-5), post-typing shows real games. Document the result-tile layout + the "Cancel" exit. | 👤 | S | |
| T-505 | **Game-loaded surface walkthrough** for at least one kind (blackjack). What's stable? What's WebView? Where is balance visible? | 👤 | S | Unblocks play_game seed fields |
| T-506 | **Account screen walkthrough** (variants for transactions / KYC / verification). Read-only for the agent but reachable via top-right profile tap. | 👤 | S | |
| T-510 | **Page-source dump of home lobby + post-tap search surface** — needed to extract the actual casino search-bar resource-id (eliminates the text-contains xpath fallback). | 👤 | XS | One-shot deliverable |
| T-511 | **Confirm category-pill labels per build/state** (Slots / Table & Card / Live Dealer / All — but actual text on Fanatics test build). | 👤 | XS | |
| T-512 | **Confirm tile-rid pattern is still `casino_game_component_tile` + `small_game_component` etc.** on the current test build. Already seeded; just validate they match observed page-source. | 👤 | XS | |
| T-513 | **Page-source of the FanCash promotional modal** (the real one, not the home false-positive) so we can re-seed `fancash_prompt:<unique_text>` signature properly. | 👤 | XS | |
| T-514 | **Replace `home_lobby` "Hollywood Casino" signatures** with Fanatics-specific text (from a post-auth home page-source dump). | 👤 | XS | T-510 deliverable covers this |

---

## Phase 6 — Tech debt (no operator/runtime impact today; clean later)

| ID | Item | Owner | Effort | Notes |
|---|---|---|---|---|
| T-601 | **Deprecate + drop `game_catalog` table** (1 row legacy; superseded by game_directory + game_playbook). Migrate the `min_bet_usd / max_bet_usd` columns onto game_directory first. | 🤖 | S | |
| T-602 | **Rename `screen_elements.intent` → `purpose`** to remove name-collision with the new intent_* concept. | 🤖 | S | |
| T-603 | **Unify `logical_screens.is_hub` with `role`** — overlapping flags from spec 005 and spec 006. Pick one. | 🤖 | XS | |
| T-604 | **Drop `run_observations`** (1 row total, superseded by `observation_log`). | 🤖 | XS | |
| T-605 | **Investigate `transition_outcomes` empty despite 165+ observer fires** — autorecord wiring may be broken. | 🤖 | S | |
| T-606 | **Fix the 10 pre-existing test failures** in `test_agent_goal_workflow.py`, `test_mcp_integration.py`, `test_tool_activities.py` — Temporal harness wiring issues; not spec 006-related, but they pollute the regression signal. | 🤖 | M | |
| T-607 | **`all-prompts.md` updates** — add `app_structure.md` to L0; correct `init.py` → `__init__.py`; reword `fancash_spins.md` framing; reflect 6-intent count. | 🤖 | XS | After T-114 |
| T-608 | **`prompts/README.md` is stale** — doesn't list `app_structure.md`, doesn't note `soul_and_identity()` composes 3 files. | 🤖 | XS | |

---

## Phase 7 — Ship validation

| ID | Item | Owner | Effort | Notes |
|---|---|---|---|---|
| T-701 | **Round 5 regression run** with Phase 1+2+3 changes — `play any blackjack` should reach `intent_report` and write a markdown report. | 🤝 | S | After Phases 1–3 |
| T-702 | **Round 6 with Phase 4 (auto-discovery fix)** — `game_directory` should gain ≥1 row from the lobby walk. Closes spec-006 success criterion #1. | 🤝 | S | After Phase 4 |
| T-703 | **Update `CLAUDE.md` "Recent Changes"** to reflect spec 006 completion + Path A delivery. | 🤖 | XS | After T-701/T-702 |
| T-704 | **Close spec 006, open spec 007** — define what's next (per-game play deepening? cert-build promotion? sportsbook fork?). | 🤝 | M | |

---

## Critical path (shortest route to a successful play-blackjack-and-report run)

1. T-101 → T-106 (remove play_bonus, ~30 min)
2. T-201 → T-205 (foundational wiring, ~2-3 hr)
3. T-110 → T-114 (remove load_game_context, ~30 min, depends on T-201/T-203)
4. T-105b (rewrite user.md goal-overview block + rebuild API, ~30 min)
5. T-301 → T-302 → T-310 → T-320 (play-intent tightening, ~1 hr)
6. T-701 (round 5 test, ~30 min)

**Total**: ~half a day of focused work to get the full chain working end-to-end on blackjack.

Phase 4 (observer divergence) + Phase 5 (operator screens) + Phase 6 (tech debt) are all parallel-safe and can happen later.

---

## Open questions for the operator

These don't block the critical path but should be answered before spec 007 opens:

- **Per-screen walkthrough cadence**: bulk session (one sitting, all screens) or as-encountered (one screen per workflow run)?
- **Multi-state testing**: do we want geo-override via the debug menu (capability we've already declared) as a real intent in spec 007, or stays manual?
- **Bonus-round handling**: when slingo bonuses first appear, do we re-add `intent_play_bonus` or branch inside `intent_play_game`?
- **iOS rollout**: spec 006 is Android-only. Bottom-nav fixed-position rule has iOS noted (side, not center). Spec 007 scope?
- **Cert/prod readiness**: ASK-USER-OTP policy works in test (auto-fill). Cert/prod path needs operator interaction at the OTP step — is that in scope?
