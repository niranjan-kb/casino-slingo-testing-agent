# Feature Specification: goal_slingo_qa

**Feature Branch**: `001-goal-slingo-qa`
**Created**: 2026-03-12
**Status**: Draft
**Input**: Add goal_slingo_qa: an AI agent goal that uses mobile-mcp tools to play Slingo Cash Eruption on the Fanatics Casino Android app and report balance changes

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Take a Screenshot of the Emulator (Priority: P1)

A QA engineer sets `AGENT_GOAL=goal_slingo_qa` in `.env`, starts the system, and sends "Take a screenshot" in the chat UI. The agent calls `mobile_take_screenshot` via mobile-mcp and the screenshot appears in the conversation.

**Why this priority**: This is the foundation. If the agent can't see the device, nothing else works. Proves the mobile-mcp to ADB to emulator pipeline end-to-end through the existing Temporal agent loop.

**Independent Test**: Start the system with the Slingo QA goal, send any message, confirm the agent calls `mobile_take_screenshot` and the result (base64 image) appears in conversation history.

**Acceptance Scenarios**:

1. **Given** the emulator is running and `AGENT_GOAL=goal_slingo_qa` is set, **When** the user sends "Take a screenshot of the emulator", **Then** the agent responds with `next: confirm, tool: mobile_take_screenshot` and after confirmation the screenshot image is returned in the tool result.
2. **Given** no emulator is running, **When** the agent attempts `mobile_take_screenshot`, **Then** the tool returns an error and the agent reports the failure to the user.
3. **Given** `SHOW_CONFIRM=True`, **When** the agent proposes a screenshot, **Then** the UI shows a confirm button and the tool only executes after the user clicks confirm.

---

### User Story 2 - Launch the Fanatics Casino App (Priority: P1)

The QA engineer sends "Launch the Fanatics Casino app". The agent calls `mobile_launch_app` with the correct package name, waits, then takes a screenshot to confirm the app opened.

**Why this priority**: Can't test anything without the app running. Validates the agent knows the package name and can sequence tool calls (launch then wait then screenshot then verify).

**Independent Test**: With emulator running and app installed, send "Launch the casino app" and verify the app opens to its home/login screen.

**Acceptance Scenarios**:

1. **Given** the emulator is running and the Fanatics Casino app is installed, **When** the user says "Launch the casino app", **Then** the agent calls `mobile_launch_app` with `packageName: com.betfanatics.casino.dev` and the app opens.
2. **Given** the app is already running, **When** the agent calls `mobile_launch_app`, **Then** the app is brought to foreground without crashing.
3. **Given** the app is not installed, **When** the agent calls `mobile_launch_app`, **Then** the tool returns an error and the agent informs the user.

---

### User Story 3 - Navigate to Slingo Cash Eruption Game (Priority: P2)

The QA engineer sends "Search for Slingo Cash Eruption and open it". The agent navigates through the app: taps the search bar, types the game name, taps the search result, handles the FanCash prompt, and waits for the game to load. The agent confirms success via screenshot.

**Why this priority**: Validates the full navigation chain with multiple tool calls in sequence, text input, and screen state detection. This is the first multi-step interaction.

**Independent Test**: With app open and logged in, send "Find and open Slingo Cash Eruption" and verify the game loads inside the WebView.

**Acceptance Scenarios**:

1. **Given** the app is on the home screen and logged in, **When** the user says "Search for Slingo Cash Eruption and open it", **Then** the agent taps the search bar, types the game name via `mobile_type_keys`, taps the game result via `mobile_click_on_screen_at_coordinates`, and the game loads.
2. **Given** the game is not found in search results, **When** the agent takes a screenshot after typing, **Then** the agent reports that the game was not found.
3. **Given** a FanCash prompt appears after tapping the game, **When** the agent detects this screen, **Then** the agent taps "Start playing" to proceed.

---

### User Story 4 - Play One Full Round of Slingo and Report Balance (Priority: P2)

The QA engineer sends "Play one round of Slingo and report the balance change". The agent reads the starting balance, spins through 5 base spins (handling wilds and super wilds if they appear), ends the round (does NOT buy extra spins), reads the ending balance, and reports the delta.

**Why this priority**: This is the core QA test case. It exercises the full gameplay loop with decision-making (wild selection, end game vs extra spins).

**Independent Test**: With the Slingo game loaded and ready to spin, send "Play one round" and verify the agent completes all spins and reports balance before vs after.

**Acceptance Scenarios**:

1. **Given** Slingo Cash Eruption is loaded and showing the game screen, **When** the user says "Play one round", **Then** the agent reads the starting balance from the screenshot, taps the spin button 5 times (with screenshots between each), and reports the starting balance, ending balance, and delta.
2. **Given** a WILD symbol appears on the reel during a spin, **When** the agent detects the wild selection prompt via screenshot, **Then** the agent selects an unmarked number in the wild's column by tapping at the appropriate grid coordinates.
3. **Given** a SUPER WILD appears, **When** the agent detects it, **Then** the agent selects any unmarked number on the grid (preferring center positions for maximum payline coverage).
4. **Given** all base spins are exhausted and the extra spins phase begins, **When** the agent detects the "Spin for $X.XX" button, **Then** the agent taps the native header exit button and confirms "No thanks, exit" on the modal (does NOT buy extra spins).
5. **Given** the game is over, **When** the agent reads the final balance, **Then** the agent reports a structured result: starting balance, ending balance, bet amount, spins played, and balance delta.

---

### User Story 5 - Full End-to-End QA Test (Priority: P3)

