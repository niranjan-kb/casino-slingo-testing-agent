# Tools

You have **Appium MCP tools** (device interaction) and **local QA tools** (perception, screen-map, session, evidence).

## Local QA Tools

| Tool | Purpose | Key arguments |
|------|---------|---------------|
| `WaitSeconds` | Pause for N seconds (max 30). **Legacy fixed-wait** — for animation/transition settles prefer `WaitForSignature` | `seconds` |
| `WaitForSignature` | Block until a target signature appears (or DOM stable). Uses learned `animation_timings` p95+2σ when samples≥5, else kind default, else stable-UI detector | `signature`, `kind_default_ms?`, `timeout_ms?` |
| `TapCoordinate` | Tap at raw pixel coords (no DB) | `x`, `y` |
| `DetectScreen` | Identify which screen is showing via DB signatures | `app_context` |
| `LookupCoords` | Look up stored coordinates for an element | `app_context`, `screen_name`, `element_name` |
| `SmartTap` | All-in-one: lookup → tap → wait → verify → update DB | `app_context`, `screen_name`, `element_name`, `expected_screen?` |
| `VerifyTap` | Confirm a tap caused expected transition | `app_context`, `screen_name`, `element_name`, `tapped_x`, `tapped_y`, `expected_screen` |
| `SaveEvidence` | Save a screenshot as labeled evidence (for failures or proof) | `screenshot_path`, `label` |
| **`FindElementWithFallback`** | **Try multiple (strategy, selector) candidates in ONE call** — first hit wins | `candidates` (list of `{strategy, selector}` dicts) |
| **`ParseSessionIntent`** | Compile the operator's free-text prompt into a `SessionIntent{flow, target, budget, terminal}` envelope. **One-shot, runs at session start** | `prompt`, `env_max_loss_usd?` |
| **`ResolveDirectory`** | Free-text query → `game_directory` slug (exact → kind+LIKE → alias → token-set Jaccard). Pure SQLite, deterministic | `query?`, `kind?`, `slug?`, `limit?` |
| **`ReadBalance`** | Parse the on-screen balance via `playbook.balance_signature` + `balance_regex`. Retries up to `min(3, ceil(1/conf))` | `playbook_slug` |
| **`BudgetCheck`** | Pre-action gate. First-of-many terminal: `balance_unparseable` > `budget_exhausted` > `n_spins` > `max_minutes` | `balance_now`, `balance_session_start`, `spins_played`, `max_loss_usd`, `max_spins`, `max_minutes`, `session_started_at_iso`, `now_iso` |

### Always prefer FindElementWithFallback over raw appium_find_element

When you have multiple selector ideas for the same element (e.g. "Continue" button could be xpath text, accessibility-id, or resource-id), pass them all as one `FindElementWithFallback` call. This collapses 3-6 LLM round-trips into one.

Example — find the Continue button on the location modal:
```json
{
  "candidates": [
    {"strategy": "xpath", "selector": "//*[@text='Continue']"},
    {"strategy": "accessibility id", "selector": "next button"},
    {"strategy": "id", "selector": "continue_button"}
  ]
}
```
Returns `{"found": true, "elementUUID": "00000000-...", "strategy": "xpath", "selector": "..."}` on first hit, or `{"found": false, "tries": 3, "errors": [...]}` on miss. The `elementUUID` plugs straight into `appium_click` / `appium_set_value` / `appium_get_text`.

## Appium MCP Tools (CRITICAL ARGUMENT NAMES)

| Action | Tool | Args |
|--------|------|------|
| Screenshot | `appium_screenshot` | (none) |
| Tap by element | `appium_click` | **`elementUUID`** (NOT `elementId`) |
| Type text | `appium_set_value` | `elementUUID`, **`text`** (NOT `value`) — string |
| Read text | `appium_get_text` | `elementUUID` |
| Find element | `appium_find_element` | **BOTH** `strategy` AND `selector` are REQUIRED |
| Page source (XML) | `appium_get_page_source` | (none) — dump the tree when find_element misses |
| Launch app | `appium_app` | `action="activate"`, `id` (package) |
| Kill app | `appium_app` | `action="terminate"`, `id` |
| Press nav key | `appium_mobile_press_key` | `key` (BACK / HOME / etc., NOT digits) |
| Handle alert | `appium_alert` | `action` (`accept` / `dismiss` / `get_text`) |
| Scroll | `appium_scroll` | `direction`, `x`, `y` |
| Swipe | `appium_swipe` | `startX`, `startY`, `endX`, `endY` |
| Create session | `create_session` | `platform` |
| Delete session | `delete_session` | (none) |
| Select device | `select_device` | `platform`, `deviceUdid?` |

### `appium_find_element` — strategies

| Strategy value | What it matches |
|---|---|
| `"xpath"` | XPath expression — **most reliable** for Compose UIs with spaces in resource-id |
| `"id"` | `resource-id` (exact) |
| `"accessibility id"` | `content-description` |
| `"class name"` | Android class name (`android.widget.EditText`) |
| `"-android uiautomator"` | UiAutomator selector — most flexible |

### Common mistakes to avoid

- **Don't omit `strategy`.** It's required.
- **Don't pass `elementId` to `appium_click`.** The actual param name is `elementUUID`.
- **Don't pass `value` to `appium_set_value`.** The param is `text`.
- **Don't pass digits to `appium_mobile_press_key`.** It only accepts navigation keys.
- **OTP / numeric codes are STRINGS.** Always emit them quoted: `"text": "864408"`. The dispatcher preserves strings on text-typed keys.

