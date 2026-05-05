# Feature Specification: Multi-Platform Slingo QA Agent

**Feature Branch**: `002-multiplatform-slingo-qa`
**Created**: 2026-03-12
**Status**: Draft
**Input**: Extend the Slingo QA agent to support Android, iOS, and Web simultaneously, each running in its own worker, with a path to scale via a cloud device service.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Slingo QA on Android via Appium (Priority: P1)

A QA engineer sets `AGENT_GOAL=goal_slingo_qa_android` and starts an Android worker. They send "Run the full Slingo QA test" and the agent uses the Appium-based mobile tool layer to launch the Fanatics Casino app on an Android emulator, navigate to Slingo Cash Eruption, play one round, and report the balance change — identical behaviour to spec-001 but using the new Appium tool layer instead of mobile-mcp.

**Why this priority**: This is the migration foundation. Proves that Appium-based tooling can replicate everything spec-001 achieved, without changing the agent framework. Required before iOS or Web goals can be trusted.

**Independent Test**: With a local Android emulator running, start the Android worker, send "Run the full Slingo QA test", and verify the agent completes the full flow and produces a test report.

**Acceptance Scenarios**:

1. **Given** a local Android emulator is running with the Fanatics Casino app installed, **When** the user sends "Run the full Slingo QA test" to the Android goal, **Then** the agent launches the app, navigates to Slingo Cash Eruption, plays one round, and reports starting balance, ending balance, and delta.
2. **Given** the Android worker is running outside Docker on a Mac, **When** the agent takes a screenshot, **Then** the screenshot is returned successfully, proving the Appium-to-emulator connection works.
3. **Given** BrowserStack credentials are configured, **When** the Android worker starts, **Then** the agent connects to a BrowserStack remote Android device instead of a local emulator, with no changes to the goal definition.

---

### User Story 2 - Run Slingo QA on iOS (Priority: P1)

A QA engineer sets `AGENT_GOAL=goal_slingo_qa_ios` and starts an iOS worker on a macOS machine. They send "Run the full Slingo QA test" and the agent uses the Appium tool layer to launch the Fanatics Casino app on an iOS Simulator, navigate to Slingo Cash Eruption, play one round, and report the result.

**Why this priority**: iOS is a hard requirement. Without it the system cannot support the three-platform demo or satisfy management's acceptance criteria.

**Independent Test**: With Xcode Simulator running and the Fanatics Casino iOS app installed, start the iOS worker on a macOS machine, send "Run the full Slingo QA test", and verify the agent completes the flow.

**Acceptance Scenarios**:

1. **Given** an iOS Simulator is running on macOS with the Fanatics Casino app installed, **When** the user sends "Run the full Slingo QA test" to the iOS goal, **Then** the agent launches the app, navigates to Slingo Cash Eruption, plays one round, and reports the test result.
2. **Given** the iOS worker is running on macOS, **When** the agent calls the screenshot tool, **Then** a screenshot of the iOS Simulator is returned.
3. **Given** BrowserStack credentials are configured, **When** the iOS worker starts, **Then** the agent connects to a BrowserStack remote iOS device instead of a local simulator.
4. **Given** an attempt is made to run the iOS worker on a non-macOS host, **When** the worker starts, **Then** it fails immediately with a clear message explaining that iOS requires macOS.

Tech implemented during this story:
Update Todos

Design SQLite schema (screen_elements, run_observations, device_profiles tables)

Build screen_map DB module (CRUD operations, confidence tracking, cross-device fallback)

Write migration script to seed SQLite from existing JSON screen maps

Build element-based screen detector activity (appium_find_element signature matching)

Build vision-based screen detection activity (screenshot → LLM → which screen?)

Build vision-based element location activity (screenshot → LLM → where is element?)

Build verify-and-correct feedback loop (post-tap screenshot → verify → correct coords → update DB)

Add login and OTP screen definitions to screen maps (signatures + seed coordinates)

Rewrite goal prompt with full flow: launch → login → OTP → search → play + adaptive coord lookup

Update example conversation history for the new OTP-aware flow

Wire new activities into Temporal worker and workflow

Test end-to-end: start workflow, verify agent uses DB coords and asks for OTP
Here's the plan laid out with the reasoning for ordering:

