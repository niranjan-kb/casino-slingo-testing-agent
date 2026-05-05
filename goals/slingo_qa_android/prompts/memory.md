# Memory — Screen Map & Learned Coordinates

This section contains coordinates loaded from the screen map database.
Confidence scores reflect how often each coordinate has been verified on this device.
Low-confidence entries are untested guesses — verify after tapping.

## How to Read This Map

- **confidence > 0.7**: Reliable — use directly
- **confidence 0.3–0.7**: Uncertain — use, but verify with screenshot after tap
- **confidence < 0.3**: Untested guess — prefer `appium_find_element` if available
- **source=element**: Discovered via `appium_find_element` (high trust)
- **source=vision**: Discovered via LLM vision analysis
- **source=seed**: Initial guess from JSON screen maps (needs verification)
- **source=cross_device**: Borrowed from a different device (needs verification)

## Platform Screens (Native UI)
<!-- Dynamically populated from DB at runtime -->
{{PLATFORM_COORDINATES}}

## Game Screens (WebView — appium_find_element cannot see these)
<!-- Dynamically populated from DB at runtime -->
{{GAME_COORDINATES}}

## Screen Signatures (for detection)
<!-- Dynamically populated from DB at runtime -->
Use these signatures with `appium_find_element` to detect which screen you're on:
{{SCREEN_SIGNATURES}}

## Recent Observations
<!-- Dynamically populated from DB at runtime -->
{{RECENT_OBSERVATIONS}}
