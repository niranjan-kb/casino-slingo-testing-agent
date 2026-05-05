# Tasks: goal_slingo_qa

**Input**: Design documents from `/specs/001-goal-slingo-qa/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification. Test tasks are omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Screen map JSON files and environment configuration that all user stories depend on

- [x] T001 [P] Create platform screen map with native app UI coordinates (search bar, game header, modals) in screen_maps/platform/1080x1920.json following the Screen Map Schema from the constitution
- [x] T002 [P] Create Slingo Cash Eruption game screen map with grid coordinates (5x5), reel slots (1x5), and controls (spin button, end game, stake, settings) in screen_maps/games/slingo_cash_eruption/1080x1920.json using coordinates from the_game.md
- [x] T003 [P] Add casino-qa environment variables to .env.example: AGENT_GOAL=goal_slingo_qa, GOAL_CATEGORIES=casino-qa, ANDROID_SERIAL=emulator-5554, DEVICE_RESOLUTION=1080x1920, TEST_EMAIL, TEST_PASSWORD

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Goal file skeleton and registration that MUST be complete before any user story description can work

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create goals/slingo_qa.py with the AgentGoal skeleton: id="goal_slingo_qa", category_tag="casino-qa", agent_name="Slingo QA Agent", tools=[], mcp_server_definition=get_mobile_mcp_server_definition() with all 10 included_tools (mobile_take_screenshot, mobile_click_on_screen_at_coordinates, mobile_swipe_on_screen, mobile_type_keys, mobile_press_button, mobile_list_elements_on_screen, mobile_launch_app, mobile_get_screen_size, mobile_save_screenshot, mobile_list_available_devices). Use a placeholder description string. Import get_mobile_mcp_server_definition from shared.mcp_config. Export slingo_qa_goals list.
- [x] T005 Register the goal in goals/__init__.py: add `from goals.slingo_qa import slingo_qa_goals` import and `goal_list.extend(slingo_qa_goals)` after the existing goal_list extensions

**Checkpoint**: Goal loads and MCP tools connect. Sending any message should trigger the LLM loop (even if the description is placeholder). Verify by setting `AGENT_GOAL=goal_slingo_qa` and starting the system.

---

## Phase 3: User Story 1 - Take a Screenshot of the Emulator (Priority: P1) MVP

**Goal**: Agent can take a screenshot of the running emulator and display it in the chat UI

**Independent Test**: Start system with `AGENT_GOAL=goal_slingo_qa`, send "Take a screenshot", confirm the agent calls `mobile_take_screenshot` and the base64 image appears in conversation history

### Implementation for User Story 1

- [x] T006 [US1] Write the starter_prompt string in goals/slingo_qa.py: greet the user as "Slingo QA Agent", describe available actions (take screenshot, launch app, navigate to game, play a round, run full QA test), and ask what they'd like to do. Include the note that test credentials are read from environment variables TEST_EMAIL and TEST_PASSWORD.
- [x] T007 [US1] Write the base goal description section in goals/slingo_qa.py covering: (1) agent identity and purpose, (2) device context (emulator-5554, 1080x1920 resolution), (3) app package name (com.betfanatics.casino.dev), (4) the critical WebView warning (mobile_list_elements_on_screen cannot see in-game elements; use screenshots + coordinates for all game interactions), (5) token-saving rules (use mobile_take_screenshot not mobile_save_screenshot for viewing; call mobile_list_elements_on_screen once then reuse coordinates; 1-2s waits between taps), (6) typing reliability warning (mobile_type_keys may drop characters; always screenshot to verify typed text and retry if needed)

**Checkpoint**: Agent responds to "Take a screenshot" by proposing `mobile_take_screenshot` with correct args. After confirmation, screenshot image appears in conversation.

---

## Phase 4: User Story 2 - Launch the Fanatics Casino App (Priority: P1)

**Goal**: Agent can launch the Fanatics Casino app by package name and confirm it opened via screenshot

**Independent Test**: With emulator running and app installed, send "Launch the casino app" and verify the app opens to home/login screen

### Implementation for User Story 2

- [x] T008 [US2] Add the app launch instructions section to the goal description in goals/slingo_qa.py: when asked to launch the app, call mobile_launch_app with packageName "com.betfanatics.casino.dev", wait 3 seconds, take a screenshot to verify app opened, use mobile_list_elements_on_screen to check for login or home screen elements

**Checkpoint**: Agent launches app and confirms via screenshot. Works independently from US1.

---

## Phase 5: User Story 3 - Navigate to Slingo Cash Eruption Game (Priority: P2)

**Goal**: Agent can navigate from the home screen to a loaded Slingo Cash Eruption game

**Independent Test**: With app open and logged in, send "Find and open Slingo Cash Eruption" and verify the game loads inside the WebView

### Implementation for User Story 3

- [x] T009 [US3] Add the platform screen map coordinates section to the goal description in goals/slingo_qa.py: inline the native app coordinates from screen_maps/platform/1080x1920.json (search_bar, search_results, game_header close_button, account_button, keep_playing_modal, fancash_prompt) as a formatted reference table in the description string
- [x] T010 [US3] Add the navigation instructions section to the goal description in goals/slingo_qa.py: step-by-step instructions for searching a game (tap search bar at (540, 280), type game name via mobile_type_keys with submit=true, screenshot to verify search results, tap the matching game tile, handle FanCash prompt if shown by tapping "Start playing" at (540, 1400), wait 5-8s for game load, screenshot to verify game loaded inside WebView)
- [x] T011 [US3] Add the login instructions section to the goal description in goals/slingo_qa.py: if the app shows a login screen, read TEST_EMAIL and TEST_PASSWORD from os.getenv() and inject them into the description string using f-string interpolation (e.g., f"Test email: {os.getenv('TEST_EMAIL', 'not configured')}"), instruct the LLM to tap email field, type email, tap password field, type password, tap login button, verify login success via screenshot

**Checkpoint**: Agent navigates from home screen to loaded Slingo game. FanCash prompt handled if shown.

---

## Phase 6: User Story 4 - Play One Full Round of Slingo and Report Balance (Priority: P2)

**Goal**: Agent plays 5 base spins, handles wilds/super wilds, exits without buying extra spins, and reports balance change

**Independent Test**: With Slingo game loaded and ready to spin, send "Play one round" and verify agent completes all spins and reports balance before vs after

### Implementation for User Story 4

- [x] T012 [US4] Add the Slingo Cash Eruption game rules section to the goal description in goals/slingo_qa.py: inline game rules from the_game.md covering 5 base spins, auto-daubing, Slingos (12 paylines), prize ladder, default stake $0.20
- [x] T013 [US4] Add the game screen map coordinates section to the goal description in goals/slingo_qa.py: inline the game coordinates from screen_maps/games/slingo_cash_eruption/1080x1920.json as formatted tables - grid (5x5 with column x-values: 220, 380, 540, 700, 860 and row y-values: 730, 890, 1050, 1210, 1370), reel slots (y=1550), spin button (540, 1780), end_game DO NOT TAP warning, stake adjuster (220, 1780), game over dismiss (540, 1050)
- [x] T014 [US4] Add the special symbols handling section to the goal description in goals/slingo_qa.py: WILD detection (visual cue: game pauses, "SELECT ANY HIGHLIGHTED NUMBER" text, agent must identify which column the wild is in and tap any unmarked number in that column using grid coordinates), SUPER WILD (can tap any unmarked number, prefer center (540, 1050) for max payline coverage), Free Spin (no action needed), Fireball/blocker (no action needed)
- [x] T015 [US4] Add the end-of-round and exit instructions section to the goal description in goals/slingo_qa.py: CRITICAL WARNING that the in-game END GAME button's touch target overlaps with SPIN FOR and MUST NOT be tapped, instead always exit via native header close button at game_header position then tap "No thanks, exit" on the Keep Playing modal at (540, 1300). Include the full reliable exit sequence: (1) tap close_button, (2) wait 2s, (3) use mobile_list_elements_on_screen to confirm modal appeared, (4) tap "No thanks, exit"
- [x] T016 [US4] Add the balance tracking and test report section to the goal description in goals/slingo_qa.py: instruct LLM to read starting balance from native header (use mobile_list_elements_on_screen for "cash balance label") before entering game, read ending balance from screenshot after exiting game, produce structured report with fields: starting_balance, ending_balance, balance_delta, spins_played, wilds_encountered, super_wilds_encountered, extra_spins_purchased (always 0), anomalies, status (PASS/FAIL)
- [x] T017 [US4] Add the gameplay loop section to the goal description in goals/slingo_qa.py: step-by-step spin cycle (1) take screenshot to read game state, (2) tap spin at (540, 1780), (3) wait 3-4s for animation, (4) take screenshot to check result, (5) if wild/super wild detected handle per special symbols section, (6) if spins remaining > 0 repeat from step 1, (7) if spins = 0 execute reliable exit sequence, (8) report results

**Checkpoint**: Agent plays full round, handles wilds, exits cleanly via native header, reports balance delta. Never buys extra spins.

---

## Phase 7: User Story 5 - Full End-to-End QA Test (Priority: P3)

**Goal**: Agent chains all steps (launch, login, navigate, play, report) in response to a single command

**Independent Test**: From cold emulator with app installed but not running, send "Run the full Slingo QA test" and verify complete flow

### Implementation for User Story 5

- [x] T018 [US5] Add the full QA test orchestration section to the goal description in goals/slingo_qa.py: when the user says "Run the full Slingo QA test" or similar, execute the full sequence: (1) check device with mobile_list_available_devices, (2) verify resolution with mobile_get_screen_size, (3) launch app, (4) handle login if needed (using env credentials), (5) navigate to Slingo Cash Eruption, (6) play one round, (7) produce comprehensive test report. Include failure handling: if any step fails, report which step, include failure screenshot, and stop gracefully.
- [x] T019 [US5] Write the example_conversation_history string in goals/slingo_qa.py: approximately 25-30 exchange turns showing the full flow - user says "Run the full Slingo QA test", agent proposes screenshot, tool result shows home screen, agent proposes launch app, tool result confirms launch, agent takes screenshot, agent navigates to search, types game name, taps result, handles FanCash, game loads, reads starting balance, plays 1 spin (show spin + screenshot + result), handles a wild selection, plays remaining spins (summarized), enters extra spins phase, exits via native header + modal, reads ending balance, produces final report with next="done". Use the format from goals/food.py as pattern reference (user/agent/user_confirmed_tool_run/tool_result turns).
- [x] T020 [US5] Write the agent_friendly_description string in goals/slingo_qa.py: concise description for the goal picker UI - "Play Slingo Cash Eruption on the Fanatics Casino Android emulator and report QA results. Supports individual actions (screenshot, launch, navigate, play) and full end-to-end test flows."

**Checkpoint**: Full E2E test completes in one command. All previous user stories compose correctly.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, edge cases, and documentation

- [x] T021 [P] Add edge case handling instructions to the goal description in goals/slingo_qa.py: emulator not reachable (detect MCP error, inform user), app crash mid-game (detect unexpected screen, report), network timeout during game load (wait, retry screenshot, report if never loads), Reality Check popup (dismiss and continue), Cash Eruption Bonus (wait for Game Over modal, collect), uncertain balance readings (flag in report)
- [x] T022 [P] Verify zero modifications to framework files: confirm that workflows/agent_goal_workflow.py, activities/tool_activities.py, shared/mcp_client_manager.py, and prompts/agent_prompt_generators.py are unchanged from their pre-feature state using git diff
- [x] T023 Run quickstart.md validation: start system with AGENT_GOAL=goal_slingo_qa, send "Take a screenshot", confirm tool call, verify screenshot appears in conversation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Can start in parallel with Setup (goals/slingo_qa.py doesn't depend on screen map JSONs at import time)
- **User Stories (Phase 3-7)**: All depend on Foundational phase (T004, T005) completion
  - US1 and US2 can proceed in parallel (both P1, different description sections)
  - US3 depends on US1+US2 being complete (navigation builds on launch)
  - US4 depends on US3 (gameplay requires game to be loaded)
  - US5 depends on US1-US4 (composes all previous stories + adds example conversation)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

```
Phase 1 (Setup) ─────┐
                      ├──> Phase 2 (Foundational: T004, T005)