Implementation Plan
Layer 1: Storage Foundation (tasks 1-3)
Everything builds on this. The DB schema defines what the agent can remember.

Schema: screen_elements (the coordinate cache), run_observations (what happened and what the agent learned), device_profiles (resolution, density, known offsets)
DB module: Functions like get_element_coords(device, screen, element) → returns coords + confidence, update_element_coords(...) after correction, get_best_guess(screen, element) for unknown devices (queries across all devices, picks closest resolution)
Migration: Seed from your 4 existing JSON screen maps so we don't start cold
Layer 2: Perception (tasks 4-6)
How the agent sees and understands the screen.

Element-based screen detection (primary, fast, free): Define signature elements per screen — e.g., login screen has a "Sign In" button, OTP screen has a 6-digit input. appium_find_element checks for these. When found, it also captures the element's coordinates and writes them to SQLite.
Vision screen detection (fallback): When element detection matches nothing known → screenshot → LLM: "What screen is this? Choose from: [login, otp, home, search_results, game_loading, game_playing, game_over, error, unknown]"
Vision element location: screenshot → LLM: "Where is the email input field? Return pixel coordinates." → cache result in SQLite
Layer 3: Self-Improvement (task 7)
The core loop that makes it get better over time.


tap(coords from DB) → screenshot → verify(expected_screen/state)
  ├─ match → confidence++ on those coords
  └─ mismatch → vision_locate(target_element) → get correct coords
              → update DB → log observation → retry with new coords
Each run makes the coordinate map more accurate. After 2-3 runs on a device, it should hit 100% on native screens.

Layer 4: Agent Behavior (tasks 8-10)
The actual prompts and flow.

Login/OTP screens: Add signature elements and seed coordinates. The OTP step uses next='question' to ask the user, then waits for the signal via chat.
Goal prompt rewrite: Instead of hardcoded coordinates in the prompt, the agent calls get_coords(screen, element) activities. The prompt focuses on the flow logic (what to do), not the where (coordinates come from DB).
Example conversation: Shows the OTP handoff pattern clearly so the LLM learns it.
Layer 5: Integration + Test (tasks 11-12)
Wire it all together and verify.

Key design decision: The goal prompt will change from "tap x=540, y=280 for search bar" to "use lookup_element to get search bar coords, then tap". This means the agent works on ANY device without prompt changes — only the DB needs data (or it discovers coords via vision on first run).
---

### User Story 3 - Run Slingo QA on Web Browser (Priority: P1)

A QA engineer sets `AGENT_GOAL=goal_slingo_qa_web` and starts a web worker. They send "Run the full Slingo QA test" and the agent uses the Playwright tool layer to open the Fanatics Casino web app in a browser, navigate to Slingo Cash Eruption, play one round, and report the result.

**Why this priority**: Web is the third hard requirement. Together with Android and iOS it completes the three-platform coverage needed for the demo and management sign-off.

**Independent Test**: Start the web worker (locally or in Docker), send "Run the full Slingo QA test", and verify the agent completes the web flow and produces a report.

**Acceptance Scenarios**:

1. **Given** the web worker is running, **When** the user sends "Run the full Slingo QA test" to the web goal, **Then** the agent opens the Fanatics Casino web app, navigates to Slingo Cash Eruption, plays one round, and reports the test result.
2. **Given** the web worker is running inside Docker, **When** the agent takes a browser screenshot, **Then** the screenshot is returned successfully — confirming web workers are container-compatible.
3. **Given** BrowserStack Automate credentials are configured, **When** the web worker starts, **Then** the agent runs the test against a remote BrowserStack browser instead of a local one.

---

### User Story 4 - Run All Three Platforms Simultaneously (Priority: P2)

A QA engineer starts all three workers (Android, iOS, Web) at the same time and triggers a test run on all three simultaneously. Each worker processes its test independently and in parallel. All three produce test reports without interfering with each other.

**Why this priority**: This is the demo showpiece. Three simultaneous QA runs across platforms is the core value proposition for management approval.

**Independent Test**: Start all three workers, trigger all three goals at once, and verify that three independent test reports are produced concurrently.

**Acceptance Scenarios**:

1. **Given** all three workers are running, **When** three test runs are triggered simultaneously, **Then** all three complete independently and produce separate test reports.
2. **Given** one platform's test fails mid-run, **When** the other two platforms continue, **Then** the other two complete successfully — failure is isolated per platform.

