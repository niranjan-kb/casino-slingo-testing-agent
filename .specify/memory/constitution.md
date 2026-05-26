# Casino QA Agent Constitution

**Version**: 3.0.0 · **Ratified**: 2026-03-12 · **Amended**: 2026-05-05

## Identity

A self-evolving AI player that tests the **Fanatics Casino** app (Android, iOS, Web) end-to-end. FBG is the operator, not the game studio — game engines belong to providers (Gaming Realms, Evolution, IGT, Light & Wonder, etc.). Our concern: does the app correctly wrap, launch, settle, and account for every game across every device, environment, and jurisdiction?

## Core Principles

### I. The map is primary; the LLM is the fallback

The agent's capability surface lives in `data/screen_map.db` — `screen_signatures` (where am I?), `screen_elements` (where's the X?), `screen_transitions` (what edges exist?), `game_catalog` (what games?). The LLM is invoked only when the map can't answer. Every successful action writes back; confidence grows with use. Third+ runs of any known flow are ~zero-LLM. JSON files are seed only; SQLite is the runtime source of truth.

### II. One agent, intents picked at runtime

`AgentGoalWorkflow` is the spine. The active intent is selected by the same planner LLM call that picks the next tool, every turn, from a closed-set registry (e.g., `intent_authenticate`, `intent_navigate_to_screen`, `intent_play_game`, `intent_report`). No hand-coded prompt parser, no per-prompt-shape branching, no goal-per-game files. New scenarios = new intents (rare); new games = `game_catalog` rows (common).

### III. Observers are the side-channel; never halt the run

Cross-cutting feature awareness lives in observers (`observers/`) that tick after every screen change. Observers WRITE to `observation_log` and the session report; they NEVER halt, pause, or block the goal loop. All observer-side failures — AC misses, code crashes, sub-flow timeouts, spec-loader errors — become report rows at appropriate severity, not run halts. "Silent" means silent-to-the-goal-loop, not silent-to-the-engineer reading the report.

### IV. Self-healing is non-negotiable

The agent never gets stuck. Selector miss → next strategy → dump page-source → coordinate fallback. ≥3 failed strategies on one intent: save evidence, continue optimistically. ≥5 failures on one screen: save evidence, stop. Never `next='question'` for routine recovery; the only sanctioned question is OTP under `ASK-USER-OTP` policy.

### V. Risk tiers gate map confidence promotion

| Tier | Examples | Graduation |
|---|---|---|
| HIGH-RISK | spin_button, place_bet, deposit_confirm, otp_submit, sign_in | NEVER — always verify |
| MEDIUM | close_button, keep_playing, first_result | 90% conf + 5 uses |
| LOW | search_bar, grid cells, nav tabs | 80% conf + 3 uses |

Single failure on a graduated row resets confidence. Enforced in `screen_map_db.should_verify_tap`.

### VI. Operational soul only in runtime prompts

Every token in a runtime prompt MUST drive behavior. Aspirational prose, Python-described loops, duplicated env blocks, and example conversations belong outside the prompt (CLAUDE.md, this file). Goal/intent files are operational only; ≤ 600 tokens per intent declaration.

### VII. Human approval at financial boundaries

Bets, deposits, withdrawals, promo redemptions, FanCash conversions REQUIRE human confirm in `cert`/`prod`. In `dev`/`test` (`SHOW_CONFIRM=False`) auto-confirm is permitted to enable autonomous smoke runs. Navigation, screenshots, reads, non-financial taps proceed without confirmation.

## Hard Rules

### Platform & topology

- **PT-1** iOS workers MUST run on macOS. Non-macOS hosts fail at startup within 10s.
- **PT-2** Android on macOS runs OUTSIDE Docker (KVM access).
- **PT-3** Android on Linux MAY run inside Docker iff `/dev/kvm` is exposed.
- **PT-4** Web workers MUST be Docker-compatible.
- **PT-5** One worker = one platform = one device = one MCP process = one session.

### MCP layer

- **MCP-1** All device interaction goes through MCP. No direct ADB / Selenium / Playwright in workflow or activity code.
- **MCP-2** `appium-mcp` is the mobile tool layer; **PINNED to 1.56.3** — newer versions consolidated/renamed tools and break the agent.
- **MCP-3** `@playwright/mcp` is the web tool layer.

### Scalability

- **SC-1** Per-platform Temporal task queue: `casino-qa-{android|ios|web}`.
- **SC-2** Local ↔ BrowserStack switch is env-var only. Zero code change.
- **SC-3** Worker processes are stateless. State lives in Temporal + screen_map.db.

### Workflow contract

