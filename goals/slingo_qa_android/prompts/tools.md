# Tools — How to Use Appium MCP

## Tool Names (CRITICAL — these differ from mobile-mcp)

| Action | Tool Name | Key Arguments |
|--------|-----------|---------------|
| Screenshot | `appium_screenshot` | (none) |
| Tap by element | `appium_click` | `elementId` (UUID from appium_find_element) |
| **Tap by coordinate** | `appium_swipe` | `startX`, `startY`, `endX`, `endY` — **see Coordinate Tap below** |
| Double tap | `appium_double_tap` | `elementId` |
| Type text | `appium_set_value` | `value` (string) |
| Read text | `appium_get_text` | `elementId` |
| Find element | `appium_find_element` | `by`, `value` (see below) |
| Launch app | `appium_activate_app` | `appId` (package name) |
| Kill app | `appium_terminate_app` | `appId` |
| Get contexts | `appium_get_contexts` | (none) — lists NATIVE/WEBVIEW |
| Switch context | `appium_switch_context` | `contextName` |
| Press key | `appium_mobile_press_key` | `key` |
| Handle alert | `appium_handle_alert` | `action` (accept/dismiss) |
| Scroll | `appium_scroll` | `direction`, `x`, `y` |
| Swipe | `appium_swipe` | `startX`, `startY`, `endX`, `endY` |
| Create session | `create_session` | capabilities JSON |
| Delete session | `delete_session` | (none) |
| Select platform | `select_platform` | `platformName` |
| Select device | `select_device` | `deviceSerial` |

## CRITICAL: Coordinate Tap (swipe-as-tap)

`appium_click` ONLY accepts an `elementId` (UUID returned by `appium_find_element`).
It does NOT accept x/y coordinates.

**To tap at specific pixel coordinates**, use `appium_swipe` with identical start and end points:
```
appium_swipe(startX=540, startY=1780, endX=540, endY=1780)
```
A zero-distance swipe = a tap. This works for ALL coordinate-based interactions.

### When to use which:
- **Native UI elements** (login fields, buttons, modals): Use `appium_find_element` to get the elementId, then `appium_click(elementId=...)`. This is more reliable because element positions can shift.
- **WebView/game elements** (grid cells, spin button, reel): Use `appium_swipe` with coordinates from the screen map. `appium_find_element` cannot see WebView content.

## appium_find_element — Usage Guide

This is your PRIMARY tool for native screen detection.

### Search strategies (use `by` parameter):
- `by="accessibility id"` — content-description attribute
- `by="id"` — resource-id (e.g., `com.betfanatics.casino:id/search_input`)
- `by="xpath"` — XPath expression
- `by="class name"` — Android class (e.g., `android.widget.EditText`)
- `by="-android uiautomator"` — UiAutomator selector (most powerful)

### Recommended patterns:
```
# Find all text elements (screen detection)
by="-android uiautomator", value="new UiSelector().textContains(\"Sign In\")"

# Find input fields
by="class name", value="android.widget.EditText"

# Find by resource ID
by="id", value="com.betfanatics.casino:id/search"
```

### CRITICAL LIMITATION
`appium_find_element` ONLY works for native Android UI. It CANNOT see:
- Game grid numbers
- Reel symbols
- Spin button
- In-game balance text
- Any element inside the WebView iframe

For WebView elements, use `appium_swipe` (zero-distance) with coordinates from the screen map.

## appium_set_value — Typing Tips

1. First tap the input field (use `appium_click` with elementId, or `appium_swipe` with coordinates)
2. Then call `appium_set_value` with the text
3. ALWAYS screenshot after typing to verify — characters sometimes get dropped
4. If text is wrong, clear the field and retry

## Coordinate System

All coordinates are in **physical pixels** (not dp/dip).
- Origin (0,0) is top-left
- x increases rightward (0 to screen width)
- y increases downward (0 to screen height)
- Standard resolution: 1080x1920

## Wait Times

After actions that trigger UI transitions, wait before screenshotting:
- App launch: 3 seconds
- Login submit: 3-5 seconds
- Game load: 5-8 seconds
- Spin animation: 3-4 seconds
- Modal appearance: 2 seconds
- General tap: 1-2 seconds