The QA engineer sends "Run the full Slingo QA test". The agent chains all steps: launch app, log in, search game, open game, play round, report. This is the demo flow for the VP.

**Why this priority**: Composes all previous stories into a single command. Requires all prior stories to work. This is the showcase.

**Independent Test**: From a cold emulator with app installed but not running, send "Run the full QA test" and verify the agent completes the entire flow and produces a test report.

**Acceptance Scenarios**:

1. **Given** the emulator is running and the app is installed, **When** the user says "Run the full Slingo QA test", **Then** the agent launches the app, logs in (with credentials from the conversation or env), navigates to Slingo, plays one round, and reports the complete test result.
2. **Given** any step fails (login fails, game not found, tap misses), **When** the agent detects the failure via screenshot, **Then** the agent reports which step failed, includes a screenshot of the failure state, and stops gracefully.

---

### Edge Cases

- What happens when the emulator is not reachable via ADB? Agent should detect the mobile-mcp error and inform the user.
- What happens when the app crashes mid-game? Agent should detect the unexpected screen (home screen or crash dialog) and report it.
- What happens when a network timeout occurs during game load? Agent should wait, retry screenshot, and report if the game never loads.
- What happens when the balance text is partially obscured or the LLM misreads it? The report should flag uncertain readings.
- What happens when the game enters the Cash Eruption Bonus (unlikely on a single round)? Agent should wait for the bonus to complete and the "Game Over" modal to appear, then collect.
- What happens when a Reality Check popup appears (after extended play)? Agent should dismiss it and continue.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define a new `AgentGoal` named `goal_slingo_qa` in `goals/slingo_qa.py` with `mcp_server_definition` pointing to `@mobilenext/mobile-mcp@latest`.
- **FR-002**: System MUST register the goal in `goals/__init__.py` so it is selectable via `AGENT_GOAL=goal_slingo_qa`.
- **FR-003**: System MUST add `get_mobile_mcp_server_definition()` in `shared/mcp_config.py` returning an `MCPServerDefinition` with `command: npx`, `args: ["-y", "@mobilenext/mobile-mcp@latest"]`.
- **FR-004**: The goal's `included_tools` MUST include: `mobile_take_screenshot`, `mobile_click_on_screen_at_coordinates`, `mobile_swipe_on_screen`, `mobile_type_keys`, `mobile_press_button`, `mobile_list_elements_on_screen`, `mobile_launch_app`, `mobile_get_screen_size`, `mobile_save_screenshot`, `mobile_list_available_devices`.
- **FR-005**: The goal's `description` MUST encode Slingo Cash Eruption game rules (from `the_game.md`), including: 5 base spins, wild/super wild handling, extra spins phase, and the instruction to always end the game via native header exit during extra spins.
- **FR-006**: The goal's `description` MUST encode the screen map coordinates for the current resolution, so the LLM can reference known tap targets.
- **FR-007**: The goal's `description` MUST instruct the LLM to read the balance before and after gameplay and report the delta.
- **FR-008**: The goal's `description` MUST warn the LLM that in-game elements (WebView/iframe) are invisible to `mobile_list_elements_on_screen` and must be interacted with via coordinates from screenshots.
- **FR-009**: The goal's `description` MUST warn the LLM that the END GAME button's touch target overlaps with SPIN FOR and to always use the native header exit button plus "No thanks, exit" modal instead.
- **FR-010**: The goal's `example_conversation_history` MUST include a realistic tool call sequence: screenshot, launch, screenshot, navigate, play, end, report.
- **FR-011**: The goal's `starter_prompt` MUST greet the user and describe available actions (take screenshot, launch app, navigate to game, play round, run full test).
- **FR-012**: System MUST NOT modify `AgentGoalWorkflow`, `ToolActivities`, `MCPClientManager`, or `agent_prompt_generators.py`.
- **FR-013**: System MUST add `casino-qa` as a valid value for `GOAL_CATEGORIES` so the goal appears when the category filter is set.

### Key Entities

- **AgentGoal**: The `goal_slingo_qa` goal definition containing description, tools, MCP server definition, starter prompt, and example conversation. Lives in `goals/slingo_qa.py`.
- **MCPServerDefinition**: Configuration for the mobile-mcp server with command, args, and included tools. Lives in `shared/mcp_config.py`.
- **Screen Map**: JSON knowledge base of UI element coordinates keyed by resolution. Loaded into the goal description. Lives in `screen_maps/`.
- **Test Report**: Structured output from a completed test run with balance before/after, delta, spins played, and screenshots captured. Returned as the final LLM response.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The agent can take a screenshot of the running emulator and display it in the chat UI within 10 seconds of the user's request.
- **SC-002**: The agent can launch the Fanatics Casino app by package name and confirm it opened via a follow-up screenshot.
- **SC-003**: The agent can navigate from the home screen to a loaded Slingo Cash Eruption game in under 60 seconds (including search, tap, and game load).
- **SC-004**: The agent can play one full round (5 base spins) and correctly report the starting balance, ending balance, and delta.
- **SC-005**: The agent correctly handles wild symbols by tapping an unmarked number in the appropriate column at least 80% of the time.
- **SC-006**: The agent never accidentally buys extra spins. It always exits via the native header exit button and modal.
- **SC-007**: The full end-to-end test (launch, login, navigate, play, report) completes in under 15 minutes.
- **SC-008**: Zero modifications to existing framework files (`agent_goal_workflow.py`, `tool_activities.py`, `mcp_client_manager.py`, `agent_prompt_generators.py`).
