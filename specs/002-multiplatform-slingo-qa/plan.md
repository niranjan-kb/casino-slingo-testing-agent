# Implementation Plan: Multi-Platform Slingo QA Agent

**Branch**: `002-multiplatform-slingo-qa` | **Date**: 2026-03-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-multiplatform-slingo-qa/spec.md`

## Summary

Extend the Fanatics Casino QA agent from single-platform Android (spec-001, mobile-mcp) to three simultaneous platforms: Android, iOS, and Web. Each platform gets its own `AgentGoal`, MCP server, Temporal task queue, and worker script. Mobile platforms use `appium-mcp`; web uses `@playwright/mcp`. A single `PLATFORM` env var drives queue and goal selection at startup. BrowserStack is the scale target — switching requires only env var changes, zero code changes.

## Technical Context

**Language/Version**: Python 3.10 (matches existing `.venv`)
**Primary Dependencies**: Temporal SDK, LiteLLM, `appium-mcp@latest` (npx), `@playwright/mcp@latest` (npx)
**Storage**: N/A — all state in Temporal workflow history
**Testing**: Manual validation per quickstart.md checkpoints; existing pytest suite unchanged
**Target Platform**: macOS (Android + iOS workers), Docker/Linux (web worker), BrowserStack (cloud)
**Project Type**: AI agent goal extension — new goal files + worker scripts only
**Performance Goals**: Full E2E test per platform under 20 minutes (SC-007)
**Constraints**: Zero modifications to frozen framework files (FI-1, FR-013); iOS requires macOS (PT-1, FR-011); web must run in Docker (PT-4, FR-012)
**Scale/Scope**: 3 platforms × 1 game = 3 new goal files, 3 worker scripts, 2 MCP server definitions, 4 screen map files, 4 capabilities templates

## Constitution Check

*GATE: Must pass before proceeding to implementation.*

| Rule | Check | Status |
|------|-------|--------|
| PT-1 | iOS macOS-only — enforced in `run_worker_ios.py` startup | ✅ PASS |
| PT-2 | Android outside Docker on Mac — worker is native script | ✅ PASS |
| PT-3 | Android Docker on Linux with KVM — noted in docker-compose + docs | ✅ PASS |
| PT-4 | Web Docker-compatible — web-worker added to docker-compose | ✅ PASS |
| PT-5 | Single-platform workers — one goal, one queue, one MCP per worker | ✅ PASS |
| MCP-1 | No mobile-mcp in new goals — appium-mcp used throughout | ✅ PASS |
| MCP-2 | playwright-mcp for web — `@playwright/mcp@latest` | ✅ PASS |
| MCP-3 | One MCP per worker — each script spawns one npx process | ✅ PASS |
| MCP-4 | MCP is only device interface — no subprocess calls in goal/activity code | ✅ PASS |
| SC-1 | Task queue `casino-qa-{platform}` — derived in worker scripts (FR-017, FR-019) | ✅ PASS |
| SC-2 | BrowserStack = env vars only — CAPABILITIES_CONFIG file swap, no code change | ✅ PASS |
| SC-3 | BrowserStack basic auth, no SDK — standard Appium remote URL | ✅ PASS |
| SC-4 | Stateless workers — all state in Temporal, no local state in scripts | ✅ PASS |
| SC-5 | Screen maps must exist per platform — android reused; ios created in Phase 3 | ✅ PASS |
| FI-1 | Frozen files unchanged — see data-model.md | ✅ PASS |
| FI-2 | spec-001 goals frozen — `goals/slingo_qa.py` untouched | ✅ PASS |
| GD-1 | One platform per goal — three separate goal files | ✅ PASS |
| GD-2 | MCP server definition per goal — each goal uses appropriate factory function | ✅ PASS |
| GD-3 | Description is sole knowledge source — all instructions in goal `description` | ✅ PASS |
| GD-4 | included_tools specified — explicit list in each goal (FR-018) | ✅ PASS |

**No violations. Gate PASSED.**

## Project Structure

### Documentation (this feature)

```text
specs/002-multiplatform-slingo-qa/
├── plan.md              ← this file
├── spec.md
├── research.md          ← complete
├── data-model.md        ← complete
├── quickstart.md        ← complete
├── contracts/
│   └── mcp-server-definitions.md
├── checklists/
│   └── requirements.md
└── tasks.md             ← /speckit.tasks output (not yet created)
```

### Source Code Changes

```text
# EDIT — minimal changes to existing files
shared/mcp_config.py                       # add 2 factory functions
goals/__init__.py                          # register 3 new goals
docker-compose.yml                         # add web-worker service
.env.example                               # add new env vars

