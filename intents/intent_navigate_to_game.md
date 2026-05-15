---
id: intent_navigate_to_game
end_state_signatures:
  - game_loaded
success_check: "current screen matches the target's `loaded_signature` from game_directory"
guardrails:
  - "ordered fallback: recents → category → search-bar → scroll-grid. First success wins"
  - "search-bar branch types the resolver query literally; do not invent alternatives"
  - "exclude_destructive=true on all path planning (no deposit/withdraw/KYC)"
  - "all four sub-strategies fail → SaveEvidence + emit done with target.unresolved=true for the report"
  - "≥5 same-screen visits in 20 actions → loop detector trips; back off via `appium_mobile_press_key key=\"BACK\"`"
risk_tier: MEDIUM
notes: "Spec 005 T033. Walks the lobby to a target game. Replaces spec-004 intent_navigate_to_screen for play flows."
---

# intent_navigate_to_game

Walk the lobby to the loaded screen of the target named in `SessionIntent.target`. Auth has already happened. Done when the target's `loaded_signature` is observed and interactable.

## How to proceed

1. Resolve target slug from `SessionIntent`. Read kind + `loaded_signature` from `game_directory`.
2. Try sub-strategies in order, FIRST SUCCESS wins:
   - **recents**: open recents strip, tap tile if present
   - **category jump**: open the category tab matching the kind, tap tile
   - **search**: tap search input, type the resolver query, tap first result
   - **scroll grid**: scroll the main grid up to cap, tap tile when visible
3. After each tap candidate, verify via `DetectScreen` matching the `loaded_signature` within 8s. Mismatch → next sub-strategy.
4. On match, emit `next='done'` with `active_intent=intent_navigate_to_game`. Next intent (`intent_load_game_context`) injects the playbook.

## Failure handling

- All four fail: SaveEvidence(label=nav_unresolved), append `target.unresolved=true` to the report, emit done so the workflow routes to `intent_report` with the failure surfaced.
- Loop detector trips: pop overlays via `appium_mobile_press_key key="BACK"`, re-detect; if still looping, terminate.

## Scope

Navigation only. No bets, no stake adjustments, no settings. If accidentally inside paytable or a deeper section, back out before completing.
