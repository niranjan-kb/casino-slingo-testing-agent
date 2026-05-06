# Quickstart: Multi-Platform Slingo QA Agent (spec-002)

**Prerequisites**: spec-001 fully working (`goal_slingo_qa` on Android via mobile-mcp).

---

## Step 1: Verify before you build

Confirm these before implementing anything:

```bash
# Confirm iOS bundle ID
# Ask iOS team or check Xcode project: what is the bundle ID for casino debug flavor?
# Expected: com.betfanatics.casino (or com.betfanatics.casino.dev for debug)

# Get your Simulator UDID
xcrun simctl list devices | grep "iPhone 14 Pro"
# Copy the UDID — you'll need it for capabilities/local-ios.json

# Confirm iOS Simulator resolution (logical points)
# Open Simulator → Hardware → Device → should show "iPhone 14 Pro"
# Logical resolution: 393x852

# Confirm Fanatics Casino web URL per environment
# Ask team: what is the test/dev URL for the web casino?
```

---

## Step 2: Update .env

Add the new variables to your `.env`:

```bash
# Platform (drives worker task queue + goal)
PLATFORM=android               # Change to ios or web as needed

# App config (real values now)
PRODUCT_FLAVOR=casino
BUILD_ENV=dev
BUILD_TYPE=debug

# iOS (when testing iOS)
# IOS_UDID=<your-simulator-udid>

# BrowserStack (optional — only needed for cloud scale)
# BROWSERSTACK_USERNAME=
# BROWSERSTACK_ACCESS_KEY=
# BROWSERSTACK_APPIUM_URL=https://hub.browserstack.com/wd/hub
# BROWSERSTACK_PLAYWRIGHT_URL=
# CAPABILITIES_CONFIG=capabilities/browserstack-android.json
```

---

## Step 3: Run infrastructure (unchanged from spec-001)

```bash
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend
```

---

## Step 4: Run the Android worker (spec-002 version)

```bash
# In a terminal — outside Docker
source .venv/bin/activate
PLATFORM=android uv run scripts/run_worker_android.py
```

Expected output:
```
Platform: android
Task queue: casino-qa-android
Agent goal: goal_slingo_qa_android
Worker ready to process tasks!
```

**Checkpoint**: Send "Take a screenshot" in the UI. Agent calls `screenshot` via appium-mcp (not mobile-mcp). Screenshot appears in chat. This proves appium-mcp → ADB → emulator pipeline.

---

## Step 5: Run the iOS worker (macOS required)

```bash
# In a new terminal — must be on macOS
# Ensure Xcode Simulator is running with Fanatics Casino app installed
PLATFORM=ios uv run scripts/run_worker_ios.py
```

Expected output:
```
Platform: ios
macOS check: PASS
Task queue: casino-qa-ios
Agent goal: goal_slingo_qa_ios
Worker ready to process tasks!
```

If not on macOS:
```
ERROR: iOS worker requires macOS. Current OS: Linux
iOS Simulator and XCUITest are macOS-only.
```

**Checkpoint**: Send "Take a screenshot" in a new browser tab / session pointed at the iOS worker. Screenshot of the iOS Simulator appears.

---

## Step 6: Run the web worker (Docker or local)

**Option A — Docker (recommended)**:

```bash
docker compose -f docker-compose.yml up web-worker
```

**Option B — Local**:
```bash
PLATFORM=web uv run scripts/run_worker_web.py
```

**Checkpoint**: Send "Take a screenshot" in a session pointed at the web worker. Browser screenshot of the Fanatics Casino web app appears.

---

## Step 7: Three-platform simultaneous demo

With all three workers running (Android, iOS, Web) and infrastructure up:

1. Open three browser tabs to `http://localhost:5173`
2. In tab 1: select `goal_slingo_qa_android`, send "Run the full Slingo QA test"
3. In tab 2: select `goal_slingo_qa_ios`, send "Run the full Slingo QA test"
4. In tab 3: select `goal_slingo_qa_web`, send "Run the full Slingo QA test"
5. All three run independently and produce test reports

**Expected**: Three concurrent test reports, one per platform, no interference.

---

## Step 8: Validate BrowserStack (when ready)

```bash
# Set BrowserStack credentials
export BROWSERSTACK_USERNAME=your_username
export BROWSERSTACK_ACCESS_KEY=your_access_key
export CAPABILITIES_CONFIG=capabilities/browserstack-android.json

PLATFORM=android uv run scripts/run_worker_android.py
```

Send "Take a screenshot" — screenshot should come from a BrowserStack remote device. No code changes made.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| iOS worker exits immediately | Not on macOS | Run on Mac or EC2 Mac instance |
| appium-mcp connection fails | ANDROID_HOME not set | `export ANDROID_HOME=/path/to/sdk` |
| Wrong task queue | TEMPORAL_TASK_QUEUE override in .env | Remove override or set `PLATFORM` |
| Web worker can't reach browser | Playwright not installed | `npx playwright install` |
| BrowserStack auth fails | Wrong credentials or app not uploaded | Check BrowserStack dashboard |
