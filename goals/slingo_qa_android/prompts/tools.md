# Tools

You have TWO types of tools: **Appium MCP tools** (device interaction) and **local QA tools** (perception, coordination, reporting).

## Local QA Tools (PREFER these when applicable)

| Tool | Purpose | Key Arguments |
|------|---------|---------------|
| **`TapMapped`** | **All-in-one: lookup → tap → wait → verify → update DB** | `app_context`, `screen_name`, `element_name`, `expected_screen?`, `wait_seconds?` |
| `TapCoordinate` | Tap at raw pixel coordinates (no DB) | `x`, `y` |
| `WaitSeconds` | Pause for N seconds | `seconds` (max 30) |
| `DetectScreen` | Identify which screen is showing | `app_context` |
| `LookupElementCoords` | Get stored coordinates for an element | `app_context`, `screen_name`, `element_name` |
| `VerifyTap` | Confirm a tap caused expected transition | `app_context`, `screen_name`, `element_name`, `tapped_x`, `tapped_y`, `expected_screen` |
| `SaveEvidence` | Save screenshot as labeled evidence | `screenshot_path`, `label` |
| `GenerateReport` | Produce structured QA test report | `starting_balance`, `ending_balance`, `spins_played`, etc. |

### TapMapped — the default for all known elements

`TapMapped` replaces the 5-step manual sequence with a single call. It:
1. Looks up coordinates + confidence from the screen map DB
2. Taps the coordinates
3. Waits for the UI transition
4. Verifies the screen changed (if the element hasn't graduated)
5. Updates confidence in the DB based on the result

**Use TapMapped whenever you know the screen_name and element_name.** It guarantees the learning loop runs every time — the DB always gets consulted before tapping and updated after.

```
TapMapped(app_context="platform", screen_name="home", element_name="search_bar", expected_screen="search")
```

Returns: `{success, tapped: {x, y}, confidence, verified, current_screen}`

### When NOT to use TapMapped

- **Unknown coordinates**: Element not in the DB yet → use `appium_find_element` + `appium_click` to discover it
- **Raw pixel taps**: You already know exact coordinates from a screenshot → use `TapCoordinate`
- **Just need to look up, not tap**: Use `LookupElementCoords` alone
- **Just need to detect screen**: Use `DetectScreen` alone

### Legacy manual flow (still available for edge cases):
```
1. DetectScreen(app_context="platform")         → know which screen
2. LookupElementCoords(screen_name=..., element=...)   → get coordinates
3. TapCoordinate(x=..., y=...)                  → tap it
4. WaitSeconds(seconds=2)                       → let UI transition
5. VerifyTap(expected_screen=...)               → confirm it worked
```

### TapCoordinate vs appium_click vs appium_swipe
- **`TapCoordinate`**: Use this for ALL coordinate taps (game elements, WebView content). It wraps appium_swipe internally.
- **`appium_click`**: Use ONLY when you have an `elementId` from `appium_find_element`. For native elements only.
- **`appium_swipe`**: Use for actual swipe gestures. For taps, use `TapCoordinate` instead.

## Appium MCP Tools (device interaction)

| Action | Tool Name | Key Arguments |
|--------|-----------|---------------|
| Screenshot | `appium_screenshot` | (none) |
| Tap by element | `appium_click` | **`elementUUID`** (NOT `elementId`!) — UUID from appium_find_element result |
| Type text | `appium_set_value` | `elementUUID`, **`text`** (NOT `value`) — string to type |
| Read text | `appium_get_text` | `elementUUID` |
| Find element | `appium_find_element` | **BOTH** `strategy` AND `selector` are REQUIRED |
| Page source (XML) | `appium_get_page_source` | (none) — use to dump the whole tree when find_element misses |
| Launch app | `appium_app` | `action="activate"`, `id` (package name) |
| Kill app | `appium_app` | `action="terminate"`, `id` |
| Get contexts | `appium_context` | `action="list"` |
| Switch context | `appium_context` | `action="switch"`, `context` (target context name) |
| Press key | `appium_mobile_press_key` | `key` |
| Handle alert | `appium_alert` | `action` (`accept` / `dismiss` / `get_text`) |
| Scroll | `appium_scroll` | `direction`, `x`, `y` |
| Swipe | `appium_swipe` | `startX`, `startY`, `endX`, `endY` |
| Create session | `create_session` | `platform` (`ios`/`android`), `capabilities` |
| Delete session | `delete_session` | (none) |
| Select device | `select_device` | `platform` (`ios`/`android`), `deviceUdid` |

## appium_find_element — Usage Guide

PRIMARY tool for native screen detection. Use `DetectScreen` for automated matching.

### Argument names (CRITICAL)
The MCP tool expects `strategy` (not `by`) and `selector` (not `value`).
Example: `{"strategy": "xpath", "selector": "//*[@text='Sign In']"}`

### Valid `strategy` values:
- `"accessibility id"` — content-description
- `"id"` — resource-id (e.g., `com.betfanatics.casino.test:id/email_input`)
- `"xpath"` — XPath expression (most flexible)
- `"class name"` — Android class (e.g., `android.widget.EditText`)
- `"-android uiautomator"` — UiAutomator selector (most powerful)

### When find_element returns "could not be located":
The element doesn't match. **Don't loop** — call `appium_get_page_source` once to dump the full XML tree, then read it to find the real text/ids and pick a better selector.

### CRITICAL LIMITATION
`appium_find_element` ONLY works for native Android UI. It CANNOT see:
- Game grid numbers, reel symbols, spin button
- In-game balance text
- Any element inside the WebView iframe

For WebView elements, use `LookupElementCoords` → `TapCoordinate`.

## appium_set_value — Typing Tips

1. First tap the input field (`appium_click` with elementId, or `TapCoordinate`)
2. Then call `appium_set_value` with the text
3. ALWAYS screenshot after typing to verify — characters sometimes get dropped
4. If text is wrong, clear the field and retry

## Wait Times (use WaitSeconds)

| Transition | Seconds |
|-----------|---------|
| App launch | 3 |
| Login submit | 3-5 |
| Game load | 5-8 |
| Spin animation | 3-4 |
| Modal appearance | 2 |
| General tap | 1-2 |
