# Feature Specification: Observer Framework

**Feature Branch**: `003-observer-framework`
**Created**: 2026-05-04
**Status**: Draft
**Input**: User description: "Observer framework for the Casino QA Agent — a low-cost side-channel that runs alongside any goal to detect, verify, and (optionally) react to cross-cutting product features (FanCash multipliers, FanCash Jackpots, FC→CC conversion, Quick Deposit, insufficient-funds modals, winning moments) and novel screens."

## Overview

The Casino QA Agent's persona is **player-first, QA-aware** — it must *notice, verify, and react* to product features the way a curious player would, not just complete macro flows (login, navigate, play, report). Today, every macro goal would have to embed feature-awareness logic ("did I see a 2x badge?", "is the jackpot icon on this screen?", "did the FanCash balance change?"), causing duplication and mixing concerns.

The Observer Framework decouples cross-cutting feature awareness from the goal pipeline. It is a **side-channel** that consumes data the goal already pulled from the device (page-source XML, screen signatures, tool-result metadata), runs declarative feature detectors against it, and emits structured observations into the session report — optionally driving a small sub-flow when a persona-gated reaction is warranted.

**Critical design principle: Observers are DATA, engines are CODE.** Five-to-six generic *observer engines* are written once in code; each new feature is added as a ~20-line YAML file plus an acceptance-criteria markdown. Adding a new feature observer must not require writing or modifying Python.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add a feature observer by writing only configuration (Priority: P1)

A casino QA engineer (or the agent itself, when bootstrapped from a Confluence spec) needs to add awareness of a new product feature — for example, the FanCash 2x earn-rate badge. They drop a YAML file declaring the trigger pattern, AC verification rules, optional sub-flow steps, and persona gating; alongside it they place an `acceptance.md` containing the feature's acceptance criteria (often pasted directly from the Confluence page). The framework auto-discovers the file at startup, instantiates the appropriate engine, and the observer is live on the next goal run — no Python files modified, no agent restart logic required beyond the standard worker reload.

**Why this priority**: This is the load-bearing capability. If adding an observer requires Python, the framework rots into per-feature code and fails its core purpose. Without this story, every other story collapses into hand-written code.

**Independent Test**: Drop a new `observers/<feature_id>/observer.yaml` + `acceptance.md` into the repo, restart the worker, run any goal that visits the relevant screen, and confirm the observer's results appear in the session report's observation ledger.

**Acceptance Scenarios**:

1. **Given** a YAML file declaring a `BadgeStateObserver` with a trigger pattern matching the FanCash header badge, **When** a goal run reaches a game screen displaying that badge, **Then** the session report contains a passed observation citing the observer's id and spec link.
2. **Given** a YAML file with an invalid engine name or malformed schema, **When** the framework loads observers at startup, **Then** the malformed observer is skipped with a clear warning logged, and other observers remain functional.
3. **Given** a goal run completes without ever encountering a screen the observer cares about, **When** the session report is written, **Then** the observer is recorded as "not triggered" rather than absent or as a failure.

---

### User Story 2 - Surface cross-cutting features in the session report during any goal run (Priority: P1)

A QA reviewer reads a session report after a `goal_login` or `goal_play_game` run to understand what the agent saw. The report must list every cross-cutting feature observation that fired during the run, with severity, summary, evidence path, and spec link, so the reviewer can confirm "yes, the 2x FanCash badge appeared on game launch and the toast text matched the spec" or "the jackpot icon was opted-out and the agent suggested opting in" — without re-running the session or replaying the Temporal history.

**Why this priority**: This is the visibility win that makes the framework useful from day one. Without observations in the report, the engineering effort produces nothing the QA team can consume.

**Independent Test**: Run any goal end-to-end (e.g., `goal_login`). Open the resulting `reports/YYYY-MM-DD-{run_id}.md` and verify it contains an "Observations" section with one row per observer that fired, including severity, summary, evidence link, and spec link.

**Acceptance Scenarios**:

1. **Given** a successful login run on a build with the FanCash multiplier feature active, **When** the report is generated, **Then** the report contains an observation entry for the multiplier with severity=info, summary mentioning the multiplier value, and a link to the feature spec.
2. **Given** a goal run encounters a screen never seen before in this run, **When** the report is generated, **Then** a `novel_screen` observation appears with the saved evidence path.
3. **Given** an observer's verify step crashes due to a bug in its rules, **When** the report is generated, **Then** the run still completed successfully and the observer's failure is recorded as a warn-severity entry, not a goal failure.

---

### User Story 3 - Catch acceptance-criteria regressions automatically (Priority: P1)

When the agent encounters a feature on-screen, the framework verifies the live UI against the feature's acceptance criteria text. If the UI fails to satisfy an AC rule (e.g., the multiplier badge is present but the launch toast is missing, or the conversion-success toast text doesn't match), the observer escalates the observation's severity to `bug`, attaches the spec link, saves evidence, and flags it prominently in the session report — turning the agent's play session into a continuous AC regression check.

**Why this priority**: This is the "QA-aware" half of the persona. Detection without verification is just logging; verification is what makes the agent earn its name as a tester.

**Independent Test**: Construct a synthetic page-source XML where an observer's trigger pattern matches but one of its AC verification rules fails. Run the observer activity against this input. Confirm the resulting observation has severity=bug, includes the spec link, and includes the failing rule's identity.

**Acceptance Scenarios**:

1. **Given** an observer whose AC requires a specific toast text, **When** a screen presents the trigger element but the expected toast is absent, **Then** the observation is recorded with severity=bug, the failing rule cited, evidence saved automatically, the bug surfaces in the top-of-report rollup, **and the goal run continues uninterrupted to its goal-defined terminal state**.
2. **Given** an observer whose AC rules all pass on the encountered screen, **When** the observation is logged, **Then** severity remains info and the report shows a green "AC passed" entry.
3. **Given** an observer encounters a screen where its trigger fires but no AC rule applies, **When** the observation is logged, **Then** pass_fail is recorded as `n/a` (not a silent pass).

---

### User Story 4 - Drive a sub-flow when persona settings allow (Priority: P2)

Some observations warrant the agent *acting* — e.g., the jackpot icon is opted-out and the QA persona has `jackpot_optin=true`, so the agent should tap the icon, opt in, close the modal, and resume the goal. The framework must support persona-gated sub-flows that emit a sequence of tool calls when triggered. Two routing modes are required: `auto_handle=true` runs the sub-flow immediately (cheap, no-decision reactions like saving evidence on a winning moment), and `auto_handle=false` surfaces the sub-flow as a *suggestion* to the next planner turn (the LLM decides whether to execute it).

**Why this priority**: Without this, the agent stays passive and the "curious player" promise is unmet. But it depends on detection (P1 stories) being solid first, hence P2.

**Independent Test**: With `persona_dials.jackpot_optin=true`, run the agent on a screen showing the jackpot icon in the opted-out variant. Confirm the suggested sub-flow appears in `pending_observations`; in a follow-up run with `auto_handle=true` set on a different observer (e.g., `winning_moment`), confirm the sub-flow tools execute before the next planner turn.

**Acceptance Scenarios**:

1. **Given** persona settings permit the jackpot opt-in sub-flow and the icon is in the opted-out state, **When** the observer fires, **Then** the next planner LLM call receives the sub-flow as a suggestion in its context.
2. **Given** persona settings forbid sub-flows (e.g., `curiosity=low`), **When** an observer would otherwise queue a probe sub-flow, **Then** the observer logs the observation but emits no sub-flow.
3. **Given** an observer with `auto_handle=true` (e.g., `winning_moment`), **When** the observation fires, **Then** its sub-flow tools execute before control returns to the planner.
4. **Given** an observer's sub-flow attempts a HIGH-RISK action (e.g., `place_bet`, `confirm_deposit`, `submit_otp`), **When** the framework dispatches the sub-flow, **Then** the action is rejected with a clear error (HIGH-RISK actions are reserved for the goal, not observers).

---

