# Feature Specification: Casino Game-Play & Verification Suite

**Feature Branch**: `005-casino-game-play-suite`
**Created**: 2026-05-06
**Status**: Draft
**Input**: User description: "Extend the agent from the auth-only POC to playing real casino games end-to-end (Spin to Win, Blackjack, Fire Roulette, Multihand Blackjack, Slingo, slots) and verifying its own self-improving infrastructure (loop, screengraph, proposals dashboard, workflow optimizations)."

> **Background docs (in this spec folder)**: [setup-before-scalling-to-game-plays-search.md](./setup-before-scalling-to-game-plays-search.md), [scaling-to-game-plays-and-search.md](./scaling-to-game-plays-and-search.md), [self-improving-loop.md](./self-improving-loop.md), [complete-screengraph.md](./complete-screengraph.md), [gaps-and-guardrails.md](./gaps-and-guardrails.md), [manual-intervention-and-maintenance.md](./manual-intervention-and-maintenance.md). Treat them as ratified context for this spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Play "Spin to Win" from a vague prompt (Priority: P1)

An operator says `play fanatics spin to win`. The agent parses the prompt into a structured session intent (game, default budget bounds, terminal condition), authenticates, navigates to the game using the lobby's recents → category → search → scroll fallback chain, loads game-specific context automatically, plays a bounded number of rounds within the operator's loss ceiling, and produces a session report.

**Why this priority**: This is the smallest end-to-end slice that proves the whole pipeline (parse → auth → navigate → contextualize → play → report). Spin-to-Win is structurally a slot game without bonus rounds, so it stresses the pipeline without complicating it. Without P1, none of the other stories can be demonstrated.

**Independent Test**: Run a single workflow with the prompt and the operator's loss ceiling configured. Observe a completed session report listing rounds played, balance delta, and any new screens proposed. The pipeline is validated even if no other game ever ships.

**Acceptance Scenarios**:

1. **Given** a fresh session with the operator's loss ceiling configured and the test account funded, **When** the operator submits `play fanatics spin to win`, **Then** the agent authenticates, reaches the loaded game screen, plays at least one round, and produces a session report.
2. **Given** the same prompt with no explicit terminal condition, **When** the agent runs, **Then** play stops at the first of: max-spins reached, max-minutes reached, or loss ceiling reached, and the report names which terminal fired.
3. **Given** the prompt explicitly says `for 5 spins`, **When** the agent runs, **Then** play stops at 5 spins regardless of remaining budget; the prompt-supplied bound is honoured because it is stricter than the defaults.
4. **Given** the prompt asks for a higher loss ceiling than the operator-configured environment ceiling, **When** the agent parses the request, **Then** the request is silently capped to the environment ceiling and the report records both the requested and effective ceiling.
5. **Given** the game tile is not in recents or the relevant category, **When** the agent navigates, **Then** it falls through to the search-bar branch, types the query, and opens the first matching result.

---

### User Story 2 - Play "Fanatics Blackjack" (Priority: P1)

An operator says `play fanatics blackjack`. The agent runs the same pipeline as Story 1 but the game is a single-hand table game with hit / stand / double / split decisions and dealer-state polling between actions.

**Why this priority**: Validates that the per-kind context layer (table-game KB) is reusable across games and that turn structure (player-action → dealer-state → next-prompt) decomposes into ordinary screen-graph paths rather than bespoke per-game code. P1 because it proves the kind-abstraction works on a real production game.

**Independent Test**: Run the workflow against a Fanatics Blackjack table; observe at least one full hand played with a sensible decision sequence (any non-pathological strategy is acceptable for this story); the report shows the hand outcome (win/lose/push) and balance delta.

**Acceptance Scenarios**:

1. **Given** the agent reaches the loaded blackjack table, **When** the dealer requests an action (hit/stand), **Then** the agent decides within a sensible turn budget and the table reflects the chosen action.
2. **Given** a hand that supports double or split, **When** the agent's decision logic indicates one of those actions, **Then** the corresponding control is exercised and the game progresses without operator help.
3. **Given** the agent observes the same dealer-state signature twice in a row, **When** it falls back to a re-poll instead of re-tapping, **Then** no double-action is sent to the table.