Phase 1 can overlap ──┘          │
                                 ├──> US1 (T006, T007) ──┐
                                 │                         ├──> US3 (T009-T011) ──> US4 (T012-T017) ──> US5 (T018-T020)
                                 └──> US2 (T008) ─────────┘
                                                                                                              │
                                                                                                              v
                                                                                                     Phase 8 (Polish)
```

### Within Each User Story

- Each story adds a section to the `description` string in goals/slingo_qa.py
- Sections are additive (later stories append to the description, don't modify earlier sections)
- The description string grows as stories are implemented

### Parallel Opportunities

- **Phase 1**: All 3 setup tasks (T001, T002, T003) can run in parallel (different files)
- **Phase 2**: T004 and T005 are sequential (T005 imports from T004)
- **US1 + US2**: T006/T007 and T008 can run in parallel (different sections of description string, but same file -- coordinate via appending)
- **Phase 8**: T021 and T022 can run in parallel

---

## Parallel Example: Phase 1

```bash
# Launch all setup tasks together:
Task: "Create platform screen map in screen_maps/platform/1080x1920.json"
Task: "Create game screen map in screen_maps/games/slingo_cash_eruption/1080x1920.json"
Task: "Add casino-qa env vars to .env.example"
```

## Parallel Example: US1 + US2

```bash
# These add different sections to the same goal description (append pattern):
Task: "T006 [US1] Write starter_prompt in goals/slingo_qa.py"
Task: "T007 [US1] Write base description section in goals/slingo_qa.py"
# Then:
Task: "T008 [US2] Add app launch section to description in goals/slingo_qa.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T005)
3. Complete Phase 3: User Story 1 (T006-T007)
4. **STOP and VALIDATE**: Send "Take a screenshot" -- verify screenshot appears in chat
5. This proves the entire pipeline: Temporal -> LLM -> mobile-mcp -> ADB -> emulator -> screenshot -> conversation

### Incremental Delivery

1. Setup + Foundational -> Goal skeleton loads, MCP tools connect
2. US1 (Screenshot) -> Pipeline proven end-to-end (MVP!)
3. US2 (Launch App) -> App control validated
4. US3 (Navigation) -> Multi-step interaction validated
5. US4 (Gameplay) -> Core QA test case working
6. US5 (Full E2E) -> Demo-ready for VP showcase
7. Polish -> Edge cases, validation, documentation

### Single Developer Strategy

Implement sequentially in priority order. Each phase checkpoint validates before moving on. Total: 23 tasks across 8 phases.

---

## Notes

- All tasks modify a single Python file (goals/slingo_qa.py) except setup tasks (JSON files, .env.example, __init__.py)
- The description string grows incrementally - each user story appends a new section
- Screen map JSONs are source-of-truth files; their content is inlined into the description at code-write time
- Test credentials (TEST_EMAIL, TEST_PASSWORD) are read from os.getenv() and injected into the description via f-string at import time
- Zero modifications to existing framework files is a hard constraint (FR-012, SC-008)