---

### User Story 5 - Scale to Cloud Devices via BrowserStack (Priority: P3)

A QA engineer changes the worker configuration to point at BrowserStack instead of local devices. Without changing any goal definitions or agent code, the same tests run against cloud-hosted real devices and browsers.

**Why this priority**: This is the production path. Local devices are for demo; cloud devices are for reliable, repeatable QA at scale.

**Independent Test**: With BrowserStack credentials set, start each worker and verify the agent connects to a BrowserStack device and completes a full test run.

**Acceptance Scenarios**:

1. **Given** BrowserStack mobile credentials are set, **When** the Android or iOS worker starts, **Then** the agent connects to a BrowserStack Appium endpoint via basic auth and runs the test on a remote device.
2. **Given** BrowserStack Automate credentials are set, **When** the web worker starts, **Then** the agent runs against a BrowserStack remote browser.
3. **Given** a switch from local to BrowserStack, **When** the test runs, **Then** zero changes to goal files, agent code, or workflow code are required — only environment variable changes.

---

### Edge Cases

- What happens when an iOS worker is started on a Linux machine? It should fail at startup with a clear message: iOS testing requires macOS.
- What happens when the Android emulator is not running and BrowserStack is not configured? The agent should detect the connection failure and report which device source it attempted.
- What happens when one platform's device is unavailable but the other two are ready? The unavailable platform's worker fails gracefully without blocking the other two.
- What happens if the Fanatics Casino app layout differs between iOS and Android? Each platform goal has its own screen map and app identifier — they are fully independent.
- What happens when the web app login flow differs from the mobile flow? The web goal has its own login sequence separate from the mobile goals.
- What happens when BrowserStack session limits are reached? The worker reports the rejection and stops gracefully rather than retrying indefinitely.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define `goal_slingo_qa_android` in `goals/slingo_qa_android.py` using the Appium mobile tool layer for Android, distinct from the spec-001 `goal_slingo_qa` goal which remains unchanged.
- **FR-002**: System MUST define `goal_slingo_qa_ios` in `goals/slingo_qa_ios.py` using the Appium mobile tool layer for iOS, including the iOS-specific app bundle ID and simulator targeting.
- **FR-003**: System MUST define `goal_slingo_qa_web` in `goals/slingo_qa_web.py` using the Playwright tool layer for browser-based testing of the Fanatics Casino web app.
- **FR-004**: System MUST add `get_appium_mcp_server_definition()` to `shared/mcp_config.py` returning an MCP server definition that launches the Appium MCP server via npx, following the same pattern as the existing mobile-mcp definition.
- **FR-005**: System MUST add `get_playwright_mcp_server_definition()` to `shared/mcp_config.py` returning an MCP server definition that launches the Playwright MCP server via npx.
- **FR-006**: System MUST define three separate Temporal task queues — one per platform — so Android, iOS, and Web workers operate independently and concurrently.
- **FR-007**: Each new goal MUST be registered in `goals/__init__.py` so it is selectable via the `AGENT_GOAL` environment variable.
- **FR-008**: The Android and iOS goals MUST include platform-specific screen maps and app identifiers (package name for Android, bundle ID for iOS).
- **FR-009**: The web goal MUST include the Fanatics Casino web app URL and browser-specific navigation instructions covering login, game search, and gameplay.
- **FR-010**: Each goal's MCP server definition MUST support switching between local device and BrowserStack remote via environment variable configuration only — no goal code changes required.
- **FR-011**: The iOS worker MUST only run on macOS. If started on a non-macOS host, it MUST fail at startup with an informative error message within 10 seconds.
- **FR-012**: The web worker MUST be able to run inside a Docker container.
- **FR-013**: System MUST NOT modify `AgentGoalWorkflow`, `ToolActivities`, `MCPClientManager`, `agent_prompt_generators.py`, or any spec-001 goal files.
- **FR-014**: Each goal's `description` MUST document platform-specific tool behaviour differences (e.g., WebView element visibility limitations on mobile vs full DOM access on web).
- **FR-015**: System MUST document the following as environment variables in `.env.example`: `PRODUCT_FLAVOR` (casino | sportsbook_casino), `BUILD_ENV` (dev | test | cert | prod), `BUILD_TYPE` (debug | release), `PLATFORM` (android | ios | web), and BrowserStack credentials `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY`, `BROWSERSTACK_APPIUM_URL`.
- **FR-016**: The Android worker MUST support running inside Docker on Linux hosts when the host exposes KVM (`/dev/kvm`). This is the required configuration for Linux EC2 staging and production environments.
- **FR-017**: Each platform's Temporal task queue MUST follow the naming convention `casino-qa-{platform}`: `casino-qa-android`, `casino-qa-ios`, `casino-qa-web`. Generic or shared queue names are prohibited.
- **FR-018**: Each goal MUST declare an explicit `included_tools` list scoped to the tools required for that platform. Open-ended tool exposure (no `included_tools` filter) is prohibited.
- **FR-019**: The `PLATFORM` environment variable MUST be used by the worker startup script to automatically select the correct task queue (`casino-qa-{PLATFORM}`) and goal, eliminating the need to manually set both `TEMPORAL_TASK_QUEUE` and `AGENT_GOAL` separately.