---

### User Story 3 - Play "Fanatics Fire Roulette" (Priority: P2)

An operator says `play fanatics fire roulette`. The agent navigates to the roulette table, places at least one bet inside the time-bounded betting window, waits for the wheel result, and records the outcome.

**Why this priority**: Validates time-pressured betting (the betting window closes regardless of agent state) and number-grid interactions (chips on grid cells). P2 because it stresses a class of games (time-pressured live or pseudo-live) that table-game and slot abstractions don't cover.

**Independent Test**: Single workflow placing at least one bet per spin for N spins; the report shows bet placement timestamps relative to window close, and any missed-window events are flagged.

**Acceptance Scenarios**:

1. **Given** the betting window is open with at least 5 seconds remaining, **When** the agent decides to bet, **Then** the bet is placed before the window closes.
2. **Given** the betting window has less than 2 seconds remaining and no bet has been placed, **When** the agent considers placing one, **Then** it skips the round rather than rushing and missing a confirmation.
3. **Given** a wheel result, **When** it is announced, **Then** the agent records win/loss/bet amount in the round log before the next betting window opens.

---

### User Story 4 - Play "Fanatics Multihand Blackjack" (Priority: P2)

An operator says `play fanatics multihand blackjack`. The same pipeline as Story 2 but the game presents multiple simultaneous hands; the agent must decide on each hand in sequence within the same turn cycle.

**Why this priority**: Validates the play-loop's ability to handle parallel decision streams (multiple hands per round) without forking the workflow. P2 because it is a delta on Story 2; if Story 2 is solid, Story 4 is mostly a context-and-loop change.

**Independent Test**: Workflow plays at least one full multi-hand round (3+ hands), making distinct decisions per hand; report shows per-hand outcomes and aggregate balance delta.

**Acceptance Scenarios**:

1. **Given** a 3-hand round, **When** the agent acts, **Then** it makes a separate decision for each hand and the table records all three before the dealer plays.
2. **Given** one hand busts mid-round, **When** the agent moves to the next hand, **Then** the busted hand is not retried and the next hand's decision is independent.

---

### User Story 5 - Play a Slingo game (Priority: P1)

An operator says `play slingo` (or names a specific Slingo game). The agent plays Slingo Classic (or the named title) through at least one full base round, recognises the bonus-trigger signature when it appears, and switches to a bonus sub-routine until base play resumes.

**Why this priority**: Validates the Slingo kind (5×5 grid, draw-mark-evaluate-ladder turn structure) and the bonus sub-intent. Slingo is the product line this agent was originally seeded around, so Slingo coverage is the canonical case. P1.

**Independent Test**: Single workflow plays N base rounds; if a bonus triggers within budget, the agent enters bonus mode and exits cleanly back to base; if no bonus triggers, base-only completion is acceptable for this story.

**Acceptance Scenarios**:

1. **Given** the agent reaches the loaded Slingo Classic game, **When** it spins, **Then** it observes the draw, recognises matched-vs-unmatched marks on the grid, and waits for the round-end signature before next spin.
2. **Given** a bonus-trigger signature is observed mid-round, **When** the agent acts, **Then** it switches to bonus mode with no further wagers and exits cleanly when base-grid signature returns.
3. **Given** the agent enters a bonus mini-game it has never seen before, **When** budget allows, **Then** it explores the bonus with frozen wagering and a capped action count, recording new screens for operator review afterwards.

---

### User Story 6 - Play a slot game (Priority: P2)

An operator says `play slots` or names a specific slot. The agent plays a production slot through at least one round, exercising spin, max-bet, and (optionally) paytable info.

**Why this priority**: Validates the slots kind. P2 because Spin-to-Win (P1) is structurally adjacent; this story confirms the abstraction generalises to a third slot title.

**Independent Test**: Workflow plays N rounds on a chosen slot title; report shows balance delta and any new screens proposed.

**Acceptance Scenarios**:

1. **Given** the loaded slot screen, **When** the agent spins, **Then** the round-end signature is reached within the configured timeout.
2. **Given** a production slot's autospin or max-bet feature is unavailable in the agent's known transitions, **When** the agent encounters it, **Then** the encounter produces a signature proposal rather than a halt.

---

### User Story 7 - Verify the self-improving loop end-to-end (Priority: P1)

An operator runs the same goal twice on a stable build, with operator review of new signature proposals between the two runs. The second run completes with materially fewer planner LLM turns than the first, because previously novel screens are now in the screen graph and resolved deterministically.

**Why this priority**: This is the cost story. The whole architecture's economic claim rests on per-action map-first lookup eliminating LLM cost on stable flows. P1 because if this doesn't hold, the rest of the system is unaffordable at scale.

**Independent Test**: Run goal X on build B → review and accept proposals → run goal X on build B again. Compare planner LLM turn counts and per-turn input-token p50.

**Acceptance Scenarios**:

1. **Given** a first run that produces N signature proposals, **When** the operator reviews and accepts the real screens, **Then** the second run on the same build resolves those screens via the screen graph (no proposal regenerated).
2. **Given** the second run on a stable build, **When** compared to the first, **Then** total planner LLM turns drop by a measurable margin (target: ≥40% reduction across the equivalent flow segment).
3. **Given** an operator who has not yet reviewed the proposals, **When** the second run starts, **Then** it still completes; it just doesn't see the cost reduction.

---

### User Story 8 - Verify screen-graph completeness via exploration (Priority: P2)

An operator runs an exploration-mode session against the cert build with a fixed budget (max screens / max actions / max wall-clock minutes). The agent traverses screens it has not previously visited, lands new candidates in the proposals queue, and a graph-rendering tool produces a viewable map of the discovered topology. A graph-diff tool against a baseline highlights what's new vs. removed.

**Why this priority**: Coverage is the property that turns the agent from a goal-runner into an app surveyor. P2 because the play-flow stories (P1) deliver value without exploration; exploration multiplies that value but is not itself the MVP.

**Independent Test**: Run an exploration session with budget; observe new proposals, render the resulting graph, run a diff against the previous main-branch graph snapshot, and present a delta summary.

**Acceptance Scenarios**:

1. **Given** an exploration budget of N screens, **When** the agent runs, **Then** it visits at least M previously-unseen screens (M ≤ N), where the value of M is meaningful for the build under test.
2. **Given** the run completes, **When** the rendering tool is invoked, **Then** an HTML graph is produced that a human can navigate (click node → screenshot evidence; click edge → list of runs that observed it).
3. **Given** a baseline graph from a prior build, **When** the diff tool runs, **Then** added nodes, removed nodes, and changed edges are listed in a markdown summary suitable for a PR comment.
4. **Given** a destructive edge (deposit, withdrawal, KYC submit, account close), **When** the agent encounters it during exploration, **Then** the edge is not traversed; it is recorded but blacklisted from autonomous use.

---

### User Story 9 - Verify the signature-proposals dashboard and approval workflow (Priority: P1)