# NEW — all additions
goals/slingo_qa_android.py
goals/slingo_qa_ios.py
goals/slingo_qa_web.py
scripts/run_worker_android.py
scripts/run_worker_ios.py
scripts/run_worker_web.py
screen_maps/platform/android/1080x1920.json
screen_maps/platform/ios/393x852.json
screen_maps/games/slingo_cash_eruption/android/1080x1920.json
screen_maps/games/slingo_cash_eruption/ios/393x852.json
capabilities/local-android.json
capabilities/local-ios.json
capabilities/browserstack-android.json
capabilities/browserstack-ios.json

# NEVER MODIFIED
workflows/agent_goal_workflow.py
activities/tool_activities.py
shared/mcp_client_manager.py
shared/config.py
prompts/agent_prompt_generators.py
api/main.py
goals/slingo_qa.py
```

## Implementation Phases

### Phase 1: Shared Infrastructure (blocking)

**T001** — Add `get_appium_mcp_server_definition(platform, included_tools)` to `shared/mcp_config.py`. Returns `MCPServerDefinition` with `npx appium-mcp@latest`, env dict with `ANDROID_HOME`, `CAPABILITIES_CONFIG`, `NO_UI=true`. See [contracts/mcp-server-definitions.md](contracts/mcp-server-definitions.md).

**T002** — Add `get_playwright_mcp_server_definition(included_tools)` to `shared/mcp_config.py`. Returns `MCPServerDefinition` with `npx @playwright/mcp@latest`, env dict with `BROWSERSTACK_PLAYWRIGHT_URL`.

**T003** — Create `scripts/run_worker_android.py`: reads `PLATFORM`, sets `TEMPORAL_TASK_QUEUE=casino-qa-android` and `AGENT_GOAL=goal_slingo_qa_android` via `os.environ.setdefault`, runs standard worker loop.

**T004** — Create `scripts/run_worker_ios.py`: macOS check at top (`platform.system() != "Darwin"` → `sys.exit(1)` with clear message). Queue = `casino-qa-ios`. Goal = `goal_slingo_qa_ios`.

**T005** — Create `scripts/run_worker_web.py`: no OS check. Queue = `casino-qa-web`. Goal = `goal_slingo_qa_web`.

**T006** — Add `web-worker` service to `docker-compose.yml`: existing Dockerfile, `PLATFORM=web`, `command: uv run scripts/run_worker_web.py`, depends on `temporal` healthy.

**T007** — Update `.env.example`: add `PLATFORM`, `PRODUCT_FLAVOR`, `BUILD_ENV`, `BUILD_TYPE` with values. Add commented BrowserStack block (`BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY`, `BROWSERSTACK_APPIUM_URL`, `CAPABILITIES_CONFIG`).

**Checkpoint**: Android worker starts and connects to `casino-qa-android`. iOS worker on Linux exits immediately with clear error. Web worker starts in Docker.

---

### Phase 2: Android Screen Maps (parallel with Phase 3/4)

**T008** — Create `screen_maps/platform/android/1080x1920.json`: copy of `screen_maps/platform/1080x1920.json` + `"platform": "android"` field.

**T009** — Create `screen_maps/games/slingo_cash_eruption/android/1080x1920.json`: copy of existing game screen map + `"platform": "android"` field.

---

### Phase 3: iOS Screen Maps (requires Simulator + app access)

**T010** — Boot iPhone 14 Pro Simulator, install Fanatics Casino iOS debug build, take screenshots of: home, search results, game header, keep playing modal, fancash prompt. Record actual logical-point coordinates.

**T011** — Create `screen_maps/platform/ios/393x852.json` with verified coordinates from T010.

**T012** — Open Slingo Cash Eruption on iOS Simulator. Screenshot game grid, reel, spin button, end-of-round. Record coordinates.

**T013** — Create `screen_maps/games/slingo_cash_eruption/ios/393x852.json` with verified coordinates from T012.

---

### Phase 4: Capabilities Templates (parallel with Phase 2/3)

**T014** — Create `capabilities/local-android.json`: local emulator config (no remote URL).
**T015** — Create `capabilities/local-ios.json`: local Simulator config with `IOS_UDID` placeholder.
**T016** — Create `capabilities/browserstack-android.json`: BrowserStack Android with `bstack:options`.
**T017** — Create `capabilities/browserstack-ios.json`: BrowserStack iOS with `bstack:options`.

---

### Phase 5: goal_slingo_qa_android

**T018** — Create `goals/slingo_qa_android.py` skeleton: id, category_tag, MCP definition using T001 function, placeholder description.

**T019** — Write `starter_prompt`.

**T020** — Write base `description`: agent identity, device context (reads `ANDROID_SERIAL`, `APP_PACKAGE`), WebView limitation warning using appium-mcp tool names, token-saving rules.

**T021** — Write app launch section: `appium_activate_app`, wait, `screenshot` to verify.

**T022** — Write navigation section: inline Android screen map coords from T008/T009. Search → type → tap → FanCash.

**T023** — Write gameplay section: inline game coords. Spin loop, wild handling, exit via native header, balance report. Same logic as spec-001, appium tool names.

**T024** — Write E2E orchestration + `example_conversation_history`.

**T025** — Register in `goals/__init__.py`.

**Checkpoint**: Full QA test via appium-mcp on Android emulator produces test report.

---

### Phase 6: goal_slingo_qa_ios (requires Phase 3)

**T026** — Create `goals/slingo_qa_ios.py` skeleton: includes iOS-specific tools (`boot_simulator`, `setup_wda`).

**T027** — Write base `description`: iOS context (bundle ID from `APP_BUNDLE_ID`, UDID from `IOS_UDID`, logical point coordinates, iOS WebView note).

**T028** — Write app launch + navigation + gameplay sections using iOS screen map coords from T011/T013.

**T029** — Write E2E orchestration + `example_conversation_history`.

**T030** — Register in `goals/__init__.py`.

**Checkpoint**: Full QA test on iOS Simulator produces test report.

---

### Phase 7: goal_slingo_qa_web

**T031** — Create `goals/slingo_qa_web.py` skeleton: uses playwright MCP from T002.

**T032** — Write base `description`: web URL (reads `CASINO_WEB_URL`), full DOM access vs mobile WebView limitation, Playwright tool names.

**T033** — Write navigation + gameplay: `browser_navigate`, `browser_fill` for search, iframe context handling for in-game interactions, `browser_evaluate` for balance reading.

**T034** — Write E2E orchestration + `example_conversation_history`.

**T035** — Register in `goals/__init__.py`.

**Checkpoint**: Full QA test in browser via playwright-mcp produces test report.

---

### Phase 8: Three-Platform Demo

**T036** — Run all three workers simultaneously. Trigger all three goals. Verify three concurrent independent test reports. Zero interference.

**T037** — Verify `SHOW_CONFIRM=False` works across all three for seamless demo.

---

### Phase 9: BrowserStack Validation

**T038** — Upload APK + IPA to BrowserStack. Update capabilities templates with `bs://` app IDs.