- **WF-1** `AgentGoalWorkflow` is the spine. Modifications are permitted but MUST preserve: replay determinism (non-deterministic ops live in activities), the LLM-decides-every-action loop, the `next ∈ {confirm, question, pick-new-goal, done}` decision surface.
- **WF-2** Workflow state additions surface via `@workflow.query` handlers, not new signal types (preserves replay).
- **WF-3** `activities/tool_activities.py` and `shared/mcp_client_manager.py` are frozen. Extensions live in new activity files (`activities/observer_activity.py`, future `activities/intent_activity.py`).

### Map writeback

- **MW-1** Every verified tap-and-verify MUST write to `screen_transitions` via `record_transition_observation(success=True|False)`. Verified divergences upsert competing edges.
- **MW-2** Every `FindElement` hit MUST write to `screen_elements` keyed by current screen + intent target.
- **MW-3** Confidence is read-time-decayed by build mismatch and staleness window; never destructively modified.
- **MW-4** Unknown screens (`obs.unknown_screen`) seen ≥3 times across ≥2 runs MUST emit a signature proposal artifact. Auto-promotion is forbidden — explicit accept step required.

## Target Matrix

| Axis | Values |
|---|---|
| Platforms | `android` (live) · `ios` (planned) · `web` (planned) |
| Build env | `dev` · `test` · `cert` · `prod-debug` · `prod` |
| Build type | `debug` · `release` |
| Flavor | `casino` · `sportsbook_casino` |
| Jurisdictions | NJ · PA · MI · WV |

State-specific behavior (RG prompts, available games, payment methods) is parameterized by `JURISDICTION`, not branched. Sportsbook+casino combined app and standalone casino (STAC) ship in parallel.

## Worker Topology

```
Mac (dev)                Linux EC2                macOS EC2          BrowserStack (scale)
├ android (native)       ├ android (Docker+KVM)   └ ios (native)     ├ android remote URL
├ ios (native)           ├ web                                       ├ ios remote URL
├ web                    └ docker: temporal/api                      └ playwright remote
└ docker: temporal/api/ui/frontend
```

Three-process startup per worker, in order: `docker compose up` (temporal+api+ui+frontend) → `npx appium-mcp@1.56.3 --httpStream --port=3100` → `scripts/run_worker_<platform>.py`. Details and env vars live in `CLAUDE.md`.

## File Structure

```
intents/                          # closed-set intent registry (post-spec-004)
goals/login/                      # transitional — migrating to intent_authenticate
observers/                        # observer framework (engines + per-feature configs)
shared/screen_map_db.py           # SQLite spine: signatures, elements, transitions, catalog
shared/screen_graph.py            # path planner (max-min-conf)
prompts/persona/                  # operational soul + identity + persona_dials.yaml
data/screen_map.db                # runtime source of truth
data/known-issues.md              # bug patterns the agent watches for
specs/                            # speckit specs
workflows/agent_goal_workflow.py  # the spine — modifications follow WF-1..WF-3
activities/tool_activities.py     # FROZEN per WF-3
activities/observer_activity.py   # observer-tick activity
```

## Governance

- This constitution is the architectural source of truth. Hard Rules override any conflicting spec.
- Specs that need a Hard Rule changed MUST amend the constitution first.
- Specs are validated against this file before `/speckit.plan` runs (Constitution Check gate).
- Amendments require a version bump and a changelog entry below.
- Operational details (env vars, three-process run, test-report schema, bug-pattern lists, provider catalog) live in `CLAUDE.md` and per-spec docs, not here.

### Changes from v2.0.0 (2026-03-12) → v3.0.0 (2026-05-05)

- **Lifted FI-1 freeze on `agent_goal_workflow.py`** — replaced with **WF-1..WF-3** workflow contract; kept freeze on `tool_activities.py` and `mcp_client_manager.py`.
- **Replaced "one goal per scenario" / "new game = new goal files"** with **Principle II** (one agent, intents picked at runtime) and **Principle I** (map-primary, JSON-as-seed, SQLite-as-runtime).
- **Added** Principles **III** (observers as side-channel, never halt), **IV** (self-healing), **V** (risk tiers), **VI** (operational soul only in prompts), **VII** (human approval at financial boundaries).
- **Added MW-1..MW-4** (map writeback contract: transitions, elements, decay, signature proposals).
- **Pinned `appium-mcp` to 1.56.3** in MCP-2.
- **Removed** Goal Catalog table, P0 Journey Coverage Map, Test Report Schema, Known Bug Patterns table, CI/CD section, Backend Integration prose, full env-var listing — these live in `CLAUDE.md`, per-spec docs, or `data/known-issues.md`. Constitution stays architectural.