An operator opens a dashboard listing pending signature proposals, grouped to deduplicate near-duplicates (rotating banners, A/B variants). For each cluster the operator can view evidence (screenshot + page-source path), name the canonical screen, accept it (which makes it influence subsequent runs' map-first lookups), or reject it as noise. The operator's queue length and weekly throughput are visible so saturation is detectable.

**Why this priority**: The operator gate is the human checkpoint that keeps the database trustworthy (FR-022 — auto-promotion forbidden). Without a usable dashboard, the gate breaks down and the inner loops poison themselves. P1.

**Independent Test**: Generate proposals from a real run; open the dashboard; cluster them; accept some and reject some; run the same flow again and observe that accepted proposals now resolve deterministically while rejected ones don't reappear as new proposals (i.e., they're dedup'd or hidden).

**Acceptance Scenarios**:

1. **Given** a run that produced ≥5 near-duplicate proposals (e.g., banner rotation), **When** the operator opens the dashboard, **Then** they see at most a small number of clusters rather than a flat list of every hash.
2. **Given** a cluster, **When** the operator accepts the canonical with a logical name, **Then** all hashes in the cluster are bound to that logical screen and subsequent runs resolve them as known.
3. **Given** the operator's pending queue exceeds the configured weekly cap, **When** the next exploration cycle would normally run, **Then** exploration self-throttles (lower exploration ratio or skipped entirely) and an alert is surfaced.
4. **Given** an accepted proposal, **When** a subsequent run encounters the same screen, **Then** the screen graph resolves it without producing a new proposal.

---

### User Story 10 - Verify workflow runs and that all optimizations are in place (Priority: P1)

An operator inspects a recent workflow run and a per-run cost dashboard. They confirm that: per-turn input-token volume is within budget at p50/p95; the prompt-cache hit rate on the static prelude is high; raw page-source content does not appear in the planner's input prompts; tool results are stored at differentiated retention levels (ephemeral vs. durable summary vs. failure-payload vs. evidence-only); and conversation history older than the most recent few turns appears as one-line summaries rather than verbatim payloads.

**Why this priority**: This is the regression gate. If any optimization silently breaks (XML re-leaks, cache busts, history compactor disabled), per-turn cost balloons and the system becomes unaffordable invisibly. P1 because regressions here are silent and expensive.

**Independent Test**: Open a recent run's dashboard and step through the planner-prompt content for representative turns; check the published metrics against thresholds. The check is a "does this run look healthy" gate that can run on every PR.

**Acceptance Scenarios**:

1. **Given** a representative run on a stable build, **When** the per-turn input-token metric is read, **Then** the p50 is below the configured ceiling for that goal (target: ≤ 30K characters per turn) and p95 is below 1.5× p50.
2. **Given** the same run, **When** prompt-cache hit rate is read, **Then** the hit rate on the static prelude is ≥ 85% across cacheable turns.
3. **Given** the same run, **When** any planner-prompt is inspected, **Then** raw page-source XML is not present (only structured summaries or paths).
4. **Given** the same run, **When** a turn's conversation history is inspected, **Then** at most a small number of recent tool results appear verbatim and older results appear as one-line summaries.
5. **Given** any of (1)–(4) fails, **When** the dashboard is opened, **Then** the failure is highlighted with the offending turn for click-through.

---

### Edge Cases

- **Operator-supplied prompt asks for unbounded play** (`play forever`, `play until I stop`): the agent enforces the env ceiling and the default time/spin bounds; it cannot be talked into ignoring them.
- **Account balance is below the bet minimum** before any round: the agent reports "insufficient balance" and terminates without halting on a perceived selector failure.
- **Mid-run modal interrupts gameplay** (responsible-gaming reminder, session-renewal, network-glitch toast): the agent dismisses recognised modals via the screen graph; novel modals trigger a proposal and a single LLM resolution.
- **Game enters maintenance mid-session**: the agent recognises the maintenance signature, saves evidence, and terminates the session cleanly with a `maintenance_observed` reason in the report.
- **Page-source read fails repeatedly** (Appium hung): the agent retries with backoff up to a small cap, then saves evidence and terminates rather than silently looping.
- **Operator promotes a wrong proposal**: the next run that fails on the wrongly-promoted screen auto-demotes the row's confidence (it does not delete it); the row is flagged for re-review in the daily triage.
- **Proposal queue saturated** (over weekly cap): exploration auto-throttles; goal runs continue normally but write fewer new proposals; an alert is raised.
- **Build version changes between runs**: previously learned per-game animation timings keyed to the prior version are no longer used; the agent falls back to a per-kind default until enough samples accumulate on the new version.
- **Same screen visited 5+ times in 20 actions** (loop): the loop detector triggers a back-off (overlay-dismiss, system-back) and, if still looping, terminates the active intent and routes to the next reachable plan-graph node.

## Requirements *(mandatory)*

### Functional Requirements — Vague-prompt parsing & budget

- **FR-001**: System MUST parse free-text prompts naming a casino game (e.g. `play fanatics spin to win`, `play slingo`, `play any slot`) into a structured session intent containing flow, target (kind/query/slug), budget, and terminal condition.
- **FR-002**: System MUST resolve the session intent's target query against the **game directory** (pre-launch availability layer) using exact slug, fuzzy name with kind filter, popularity ranking, and recents bias; record alternatives when more than one viable match exists. The directory MUST be populated either by ops seed or by lobby-walk auto-discovery; an entry's existence does not imply a populated playbook.
- **FR-003**: System MUST treat the operator-configured loss ceiling as a hard ceiling: a prompt-supplied loss budget is silently capped to the env value and never raised above it.
- **FR-004**: System MUST apply default terminal bounds to vague prompts: max spins (default 20) AND max wall-clock minutes (default 10) AND env loss ceiling, with the first to fire winning. Prompts may make any bound stricter; never looser.
- **FR-005**: System MUST surface, in the report, the requested ceiling vs. the effective ceiling whenever they differ.

### Functional Requirements — Navigation & search

- **FR-006**: System MUST locate a target game from a logged-in lobby state by trying, in order, recents, category jump (when game's kind is known), search-bar query, and grid scroll, stopping at the first success.
- **FR-007**: System MUST treat the search-bar path as a sequence of seeded transitions with a parameterised typing step keyed to the resolver's query string; no separate skill primitive.
- **FR-008**: When the resolver returns zero or ambiguous matches, system MUST attempt the search-bar branch with the original query and surface the resolved alternatives in the report.

### Functional Requirements — Game-context injection

- **FR-009**: System MUST trigger automatic context injection on the loaded-game signature, drawing from the **game playbook** row (per-game, post-launch knowledge) and the relevant **kind file** (per-category), without operator action. When no playbook row yet exists for the loaded game, the injected context MUST consist of the kind file alone, and the playbook row MUST be auto-populated as the agent observes the game in this and subsequent runs.
- **FR-010**: Injected context MUST be small enough to keep per-turn planner input within the configured ceiling (target: combined playbook + kind context ≤ 600 tokens).
- **FR-011**: System MUST treat new games as **directory rows** (populated by lobby-walk auto-discovery or by ops seed) and **playbook rows** (auto-populated on first launch and refined over runs); a new game category requires only a new per-kind file. New game or new kind support MUST NOT require new code paths.

### Functional Requirements — Bounded play loop

- **FR-012**: System MUST drive each round with read-balance, budget-check, action-dispatch, wait-for-round-end, record-outcome — in that order — and emit a round record per spin or hand.
- **FR-013**: System MUST detect a bonus-trigger signature and switch to a bonus sub-routine that does not place new wagers; on observing the base-grid signature, the sub-routine MUST exit and base play MUST resume.
- **FR-014**: When a bonus mini-game is encountered for the first time, system MUST treat it as bounded exploration (frozen wagering, capped action count) and surface unknown screens as proposals afterwards.
- **FR-015**: System MUST stop play at the first of: env loss ceiling reached, prompt-supplied stricter terminal reached, default max-spins reached, default max-minutes reached.
- **FR-016**: System MUST handle table-game decisions (hit, stand, double, split) and multi-hand decision streams via the same play-loop primitive — no per-game code paths.
- **FR-017**: System MUST place at least one bet in each open betting window when game type is roulette and budget allows; otherwise skip the round rather than rush a bet near window-close.

### Functional Requirements — Self-improving loop & screen graph

- **FR-018**: System MUST persist verified per-action observations (transitions, element coordinates, animation timings, round outcomes) to the runtime database after every successful tap.
- **FR-019**: System MUST derive read-time confidence from stored confidence with decay rules: build-environment mismatch reduces effective confidence; staleness past a configurable threshold ramps a penalty; staleness threshold MUST be settable per-surface (auth, settings, in-game stable, lobby/promo).
- **FR-020**: System MUST never modify stored confidence destructively; only effective confidence is computed at read time.
- **FR-021**: System MUST key learned scalars (animation timings) by build environment AND application version; on version mismatch, the row MUST be ignored at read time.
- **FR-022**: System MUST support 1-to-N transitions for stochastic outcomes (same start signature + action → multiple end signatures) with observed-count weighting; report-diff MUST treat distribution shifts as such, not as regressions, below a configurable threshold.
- **FR-023**: System MUST support an exploration mode that picks the highest-information-gain (screen, untried action) pair within a budget (max screens, max actions, max wall-clock); exploration MUST blacklist destructive edges (deposit/withdrawal/KYC-submit/account-close).
- **FR-024**: System MUST detect intent-level loops (same screen revisited beyond a small threshold within a small action window) and execute a back-off (overlay-dismiss, system-back) before terminating the intent.

### Functional Requirements — Operator gate & dashboards

- **FR-025**: System MUST surface unknown screens as candidate proposals, deduplicated by structural skeleton so banner rotation and A/B variants cluster instead of flooding the queue.
- **FR-026**: System MUST require operator action to promote any candidate proposal into the canonical screen-graph; auto-promotion is forbidden (per project constitution).
- **FR-027**: When a graduated screen-element row produces consecutive failures, system MUST auto-demote its tier (forcing re-verification on next attempt) before halting, and flag the row for operator review after a small number of failures.
- **FR-028**: System MUST throttle exploration when the pending operator queue exceeds a configurable weekly cap, and surface that throttle as an explicit signal.
- **FR-029**: Dashboard MUST allow an operator to view per-cluster evidence (screenshot, page-source path), name a canonical logical screen, accept (binding all variants in the cluster to the logical), or reject as noise.
- **FR-030**: Operator-accepted proposals MUST influence the next run's per-action lookup; rejected proposals MUST NOT reappear as new proposals on the same structural skeleton within a configurable cooldown.

### Functional Requirements — Workflow & cost optimizations

- **FR-031**: System MUST never include raw application page-source content in the planner's input prompt; only structured summaries or storage paths.
- **FR-032**: System MUST apply tiered retention to tool results: ephemeral (page-source, raw screenshots — never in prompt), durable summary (success outcomes — most recent N verbatim, older summarized), failure payload (only on failure, demoted on next success), and evidence-only (incident artifacts — never in prompt).
- **FR-033**: System MUST cache the per-run static prelude (persona, capability list scoped to active intent) on the model side so identical prefixes across turns do not re-bill input.
- **FR-034**: System MUST measure per-turn input-token volume and the prompt-cache hit rate, and persist them per run.
- **FR-035**: System MUST be replay-deterministic at the workflow level: the planner's non-deterministic decision call MUST live behind a single recorded boundary so workflow replay reads the prior decision rather than re-invoking the model.
- **FR-036**: System MUST verify, on every run, that the pending optimizations (FR-031, FR-032, FR-033, FR-035) are active; an inactive optimization MUST be visible in the run report.

### Functional Requirements — Reporting

- **FR-037**: System MUST emit a structured per-run report (machine-readable + human-readable) containing: rounds played and outcomes, balance start/end, terminal reason, signatures proposed, transitions added, animation-timing deltas, and any optimizations whose status is degraded.
- **FR-038**: System MUST keep operator-action-required findings (proposal queue, demoted rows, throttled exploration, missing optimizations) in a single visible section of the report.

### Key Entities

- **Session intent**: structured representation of an operator prompt — flow type, target (kind/query/slug), budget (loss ceiling, max spins, max minutes), terminal reason. One per workflow.
- **Game directory entry**: per-game pre-launch availability record. Holds slug, display name, kind, aliases, popularity, last-seen-in-lobby timestamp, last-played timestamp, available flag. Populated by lobby-walk auto-discovery or ops seed. Used by the resolver to map operator queries to a target slug; existence does NOT imply the game has ever been played or has a playbook.
- **Game playbook**: per-game post-launch knowledge record. Slug FK to directory. Holds action map (spin/max-bet/info/etc.), balance signature + regex, bonus-trigger signatures, auto-dismiss signatures, per-game recovery map. Auto-populated on first launch (kind file alone is injected when playbook is empty) and refined over runs.
- **Game-kind file**: per-category concise reference (turn structure, key signatures, typical animation magnitudes, recoverable modals). Shared across all games of a kind. Hand-authored.
- **Screen signature**: canonical identifier of a screen (composite of platform, app id, build environment, resolution, structural fingerprint), with operator-assigned logical name once promoted.
- **Screen element**: a tappable / interactive item on a known screen, with caller-supplied coordinates and confidence.
- **Screen transition**: an edge between two signatures driven by an action, with observed-count, confidence, edge kind (tap, back, system-back, swipe variants, longpress, type, scroll, deeplink), side-effect class (idempotent, reversible, destructive), and a precondition over runtime facts (logged-in state, jurisdiction, balance, feature flags).
- **Transition outcome**: 1-of-N possible end-signature for a (start, action) pair, with observed count.
- **Game round**: per-round telemetry (start/end, bet, balance before/after, outcome, evidence path, balance-read attempts).
- **Animation timing**: per-(game, action, build, version) statistical aggregate (mean, stddev, p95, sample count) used for learned-wait.
- **Signature proposal**: candidate screen pending operator review, with structural-skeleton hash for clustering.
- **Run report**: per-run audit (turns, intents, transitions added, evidence, optimizations active, operator-action items).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can submit a vague prompt naming any of the six target games (Spin to Win, Blackjack, Fire Roulette, Multihand Blackjack, Slingo, a slot) and the agent reaches the loaded-game screen in 100% of attempts on a stable cert build.
- **SC-002**: For each of the six target games, at least one full round is played within the operator's configured loss ceiling and the run produces a complete report.
- **SC-003**: For each of the six target games, no game-specific code paths are introduced; new games are realised solely as catalog rows and (where needed) per-kind files.
- **SC-004**: A second run of the same goal on the same stable build, after operator review of the first run's proposals, completes with at least 40% fewer planner decision calls across the equivalent flow segment.
- **SC-005**: An exploration session with a fixed budget produces a graph rendering and a diff against a baseline that an operator can review in under 15 minutes.
- **SC-006**: The operator queue is dedup'd such that ≥10 near-duplicate proposals from a noisy run cluster into ≤3 review items.
- **SC-007**: Per-turn planner input-token volume on a representative run has p50 ≤ 30,000 characters and p95 ≤ 45,000 characters; raw page-source content is absent from 100% of planner prompts; static-prelude prompt-cache hit rate is ≥ 85%.
- **SC-008**: A prompt that requests a higher loss ceiling than env is silently capped 100% of the time; the report records both requested and effective values 100% of the time.
- **SC-009**: When operator queue exceeds the configured weekly cap, exploration auto-throttles within the next workflow cycle 100% of the time.
- **SC-010**: Build-environment mismatch and version mismatch result in the relevant learned values being ignored at read time 100% of the time, without corrupting stored values.
- **SC-011**: A per-run report exists for every workflow, machine-readable and human-readable, with a single "operator action required" section listing all such findings.
- **SC-012**: Workflow replay never re-invokes the decision model; replays read prior decisions from history 100% of the time.

## Assumptions

- **Single platform**: Android is the only target platform for this feature. iOS and web are deferred (constitution future work).
- **Single goal**: All capability lives under `goal_casino_session`. No new goals are introduced.
- **Operator gate is real**: A human-in-the-loop reviews proposals on a daily-or-better cadence; the queue cap is sized so this is realistic. Auto-promotion is permanently forbidden.
- **Real-money risk on cert only**: The env loss ceiling is small (≤ tens of dollars) and runs only on cert; prod is read-only spectator if ever used.
- **Map-first contract preserved**: Every action attempts a deterministic resolution from the screen graph first; the model is fallback only.
- **Replay model**: Temporal is the durable spine; the model decision call is the only non-deterministic boundary and is captured as an activity result.
- **Account pool exists**: Test accounts are pre-funded by ops; the agent does not refill or rotate accounts.
- **OTP source is configured**: Cert uses a static OTP; cert+ uses an inbox listener already provisioned out-of-band.
- **Compliance/a11y/localization audits are out of scope**: Those become separate features.
- **Live-dealer games are out of scope**: They have a different latency profile and are deferred.