**T039** — Run Android + iOS workers with BrowserStack capabilities. Verify zero code changes needed.

**T040** — Run web worker with `BROWSERSTACK_PLAYWRIGHT_URL`. Verify remote browser test runs.

---

### Phase 10: Polish

**T041** — Add `CASINO_WEB_URL`, `IOS_UDID` to `.env.example`.

**T042** — Verify zero modifications to frozen files: `git diff main -- workflows/agent_goal_workflow.py activities/tool_activities.py shared/mcp_client_manager.py shared/config.py prompts/agent_prompt_generators.py api/main.py goals/slingo_qa.py` must show no changes.

---

## Dependencies & Execution Order

```
Phase 1 (Infrastructure) ─────────────────────────────────────┐
                                                                │
Phase 2 (Android screen maps) ──────┐                         │
Phase 3 (iOS screen maps) ──────────┤                         │
Phase 4 (Capabilities) ─────────────┘                         │
         │                                                      │
         ├──> Phase 5 (Android goal) ──────────────────────────┤
         │                                                      │
         ├──> Phase 6 (iOS goal) ── blocked on Phase 3 ────────┤
         │                                                      │
         └──> Phase 7 (Web goal) ──────────────────────────────┘
                                                                │
                                              Phase 8 (Demo) ──> Phase 9 (BrowserStack) ──> Phase 10 (Polish)
```

## Open Items (Resolve Before Phase 3/6)

1. **iOS bundle ID** for debug flavor — confirm with iOS team
2. **iOS Simulator UDID** — `xcrun simctl list devices`
3. **Fanatics Casino web URL** per BUILD_ENV — confirm with web team
4. **BrowserStack app IDs** — upload APK/IPA before Phase 9
5. **appium-mcp BrowserStack basic auth validation** — test before committing Phase 9