### User Story 5 - Filter past runs by which features they exercised (Priority: P2)

A QA lead or future GitHub bot needs to answer questions like "show me all runs in the last 7 days that exercised FEAT-5790 (jackpot)" or "find runs where any observer recorded a bug-severity finding". The framework must expose this metadata at the workflow level so it is queryable from the Temporal UI and from external tools without scraping reports or hitting the database directly.

**Why this priority**: This unlocks the GitHub-bot northstar (back-comments like "this PR's run verified FEAT-5790, passed 4/5 ACs") but is not required for v1 visibility.

**Independent Test**: Run several goals exercising different observers. Open the Temporal UI and filter the workflow list by `observer_hits` containing a specific observer id and by `severity_max=bug`. Confirm the filter returns the expected set of runs.

**Acceptance Scenarios**:

1. **Given** several completed goal runs, **When** filtering Temporal workflows by `observer_hits` containing `obs.jackpot_icon`, **Then** only runs that fired that observer appear.
2. **Given** a run that recorded at least one bug-severity observation, **When** filtering by `severity_max=bug`, **Then** that run appears in the filtered set.
3. **Given** a list of recently completed runs, **When** querying the workflow's `get_session_summary`, **Then** the response lists which feature spec ids were verified, with pass counts.

---

### User Story 6 - Re-verify time-sensitive UI without burning extra tool calls (Priority: P3)

Some features manifest as short-lived UI (toasts that fade in 3s, animations that play once on launch). The framework must support *delayed re-verification*: an observer fires at t=0, then a paired follow-up at t=+N seconds confirms expected disappearance or steady state — without the goal having to manually loop or poll.

**Why this priority**: Useful but not blocking — most v1 observers can be verified on the steady-state screen without timing-sensitive checks.

**Independent Test**: Configure an observer with `recheck_after_s=4`. Run it against a screen showing a toast. Confirm the observer fires at t=0 with the toast present, and emits a follow-up observation at ~t=4s confirming the toast is gone.

**Acceptance Scenarios**:

1. **Given** an observer with a delayed re-check, **When** it fires on a screen with a fading toast, **Then** a second observation lands ~N seconds later validating disappearance.
2. **Given** the goal run completes before the delayed re-check fires, **When** the run ends, **Then** the unfired re-check is recorded as cancelled, not as a failure.

---

### Edge Cases

