# Feature Specification: Navigation Graph & Intent Layer

**Feature Branch**: `004-nav-graph-intents`
**Created**: 2026-05-05
**Status**: Draft
**Input**: User description: "Navigation graph and intent layer for the Casino QA Agent — replaces per-task hand-coded goal procedures with a self-evolving screen-transition graph and thin end-state intents that walk it."

## Overview

Today the Casino QA Agent is structured around per-task goals (`goal_login`, future `goal_play_slingo`, etc.), each defined as a markdown procedure that enumerates phases, selectors, fallback candidates, and wait times. This is appium-scripting in prose. It does not compose, does not generalize, and grows linearly with every new app capability.

This feature replaces that pattern with **two intertwined surfaces**:

1. **A self-evolving navigation graph** in the screen-map DB — `screen_transitions` (already added in feature 003's commit), `screen_elements`, `screen_signatures`, and `game_catalog` together describe "from screen A, doing X with element Y lands me on screen B." Every successful tap-and-verify writes back; every failure decrements. After ~3 verified runs of any flow, that flow is deterministic and ~zero LLM calls.

2. **A thin intent layer** that replaces markdown phase procedures. Each intent is ~400 tokens describing the desired end-state, the minimum success check, and intent-specific guardrails — never selectors, never fallbacks, never wait times. The agent walks the graph to reach the end-state, falling back to LLM reasoning only on novel screens.

The user's high-level prompt — for example *"play slingo till ±$100"* — decomposes into an intent sequence (authenticate → navigate to slingo → play with budget → report). The agent does not read a script for any of that; it queries the graph.

This builds on Feature 003 (Observer Framework). Observers continue to tick on every screen change as a side-channel. The intent layer is the *primary* decision surface; observers are the *peripheral vision*.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Login as graph traversal, not procedure (Priority: P1)

The QA engineer runs `goal_login` end-to-end. The agent walks the seeded `screen_transitions` graph from `app_launch → home`, executing each transition's verb (`tap`, `fill_and_continue`, `fill_and_login`, `fill_otp_and_submit`) deterministically, with no markdown phase procedure consulted. The end-to-end smoke (`smoke_login.py`) still emits `LOGIN PASS` within budget.

**Why this priority**: This is the proof of architecture. Until login walks the graph, every other story is theoretical. Once it does, every other intent inherits the same machinery for free.

**Independent Test**: Replace `goals/login/prompts/user.md`'s phase procedure with a thin `intent_authenticate.md` (~400 tokens, end-state declaration only). Run `uv run scripts/smoke_login.py --timeout 420`. Confirm `LOGIN PASS` and that the worker log shows `propose_next_step` calls instead of phase-by-phase markdown reasoning.

**Acceptance Scenarios**:

1. **Given** a freshly reset app and a seeded login graph, **When** the user issues `login`, **Then** the agent emits `LOGIN PASS` within 420 seconds AND the workflow's tool-call sequence corresponds 1:1 to the seeded transition path AND no observer-side path halts the goal loop (FR-027 from Feature 003 carries over).
2. **Given** a screen the graph predicts ends at `password` after `tap[continue]`, **When** the actual landing screen is the `home_lobby` (because email validation routed the user past password — a real branching case), **Then** the agent records the alternate edge `email → tap[continue] → home_lobby` with low confidence AND replans from the actual current screen rather than failing.
3. **Given** the loyalty modal does not appear after OTP (some test accounts skip it), **When** the path planner had selected the `otp → loyalty → home` path, **Then** the agent detects the actual `home` screen, records a same-step `otp → home` observation that strengthens the alternate edge, and continues without halting.

---

### User Story 2 - Tap-and-verify writes back to the graph (Priority: P1)

Every successful `SmartTap` (or composite tap-and-verify sequence) records the observed transition into `screen_transitions` via `record_transition_observation`. Failures decrement confidence on the assumed edge AND record the actual `to_screen` as a competing edge. The agent's first successful traversal of any new flow grows the graph; the third reproducible traversal graduates the flow to LOW-RISK confidence per existing graduation policy.

**Why this priority**: Without auto-recording, the graph is seed-only and rots into another hand-maintained map. With auto-recording, the agent's own play sessions are the data source.

**Independent Test**: Run `goal_login` against an app build with one new modal that's not in the seeded transitions. Verify a new `screen_transitions` row appears for that modal's edge after the run completes, and that running `goal_login` a second time uses the newly-recorded edge (no LLM reasoning for that step).

**Acceptance Scenarios**:

1. **Given** a verified `(from, verb, target, to)` transition that the agent has just executed, **When** `VerifyTap` confirms the expected `to_screen`, **Then** `record_transition_observation` is called with `success=True` AND the row's `times_used`, `times_succeeded`, and `confidence` increase.
2. **Given** an existing seeded transition `A → tap[X] → B` with confidence 0.95, **When** the agent executes `tap[X]` and lands on `C` instead of `B`, **Then** confidence on the `A → tap[X] → B` row decrements AND a new row `A → tap[X] → C` is upserted.
3. **Given** a previously-recorded transition with `times_used ≥ 3` and `confidence ≥ 0.8` (LOW-RISK graduation threshold), **When** the agent walks the same transition, **Then** the post-tap verification screenshot is skipped (graduation policy from existing screen-map docs).

---

### User Story 3 - High-level prompt decomposes into intent sequence (Priority: P1)

A QA engineer types `"play slingo till ±$100"` (or similar high-level prompt). The agent does not require a goal selector or a goal-per-game. It parses target and budget, then sequences intents automatically: authenticate → navigate to a screen whose signature matches the slingo loaded state → play with budget exit → write the report.

**Why this priority**: This is the user-facing payoff for the architectural pivot. Without it, the redesign delivers no end-user value; with it, every new game/feature gets cheap end-to-end testing.

**Independent Test**: Authenticate is already covered by Story 1. Add `intent_navigate_to_screen` and `intent_play_game` (with placeholder play loop). Send the prompt `"play slingo till you lose $1"` (tiny budget for smoke speed). Confirm the agent reaches the slingo loaded screen, places at least one bet, hits the exit condition, and emits a session report — without a goal-per-game markdown.

**Acceptance Scenarios**:

1. **Given** a session prompt that names a target game and a budget bound (in any natural-language shape), **When** the planner LLM is called for the first turn, **Then** it selects `intent_authenticate` from the closed-set intent registry; on subsequent turns it advances to `intent_navigate_to_screen`, `intent_play_game`, and `intent_report` as conditions warrant — without the workflow consulting any per-prompt-shape parser.
2. **Given** a prompt that names a game not in `game_catalog`, **When** the active intent becomes `intent_navigate_to_screen` and the catalog lookup misses, **Then** the agent uses the lobby search bar or category tabs to locate the game, records its row on first encounter, and proceeds — all driven by intent end-state declarations, no per-game markdown.
3. **Given** the agent reaches the budget bound during play, **When** the next planner turn fires, **Then** the LLM advances the active intent to `intent_report` AND the report includes start balance, end balance, P/L, and which exit condition fired.
4. **Given** a session prompt with a shape never seen before in tests (e.g., *"play whatever's most generous with FanCash today"*), **When** the planner runs, **Then** the agent reaches a terminal state (PASS, FAIL, or REPORT) by selecting from the registered intents — without a code change to handle the new shape.

---

### User Story 4 - Find a game by category or name via the catalog (Priority: P2)

The agent supports queries like *"play any slingo game"* or *"play Buffalo Slots"*. The `game_catalog` table stores `(name, slug, category, loaded_signature, min/max bet, observed play loop)` for every game the agent has seen. First encounter of any new game records a row; subsequent visits go via `find_games` lookup.

**Why this priority**: Required for the "find game" capability to be data-driven instead of hand-coded per game. Without it, every new game needs a `goal_play_<game>` markdown — exactly what we're killing.

**Independent Test**: Pre-seed the catalog with one slingo entry. Issue `"play slingo"`. Confirm the agent looks up the entry, walks the screen graph to its `loaded_signature`, and starts playing. Issue a second prompt naming a game NOT in the catalog. Confirm the agent searches/explores the lobby, records the new game's row, and starts playing.

**Acceptance Scenarios**:

1. **Given** `game_catalog` has at least one row with `category='slingo'`, **When** the user prompts `"play any slingo game"`, **Then** the agent picks one (highest confidence + most recently seen) and routes to its loaded signature.
2. **Given** `game_catalog` is empty, **When** the user prompts `"play slingo"`, **Then** the agent uses the lobby search bar (or category tabs) to locate a slingo title, records its `(name, slug, category, loaded_signature)` row on first encounter, and proceeds.
3. **Given** a previously-recorded game whose tile has moved in the lobby (e.g., featured-row reshuffle), **When** the agent attempts to launch it, **Then** the agent re-explores the lobby, updates the catalog with the new path/coords, and proceeds — no failure reported.

---

### User Story 5 - Unknown screen → human-confirmed signature proposal (Priority: P2)

When the same unknown screen signature (`unk:<hash>`) is seen ≥ 3 times across runs, the system proposes a new `screen_signatures` row by extracting the screen's stable elements (text + resource-ids). A human (or LLM-with-context, deferred) confirms the screen name, and the row is upserted. From then on, the screen is recognized by name and contributes to path planning.

**Why this priority**: Closes the loop from observer-detected unknowns to graph-resolved knowns. Without it, the screen-map stays brittle; with it, the agent's coverage grows organically.

**Independent Test**: Drive the agent past an unseeded modal three times. Verify a proposal artifact is generated (file or DB row in a `signature_proposals` table). Confirm the proposal, re-run, and verify the screen now matches by its real name.

**Acceptance Scenarios**:

1. **Given** the same `unk:<hash>` has been observed in `observation_log` ≥ 3 times across at least 2 runs, **When** the proposal job runs, **Then** a proposal artifact is produced containing the candidate screen-name (best-effort heuristic), the top text/resource-id signals from the unknown screen, and a confidence estimate.
2. **Given** an accepted proposal, **When** the operator runs the seeding step, **Then** the new signature is upserted into `screen_signatures` AND subsequent runs match the screen by its accepted name (no further `unk:` for that signature).
3. **Given** an unknown screen that appears only once across all runs, **When** the proposal job runs, **Then** the screen is NOT proposed (single-occurrence unknowns are recorded but not promoted to avoid noise).

---

### User Story 6 - Element auto-record from successful selectors (Priority: P2)

When `FindElementWithFallback` succeeds with a candidate, the system records `(current_screen, intent_target, strategy, selector, bounds)` into `screen_elements` (with the bounds-derived coordinate). The next time the same element is needed on the same screen+device, the lookup is instant and confident; the LLM does not propose selector candidates.

**Why this priority**: Element-level shortcuts compound the graph-level shortcuts. With this, individual taps stop costing LLM round-trips on known screens.

**Independent Test**: Run `goal_login` once on a fresh DB. After the run, query `screen_elements` for `screen='fanatics_one_email', element='email_field'`. Confirm a row exists with confidence ≥ 0.5 and the matched strategy/selector. Re-run; confirm the second run uses the cached coords without invoking `FindElementWithFallback`.

**Acceptance Scenarios**:

1. **Given** a `FindElementWithFallback` call returns `found: true` with a strategy and selector, **When** the call completes, **Then** `screen_elements` is upserted for the current screen with the matched strategy/selector and computed center-bounds coordinates.
2. **Given** a previously-recorded element with `times_used ≥ 3` and `confidence ≥ 0.8`, **When** the agent needs that element, **Then** `LookupCoords` returns it AND the agent calls `TapCoordinate` directly without going through `FindElementWithFallback`.
3. **Given** an element whose recorded coords lead to a tap that misses (the verify step fails), **When** the failure is recorded, **Then** the row's confidence drops AND the next attempt re-runs `FindElementWithFallback`.

---

### User Story 7 - Confidence decay handles app builds and stale paths (Priority: P3)

When the app build version changes (or after N days of no verification), confidence on rows in `screen_signatures`, `screen_elements`, and `screen_transitions` decays so stale or obsolete entries don't dominate the planner. The agent re-verifies decayed paths on first encounter and bumps confidence back up when they still work.

**Why this priority**: Without decay, a removed flow stays at 0.95 confidence forever and the planner keeps trying it. Real apps ship updates frequently; staleness is a real failure mode. P3 because the system is usable without it for the first 1–2 build cycles.

**Independent Test**: Run a goal end-to-end against build A; verify confidences. Switch the worker to a build B with one changed flow (e.g., the location modal removed). Run the goal again. Confirm the planner discovers the new path and the obsolete `location_modal → ...` row's confidence drops below the planner's floor on subsequent runs.

**Acceptance Scenarios**:

1. **Given** rows tagged with `last_verified` timestamps, **When** the worker runs against an app build whose `BUILD_ENV` or `APP_PACKAGE` differs from the row's recorded build, **Then** confidence is multiplied by a decay factor before path planning consults the row.
2. **Given** a row whose `last_verified` is older than the configured staleness window, **When** path planning runs, **Then** the row is treated as exploratory (lower confidence) until next verification.
3. **Given** a decayed row that the agent re-verifies in this run, **When** the verification succeeds, **Then** confidence and `last_verified` are restored without manual intervention.

---

### Edge Cases

- **Branching transitions**: same `(from, verb, target)` can lead to two different `to_screen`s depending on prior state (e.g., OTP either lands on `loyalty_bottom_sheet` or directly on `home`). The graph stores BOTH edges; the planner picks the higher-min-confidence path; the runtime detects which actually fires and reinforces it.
- **Loop in the graph**: e.g., agent ends up on a screen the planner already visited in this traversal. The path-finder excludes already-visited nodes within a single search; runtime cycles (back-button → modal → back-button → ...) trip an attempts-per-intent cap from existing self-healing rules.
- **Empty page-source dump** mid-transition (race condition with screen render): observer pass receives `unk:empty`, single-row de-dup; planner uses last known good screen.
- **`game_catalog` lookup matches multiple games** (e.g., several slingo titles): planner picks highest-confidence + most-recently-seen by default; an explicit name in the prompt narrows the match.
- **A seeded transition becomes invalid because the build removed a screen**: confidence decays per Story 7; planner re-explores, records a new path.
- **Auto-recorder cannot infer the `intent_target` semantic name** (the user-meaningful label like `email_field`): the row uses the matched strategy+selector as a fallback label until the next intent execution provides a label.
- **Path planner returns None** (no known path): agent falls back to LLM reasoning over the current page-source and intent end-state declaration; on success, the new path auto-records.
- **Two intents conflict on the next step**: not possible in v1 — only one intent is active at a time; the workflow's intent-selector guarantees mutual exclusion.

## Requirements *(mandatory)*

### Functional Requirements

#### Screen graph (write contract)

- **FR-001**: System MUST record a `(from_screen, intent_verb, intent_target, intent_args, to_screen)` row in `screen_transitions` for every successful tap-and-verify executed by the agent.
- **FR-002**: When a verified `to_screen` differs from the planner's expected `to_screen`, System MUST decrement confidence on the assumed edge AND upsert a new row reflecting the actual `to_screen`.
- **FR-003**: System MUST update `times_used`, `times_succeeded`, and recompute `confidence = succeeded / used` on every transition observation, regardless of seed vs. observed origin.
- **FR-004**: System MUST update `last_verified` to the current UTC timestamp on every successful observation.

#### Screen graph (read contract)

- **FR-005**: System MUST expose a path-finder query (`find_path(from, to)`) that returns a sequence of transitions with maximum minimum-edge confidence (most reliable route), or `None` if no path is known above a configurable confidence floor.
- **FR-006**: System MUST expose a single-step-ahead query (`propose_next_step(from, to)`) for one-action-at-a-time loops.
- **FR-007**: System MUST exclude transitions below the configured min-confidence floor from path planning, but MUST still expose them via raw queries for observability.

#### Game catalog

- **FR-008**: System MUST persist `(slug, name, category, provider, loaded_signature, min_bet_usd, max_bet_usd, play_loop)` for every distinct game the agent encounters, keyed on `slug`.
- **FR-009**: System MUST expose lookup queries by category, by name (substring), and by slug.
- **FR-010**: When a previously-unknown game is reached for the first time, System MUST upsert a catalog row with whatever fields can be inferred from the screen (name, category, signature) and leave others null.
- **FR-011**: When a previously-known game's lobby tile location has changed, System MUST update the catalog without requiring catalog deletion (idempotent re-recording).

#### Intent layer

- **FR-012**: System MUST replace `goals/login/prompts/user.md`'s markdown phase procedure with a thin intent declaration (`intent_authenticate`) ≤ 600 tokens that contains: (a) target end-state(s) as one or more screen names, (b) minimum success check, (c) intent-specific guardrails. It MUST NOT contain selectors, fallback candidate lists, or wait-time tables.
- **FR-013**: System MUST support at minimum the following intents in v1: `intent_authenticate`, `intent_navigate_to_screen(target)`, `intent_play_game(game, budget)`, `intent_report`.
- **FR-014**: At every planner turn, the system MUST select the active intent via the same LLM call that selects the next tool, given (a) the user's session-prompt text verbatim, (b) the current screen, (c) the set of intents already completed this session, and (d) the available-intent declarations. Intent selection MUST be a closed-set choice (the LLM picks from registered intent ids; it cannot invent new names) and MUST NOT involve a hand-coded prompt parser, regex shape match, hard-coded goal selector, or per-prompt-shape branching code path. The LLM may switch the active intent on any turn when current state warrants it (e.g., recover by re-entering an authentication intent if the session unexpectedly logs out).
- **FR-015**: A single user session-prompt expressed in natural language MUST drive an end-to-end session through whichever intents the prompt requires (typically authenticate → navigate → play → report) without further user prompts, except OTP under `ASK-USER-OTP` policy. The system MUST handle prompt shapes including but not limited to `"play <game> till ±$<budget>"`, `"log in and play any slingo game"`, `"play casino games for 10 minutes"`, `"keep playing whatever you find interesting"`. **New prompt shapes MUST NOT require code changes** — handling them is the LLM's job at planner-turn time, not the workflow's.
- **FR-016**: When the planner returns `None` for the active intent's end-state, System MUST hand off to LLM reasoning over the current page-source and intent declaration. Successful LLM-driven actions MUST auto-record into the graph per FR-001.

#### Auto-record contracts

- **FR-017**: `SmartTap` MUST call `record_transition_observation(success=True)` on verified transitions and `(success=False)` on verified divergences.
- **FR-018**: `VerifyTap` MUST emit the (from, intent_verb, intent_target, to) tuple to the workflow so the workflow can record it deterministically.
- **FR-019**: `FindElementWithFallback` MUST persist the matched `(strategy, selector, bounds)` into `screen_elements` keyed by current screen name and intent target label.
- **FR-020**: When an intent target label is not available (e.g., raw page-source exploration), System MUST use the matched strategy+selector as a placeholder label until a subsequent run with intent context provides a semantic name.

#### Unknown-screen proposal

- **FR-021**: When `obs.unknown_screen` records the same `unk:<hash>` ≥ 3 times across at least 2 runs, System MUST emit a signature-proposal artifact containing: candidate screen-name (heuristic), top-N text signals, top-N resource-id signals, and the run IDs that triggered it.
- **FR-022**: System MUST NOT auto-promote a proposal into `screen_signatures` without an explicit accept step (human or LLM-with-context). Proposals are advisory.
- **FR-023**: System MUST NOT propose signatures for unknown screens with fewer than 3 occurrences across runs.

#### Confidence decay

- **FR-024**: When the worker runs against an app build whose `BUILD_ENV` or `APP_PACKAGE` differs from a recorded row's build, System MUST apply a decay factor to that row's confidence before consulting it for path planning.
- **FR-025**: Rows with `last_verified` older than a configurable staleness window MUST be treated as exploratory (their effective confidence reduced) until they are verified again.
- **FR-026**: Decay MUST be applied at read time only — actual stored confidence values are not destructively modified by decay; the next successful verification restores effective confidence to `times_succeeded / times_used`.

#### Run continuity (carries from Feature 003)

- **FR-027**: The intent layer's planner failures, auto-recorder write failures, and graph-query failures MUST NOT halt the goal loop. The workflow continues — falling back to LLM reasoning for unknowns, swallowing recorder failures with a warn observation per Feature 003's run-continuity invariant.

### Key Entities

- **Transition**: A directed edge `(from_screen, intent_verb, intent_target, intent_args, to_screen)` with confidence and `last_verified`. Unique per `(from, verb, target, to, app_context)` so branching paths are first-class.
- **Game catalog entry**: A row with stable `slug`, human `name`, `category`, optional `provider`, `loaded_signature` for navigation, `min_bet_usd`/`max_bet_usd`, and an opaque `play_loop` blob for game-specific play strategy.
- **Intent**: A declarative unit defining a desired end-state set, a minimum success check, and intent-specific guardrails. Intents are runtime-selectable; one is active at a time.
- **Path**: An ordered sequence of transitions returned by the path planner, scored by minimum-edge confidence. `None` when no known path exists.
- **Signature proposal**: An advisory artifact emitted when an unknown screen recurs across runs, containing candidate signature signals for human/LLM acceptance.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After this feature ships, `goal_login`'s `prompts/user.md` markdown phase procedure is replaced by an intent declaration of ≤ 600 tokens, and the smoke test (`smoke_login.py`) still emits `LOGIN PASS` within 420 seconds with the same end-to-end behavior.
- **SC-002**: After 3 verified runs of any seeded flow on a stable build, ≥ 80% of the flow's transitions are walked deterministically (cached coords + path-planner shortcuts) without invoking the LLM for selector reasoning.
- **SC-003**: A single user prompt of the form `"play <game> till ±$<budget>"` drives an end-to-end session (authenticate → navigate → play → report) without additional user prompts (except OTP under `ASK-USER-OTP` policy).
- **SC-004**: Adding a new game to the catalog requires zero new markdown files. The agent records a new game-catalog row on its first successful encounter; subsequent runs use the recorded row for navigation.
- **SC-005**: 100% of the seeded login-flow transitions auto-record observations on every run; their `times_used` count increases monotonically run-over-run; their confidence approaches 1.0 after 3 successful runs.
- **SC-006**: When the path planner returns `None` for an intent's end-state, the agent reaches the end-state via LLM reasoning ≥ 80% of the time AND records the discovered path so the next run uses it deterministically.
- **SC-007**: Unknown-screen proposals fire only after ≥ 3 occurrences across ≥ 2 runs, and never on single-occurrence unknowns. Signal-to-noise on the proposal feed is ≥ 95% (≤ 5% of proposals are deemed not worth seeding by the reviewer).
- **SC-008**: After an app build change, ≥ 80% of broken transitions are detected and re-explored within the first run on the new build, and the graph contains the new paths after the run completes.
- **SC-009**: 0 goal runs are halted by the navigation-graph or intent-layer code paths in a 30-day operating window. All planner/recorder failures fall back gracefully and the goal continues.
- **SC-010**: Per-screen overhead added by the graph and intent layer is < 200 ms on screens with cached transitions and < 1 second on novel screens (LLM reasoning path).
- **SC-011**: A session prompt with a shape never previously seen in any spec, test, or training example (e.g., *"play whatever's most generous with FanCash today"*) MUST drive a coherent intent sequence and reach a terminal state (PASS, FAIL, or REPORT) without code changes — verified by issuing a novel prompt and confirming the agent does not crash, does not loop, and does not emit `next='question'` for routine recovery.
- **SC-012**: 0 of the registered intent declarations contain selectors, fallback candidate lists, wait-time tables, or per-prompt-shape branching. Intent files are end-state declarations only, ≤ 600 tokens each.

## Assumptions

- **Page-source-only inputs in v1.** No vision pixel-diff, no logcat, no network proxying. Element identity comes from page-source XML; same constraint as Feature 003.
- **Intent files are markdown.** Same loading mechanism as the current goal prompts; the intent file becomes a section of the assembled description.
- **No multi-device runs.** The graph is keyed per `app_context` (and per `device_profile_id` for elements). Cross-device coord normalization is out of scope.
- **No multi-build runs concurrently.** Only one `BUILD_ENV` is active per worker. Confidence decay applies only to switches of `BUILD_ENV` or `APP_PACKAGE` between runs.
- **Risk-tier policy is unchanged.** `should_verify_tap` (HIGH-RISK never graduates) continues to apply; the graph respects it by keeping verification on for HIGH-RISK rows regardless of confidence.
- **Observer Framework (003) ships first.** This feature builds on the observer pipeline, the persona dials, and the observation_log table. `obs.unknown_screen` is the producer for FR-021's proposal flow.
- **Seed scripts are still in use** for the initial bootstrap. Auto-record covers growth; seeds cover cold-start. Both write to the same tables idempotently.
- **One persona per session.** Same as 003 — runtime persona dials are loaded once at worker start.
- **AC documents (markdown) for cross-cutting features** are out of scope here; they belong to 003's spec-attached observer path (deferred there too).
- **Game play strategy is per-game data, not per-game code.** `game_catalog.play_loop_json` carries the strategy; the play intent reads it generically. Hand-written `goal_play_<game>` files are not reintroduced.

## Out of Scope (v1)

- Vision pixel-diff over screenshots
- Logcat ingestion / network proxying
- Atlassian MCP self-bootstrapping (auto-fetch FEAT-XXXX → propose intent or signature)
- GitHub bot integration ("/test this PR")
- Cross-device / cross-emulator graph sharing beyond the existing per-device-profile element coords
- Multi-build graph diffing or A/B path comparison
- Voice / spoken-prompt input (text natural-language is in scope; audio is not)
- Fully automatic acceptance of signature proposals (v1 keeps a human/LLM-with-context confirm step)
- Persisted multi-session memory beyond the screen-map DB (no separate "agent memory" store)
