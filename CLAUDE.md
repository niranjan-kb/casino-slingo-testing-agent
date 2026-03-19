# casino-slingo-testing-agent Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-12

## Active Technologies
- Python 3.10 (matches existing `.venv`) + Temporal SDK, LiteLLM, `appium-mcp@latest` (npx), `@playwright/mcp@latest` (npx) (002-multiplatform-slingo-qa)
- N/A — all state in Temporal workflow history (002-multiplatform-slingo-qa)

- Python 3.10 (matches existing `.venv`) + Temporal SDK, LiteLLM, FastAPI, `@anthropic/mobile-mcp@latest` (MCP server, launched via npx) (001-goal-slingo-qa)

## Project Structure

```text
backend/
frontend/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.10 (matches existing `.venv`): Follow standard conventions

## Recent Changes
- 002-multiplatform-slingo-qa: Added Python 3.10 (matches existing `.venv`) + Temporal SDK, LiteLLM, `appium-mcp@latest` (npx), `@playwright/mcp@latest` (npx)

- 001-goal-slingo-qa: Added Python 3.10 (matches existing `.venv`) + Temporal SDK, LiteLLM, FastAPI, `@anthropic/mobile-mcp@latest` (MCP server, launched via npx)

<!-- MANUAL ADDITIONS START -->

## SlotBot (`SlotBot/` submodule)

SlotBot is a **Kotlin/JVM game state machine library** (separate repo, cloned into `SlotBot/`). It automates casino game testing using Selenium + OpenCV template matching + Valkey cache for scale factors. It is **complete and published** (`com.betfanatics:slotbot:0.0.1-SNAPSHOT` on GitHub Packages).

### What SlotBot does well
- **Deterministic state detection**: OpenCV `matchTemplate` with scale factor sweep (0.8–1.2x) and Valkey caching
- **Config-driven state machine**: YAML/JSON game configs define states, transitions, delays, polling timeouts
- **Polling with deadline**: `poll_for` per state — polls every 500ms up to N seconds, adapts to load times
- **Scenario system**: Conditional actions (`repeat`, `stop`, `callback`) per state

### What SlotBot CANNOT handle for Slingo
- **Decoupled click targets**: SlotBot clicks where it detects the template. Slingo WILDs require detecting the wild on the reel but clicking a *different* location (an unmarked grid cell in the column above).
- **Strategic decisions**: Picking the best cell for WILD/SUPER WILD requires grid awareness and reasoning — not template matching.
- **Native UI outside WebView**: Exit sequence uses native Android header close button, not in-game Selenium elements.

### Hybrid Architecture (target design)

Use SlotBot's **eyes** (OpenCV) + agent's **brain** (LLM) + Temporal **durability**:

```
Activity: launch_app()              ← appium-mcp (deterministic)
Activity: login()                   ← LLM (field detection, typo retry)
Activity: navigate_to_game()        ← LLM (search, dismiss prompts)
Activity: wait_for_state("load")    ← OpenCV (poll until game loaded)
Activity: read_balance()            ← LLM (interpret screenshot)
┌─ loop: 5 spins ─────────────────────────────────────────────┐
│ Activity: tap_spin()              ← appium_click (fixed coord) │
│ Activity: wait_for_state(         ← OpenCV (which state next?) │
│   ["spin","wild","super_wild",                                 │
│    "game_over","free_spin"])                                   │
│ if wild     → Activity: handle_wild()       ← LLM             │
│ if super    → Activity: handle_super_wild() ← LLM             │
│ if game_over → break                                           │
│ else        → continue (no LLM needed)                         │
└──────────────────────────────────────────────────────────────┘
Activity: exit_game()               ← appium_click (fixed coords)
Activity: read_balance()            ← LLM
Activity: generate_report()         ← pure logic
```

**LLM only runs for ~3 of ~15 activities.** The rest are OpenCV or fixed-coordinate taps. Every activity is durable via Temporal — worker crash mid-spin replays to that exact point.

### What to steal from SlotBot into Python
1. **Game config YAML format** — state graph with `next_states`, `poll_for`, `delay`, `turn_end`
2. **OpenCV template matching** — `cv2.matchTemplate` in Python (~20 lines, no JVM bridge needed)
3. **Scale factor caching** — Valkey get/set per game+state+device (already in docker-compose)
4. **Poll-with-deadline pattern** — replace fixed "wait 3-4 seconds" with adaptive polling

### What NOT to steal
- SlotBot's "click where you found it" model (Slingo needs separate detect/click targets)
- The JVM runtime (rewrite in Python with `cv2`)
- The `Scenario` system (Temporal workflow branching is more powerful)

<!-- MANUAL ADDITIONS END -->