- **Observer code crashes mid-tick**: framework MUST catch the exception, record a warn-severity observation describing the crash, and continue the goal run uninterrupted.
- **Multiple observers fire on the same screen**: all run; all log; sub-flow suggestions are presented to the planner together; auto-handle sub-flows execute in registration order.
- **Sub-flow leaves the agent on a different screen than where it started**: the framework MUST mark the screen as having changed so the planner re-orients on the next turn (no silent screen drift).
- **No observer matches a new screen**: the catch-all `NoveltyObserver` fires, saves evidence, and (per persona) optionally queues a probe sub-flow.
- **Persona dial change mid-session**: takes effect from the next observer tick; in-flight sub-flows continue with the values they were dispatched under.
- **Two observers' sub-flows conflict** (one wants to open a modal, one wants to dismiss the same modal): the framework records the conflict as a warn observation; only the first registered observer's sub-flow runs in `auto_handle` mode; suggestions are passed to the planner verbatim for `auto_handle=false`.
- **Malformed observer YAML**: skipped at load time with a clear warning; does not block other observers from loading.
- **Spec link unreachable** (Confluence down, page deleted): observation is still recorded with the configured spec_url; no run-blocking behavior.
- **Trigger too loose, observer fires on every screen**: framework MUST de-duplicate by observer_id within a configurable recent window (default: don't re-log identical observations within 30 seconds unless state changed).
- **Page-source unavailable for a tick** (e.g., dump failed): the observer pass is skipped for that tick with a debug-level entry; no severity escalation.

## Requirements *(mandatory)*

### Functional Requirements

#### Authoring & registration

- **FR-001**: System MUST discover and register all observers at startup by walking a known observers directory and loading each subdirectory's `observer.yaml` and `acceptance.md`.
- **FR-002**: System MUST support adding a new feature observer without modifying any Python source file. A new feature observer is created by adding a directory with two files: a YAML configuration and an acceptance-criteria markdown.
- **FR-003**: System MUST support at minimum the following observer engines: a Modal engine (overlays/drawers/sheets), a Toast engine (short-lived banners with text patterns), a BadgeState engine (persistent header/nav elements with variants), a BalanceDelta engine (numeric deltas across screens), a Novelty engine (first-seen screen signatures), and a ToolError engine (tool-result metadata anomalies). Together these MUST cover all six v1 observers without falling through to a custom-Python engine.
- **FR-004**: System MUST validate observer YAML at load time and skip malformed entries with a clear warning, without aborting startup.
- **FR-005**: System MUST allow each observer to declare a spec link (URL to Confluence/Jira) that is attached to every observation it emits.

#### Detection (the tick)

- **FR-006**: System MUST run all registered observers between every two device-affecting tool results during a goal run (not mid-tool, not on a wall-clock interval).
- **FR-007**: System MUST provide each observer tick a curated context bundle containing: parsed page-source XML, current screen signature, per-run novelty flag, last tool result metadata, parsed wallet/balance snapshot when available, persona dials, and recent observation history for de-duplication.
- **FR-008**: System MUST NOT pull additional device data (no extra screenshots, no extra page-source dumps, no extra tool calls) for the observer pass — observers piggyback on data the goal already pulled this turn.
- **FR-009**: System MUST de-duplicate observations within a recent window so that a loose trigger does not flood the report with identical entries.

#### Verification

- **FR-010**: System MUST evaluate each observer's AC rules against the current ScreenContext and record the outcome as `pass`, `fail`, or `n/a`.
- **FR-011**: When an AC rule fails, System MUST escalate the observation severity to `bug` (or `warn` if the observer declares a softer escalation), attach the spec link, and automatically save evidence (screenshot path + page-source snippet) for the run. The run MUST continue — an AC failure is a finding written to the report, never a halt of the goal loop (see FR-027).
- **FR-012**: System MUST allow observers to capture extracted values from the trigger (e.g., the `2x` multiplier value from a regex group) and include them in the observation summary.

#### Reaction (sub-flows)

- **FR-013**: System MUST support two sub-flow routing modes per observer: `auto_handle=true` executes the sub-flow's tool calls immediately, before the next planner turn; `auto_handle=false` surfaces the sub-flow as a suggestion in the next planner turn's context. Every executing sub-flow MUST be bounded by a hard time budget (default 30 seconds, observer-overridable). A sub-flow that exceeds the budget, raises an unhandled exception, or whose first tool call fails MUST be abandoned — recorded as a warn-severity observation in the report and NOT retried automatically. The goal loop continues regardless.
- **FR-014**: System MUST gate sub-flow execution on persona dials declared in the observer's YAML (e.g., `when: persona.jackpot_optin and state == 'opted_out'`).
- **FR-015**: System MUST reject any sub-flow tool call categorized as HIGH-RISK (e.g., `place_bet`, `confirm_deposit`, `submit_otp`, `tap_spin`). HIGH-RISK actions are reserved for the goal, not observers.
- **FR-016**: System MUST mark the screen state as "changed" after any sub-flow that executes screen-affecting tool calls, so the goal's planner re-orients on the next turn rather than assuming the prior screen.
- **FR-017**: System MUST NOT allow observers to mutate goal state directly (no goal switching, no run-end signals from observers, no `next='question'` user prompts).

#### Persistence & observability

- **FR-018**: System MUST persist every fired observation (regardless of pass/fail) to a durable observation log and include it in the goal's session-report ledger.
- **FR-019**: System MUST update the screen-map with newly-learned selectors discovered by observers (e.g., the resource-id of a newly-encountered modal button), using the same write-path as the goal's main flow.
- **FR-020**: System MUST expose workflow-level metadata for filtering past runs: which observers fired, the maximum severity reached, and which feature spec ids were verified.
- **FR-021**: System MUST expose live read-only access to the current run's pending observations, full observation log, and a session summary, for consumption by the React UI and external tooling.

#### Resilience

- **FR-022**: An exception raised anywhere in the observer pipeline MUST NOT abort the goal run. This explicitly includes: an observer's `trigger`, `verify`, or `sub_flow` logic; the spec-loader (missing markdown, malformed AC, unreachable spec source); the LLM verifier (non-JSON return, schema violation, inconclusive output); sub-flow tool dispatch; and any other observer-side code path. Every such failure is recorded with appropriate severity (`warn` for crashes/inconclusive, `info` for missing-spec) in the observation log and the run continues.
- **FR-023**: System MUST allow observers to schedule delayed re-verification (e.g., re-check the same trigger N seconds later) without requiring the goal to manually loop.
- **FR-024**: When a goal run ends before a scheduled delayed re-check fires, System MUST mark the unfired re-check as cancelled (not as a failure).

#### Persona configuration

- **FR-025**: System MUST load persona dials from a single configuration source per session and make them available to all observers via the ScreenContext.
- **FR-026**: Persona dials MUST include at minimum: a curiosity setting (gates novelty/probe sub-flows), a risk-appetite setting (informs stake guidance for goals), a jackpot opt-in flag, a max session loss bound, a react-to-wins flag, and an explore-unknown-icons flag.

#### Run-continuity invariant (umbrella)

- **FR-027**: **Observers MUST NEVER halt or pause the goal run.** No observer outcome — including AC verification failure, observer code crash, spec-loader error, LLM verifier inconclusive or malformed return, sub-flow execution failure, sub-flow timeout, sub-flow tool dispatch error, screen drift after a sub-flow, or any other observer-side path — MAY pause, halt, or block the goal loop, and observers MAY NOT emit `next='question'`, end the run, switch goals, or set any state that pauses the planner. The observer machinery has exactly two channels: (1) a *run-control* channel into which it writes nothing, and (2) a *report* channel into which every non-success outcome is recorded with appropriate severity, evidence, and spec link. "Silent" means silent-to-the-goal-loop; never silent-to-the-engineer reading the report.

#### Report surfacing

- **FR-028**: The session report MUST surface bug-severity and warn-severity observations prominently at the top of the report (rollup counts, then a per-finding list with spec link and evidence path) before the chronological event log. Bugs MUST NOT be buried in chronological order. Findings of severity `info` MAY appear only in the chronological log.

### Key Entities

- **Observer**: A declarative unit of feature awareness, defined by a YAML configuration and an acceptance-criteria text. Has an id, an engine type, a trigger pattern, optional state declarations, optional verification rules, optional sub-flow steps with persona gating, and a spec link.
- **ObserverEngine**: A code unit that interprets one class of observer YAMLs (Modal, Toast, BadgeState, BalanceDelta, Novelty, ToolError). Engines are written once; observers are data.
- **ScreenContext**: The curated input bundle handed to every observer per tick. Contains parsed page-source XML, screen signature, novelty flag, last tool result metadata, balance snapshot, persona dials, and recent observation history.
- **ObservationResult**: The structured output of one observer firing on one tick. Records observer_id, matched flag, severity (info/warn/bug), summary, evidence path, spec link, pass/fail/n/a, auto_handle flag, and any sub-flow tool calls suggested or executed.
- **ObservationLog**: The persisted history of all observations from one or more goal runs, queryable for trends and regression analysis.
- **PersonaDials**: The single configuration object per session that gates sub-flow execution and informs goal stake/risk choices.
- **AcceptanceCriteria**: Free-text markdown alongside each observer, often pasted from a Confluence FEAT page, used to verify observer behavior against the spec.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new feature observer can be added end-to-end (write YAML + acceptance text + run a smoke goal that exercises it) in under 30 minutes by an engineer with no prior framework knowledge, without modifying any Python source file.
- **SC-002**: For the six v1 observers (jackpot, fancash_multiplier, fc_to_cc_conversion, quick_deposit_drawer, insufficient_funds, winning_moment), 100% of the acceptance criteria stated in their corresponding feature specs can be encoded in YAML rules using one of the six engines, with zero observers requiring custom-Python escape hatches.
- **SC-003**: Every completed goal run produces a session report whose Observations section lists every observer that fired, with severity, summary, evidence link, and spec link — verifiable by reading the report alone, without re-running the session or replaying Temporal history.
- **SC-004**: 0 goal runs are aborted by observer code paths in a 30-day operating window. Observer crashes are recorded as warn observations and the run continues.
- **SC-005**: Adding the observer pass to a goal run increases per-screen overhead by less than 500 ms on average (no extra device round-trips; the additional work is XML parsing, regex matching, and DB writes that are bounded and cheap).
- **SC-006**: A QA reviewer can locate all past runs that exercised a specific feature spec (e.g., FEAT-5790 jackpot) in under 1 minute by filtering on workflow metadata, without scraping reports or hitting the database directly.
- **SC-007**: When a feature's acceptance criterion is violated by a build under test, the framework escalates the observation to bug-severity and saves evidence within the same goal run that detected it (no separate verification pass required).
- **SC-008**: The `goal_login` smoke run emits at least one observation per run (typically `novel_screen` for first-time signatures and possibly `tool_error` entries), confirming the observer pipeline is alive and integrated.
- **SC-009**: An end-to-end run of a play-game goal on a build with the FanCash multiplier feature active emits at least one `fancash_multiplier` observation and, on a winning spin, at least one `winning_moment` observation in the session report.
- **SC-010**: When a sub-flow attempts a HIGH-RISK action, it is rejected and recorded as a warn observation — never silently executed.
- **SC-011**: In a 30-day operating window, 0 goal runs are halted, paused, or aborted by any observer-side code path (AC failure, observer crash, spec-loader error, verifier malformed return, sub-flow timeout/error, screen drift) — every such outcome appears in the observation log with appropriate severity and the run continues to its goal-defined terminal state.
- **SC-012**: A QA reviewer opening a session report sees the run's bug-severity and warn-severity findings within the first screen of the report (rollup + finding list), without scrolling past the chronological event log, and each finding is one click away from its spec link and evidence file.

## Assumptions

- **Page-source-only inputs in v1.** Observers consume parsed page-source XML, screen signatures, tool-result metadata, and persona dials. They do *not* analyze screenshot pixels, ingest logcat, or proxy network calls. Logcat and timing inputs may be added later as additional ScreenContext fields without breaking the engine contracts.
- **Per-run novelty.** A "novel" screen is one not seen before *in this run*. Cross-run / cross-device novelty is out of scope for v1.
- **Page-source is already pulled by the goal's screen-detection step**, so the observer pass adds no extra device round-trips.
- **One persona per session.** The session loads a single `persona_dials` configuration at start; mid-session edits require a new run.
- **Atlassian MCP self-bootstrapping is out of scope** for v1 (the path is mentioned in the project north-star but is not built in this feature). v1 observer YAMLs are authored by hand.
- **Custom-Python observers are an escape hatch reserved but empty** in v1. If three or more candidate features would need a custom observer, that signals a missing engine pattern that should be promoted.
- **HIGH-RISK action set** matches the existing risk tier classification from the agent's persona doc (`place_bet`, `confirm_deposit`, `submit_otp`, `tap_spin`, `sign_in_button`, `deposit_confirm`, `otp_submit`). Observers may NEVER tap these regardless of persona settings.
- **Industry-standard report retention** (existing `reports/` directory convention) applies to observation logs; no new retention policy is introduced here.

## Out of Scope (v1)

- Vision pixel-diff over screenshots
- Logcat ingestion
- Network proxying
- Cross-run / cross-device novelty
- Atlassian MCP self-bootstrapping ("add observer for FEAT-XXXX" auto-authoring)
- GitHub bot integration ("/test this PR")
- Custom-Python observer engine implementations (escape hatch reserved, no observers ship in this category in v1)