### Key Entities

- **Platform Goal**: An `AgentGoal` scoped to a single platform (Android, iOS, or Web). Contains the platform's MCP server definition, screen maps, app identifier, and tool instructions.
- **Appium MCP Server Definition**: Configuration to launch `npx appium-mcp@latest` as an MCP server, with optional remote server URL for BrowserStack connectivity.
- **Playwright MCP Server Definition**: Configuration to launch `npx @playwright/mcp@latest` as an MCP server, with optional BrowserStack Automate remote URL.
- **Platform Task Queue**: A named Temporal task queue dedicated to one platform's worker, enabling independent and concurrent execution across platforms.
- **Screen Map (per platform)**: JSON coordinate reference for a specific platform and resolution. Android and iOS have separate screen maps due to layout and resolution differences.
- **SlotBot (future reference)**: A colleague's Java/Kotlin library using OpenCV image template matching and a YAML-configured state machine for deterministic game automation. Complementary to this AI agent (SlotBot = automated player; this agent = AI QA tester that observes, decides, and reports). Future integration opportunity: expose SlotBot's game state detection as a callable tool within this agent for more reliable state identification. Out of scope for spec-002.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All three platform goals (Android, iOS, Web) can each independently complete a full Slingo QA test run and produce a structured test report.
- **SC-002**: All three platform workers run simultaneously without interfering with each other, each producing a separate test report in a single session.
- **SC-003**: Switching from local device to BrowserStack requires only environment variable changes — zero goal or framework code modifications.
- **SC-004**: The web worker starts and completes a full test run inside a Docker container.
- **SC-005**: Starting an iOS worker on a non-macOS host produces a clear, actionable error within 10 seconds of startup.
- **SC-006**: Zero modifications to existing framework files (`agent_goal_workflow.py`, `tool_activities.py`, `mcp_client_manager.py`, `agent_prompt_generators.py`) and zero modifications to spec-001 goal files.
- **SC-007**: Each platform's full end-to-end QA test completes in under 20 minutes on both local devices and BrowserStack.
- **SC-008**: The three-platform simultaneous demo runs successfully: all three workers active, all three tests triggered at once, all three reports produced without manual intervention.

## Assumptions

- The `PRODUCT_FLAVOR=casino` (standalone casino) and `BUILD_TYPE=debug` are the default configuration for QA testing. Release builds and sportsbook_casino flavor are tested separately.
- The Fanatics Casino app is available on both Android (APK) and iOS (IPA) and can be installed on local emulators/simulators for testing.
- The Fanatics Casino web app is accessible at a known URL and supports the same Slingo Cash Eruption game flow as the mobile apps.
- BrowserStack basic auth (username + access key) is sufficient for both Appium mobile and Playwright browser automation.
- iOS Simulator and Xcode are available on any macOS machine used for iOS testing (local Mac or AWS EC2 Mac instance).
- The Android emulator screen resolution for the new Android goal matches spec-001 (1080x1920) so existing screen maps can be reused.
- iOS Simulator resolution will differ from Android and requires a new iOS-specific screen map.
- The `appium-mcp` package single-session-per-process limitation is acceptable since each worker spawns its own independent process.
- Web gameplay is sufficiently similar to mobile that the same game rules and balance-tracking logic apply, with browser-specific navigation handled in the web goal description.
