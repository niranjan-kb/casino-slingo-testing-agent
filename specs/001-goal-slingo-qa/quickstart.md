# Quickstart: goal_slingo_qa

## Prerequisites

1. Android emulator running (`emulator-5554`) at 1080x1920 resolution
2. Fanatics Casino dev app installed (`com.betfanatics.casino.dev`)
3. App logged in with a funded test account
4. Node.js installed (for `npx` to launch mobile-mcp)
5. Temporal server running (`localhost:7233`)

## Setup

1. Set environment variables in `.env`:

```env
AGENT_GOAL=goal_slingo_qa
GOAL_CATEGORIES=casino-qa
ANDROID_SERIAL=emulator-5554
SHOW_CONFIRM=True
```

2. Start the backend worker and API:

```bash
# Terminal 1: Temporal worker
python run_worker.py

# Terminal 2: FastAPI server
python -m uvicorn api.main:app --reload

# Terminal 3: Frontend
cd frontend && npm run dev
```

3. Open the UI and send a message.

## Usage Examples

| User Message | What the Agent Does |
|-------------|-------------------|
| "Take a screenshot" | Calls `mobile_take_screenshot`, shows device screen |
| "Launch the casino app" | Calls `mobile_launch_app` with `com.betfanatics.casino.dev` |
| "Search for Slingo Cash Eruption" | Taps search, types game name, shows results |
| "Play one round of Slingo" | Plays 5 spins, handles wilds, exits, reports balance |
| "Run the full Slingo QA test" | Launch -> navigate -> play -> report (full chain) |

## Files Changed

| File | Change |
|------|--------|
| `goals/slingo_qa.py` | NEW - Goal definition |
| `goals/__init__.py` | EDIT - Add `from goals.slingo_qa import slingo_qa_goals` + `goal_list.extend(slingo_qa_goals)` |
| `screen_maps/platform/1080x1920.json` | NEW - Native app coordinates |
| `screen_maps/games/slingo_cash_eruption/1080x1920.json` | NEW - Game coordinates |
| `.env.example` | EDIT - Add casino-qa env vars |

## Verification

1. Start the system with `AGENT_GOAL=goal_slingo_qa`
2. Send "Take a screenshot" in the chat
3. Confirm the screenshot tool call when prompted
4. Verify the emulator screenshot appears in the conversation

If the screenshot appears, the mobile-mcp pipeline is working end-to-end.
