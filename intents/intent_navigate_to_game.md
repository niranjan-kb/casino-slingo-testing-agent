---
id: intent_navigate_to_game
end_state_signatures:
  - game_loaded
success_check: "current screen matches the target's `loaded_signature` from game_directory"
guardrails:
  - "ordered fallback: recents → category → search-bar → scroll-grid. First success wins"
  - "ResolveDirectory `unresolved` is the NORMAL case on a fresh DB — it does NOT mean the game is absent; proceed to sub-strategy 1"
  - "≥1 verified tap on a navigation control before `next=done` is allowed; otherwise SaveEvidence(label=nav_no_attempts) and emit done"
  - "target stickiness: type `SessionIntent.target.query` LITERALLY. Do NOT substitute from game_catalog/directory/page-source/training data. Wrong query → search fails → fall through (correct behavior)"
  - "search-bar selector: PREFER resource-id (e.g. `search_src_text` or app-specific search rid). NEVER `xpath: //*[contains(@text, 'Search')]` — matches system widgets, backgrounds the app"
  - "after tapping an input to focus it, the elementUUID may expire; re-find via `appium_find_element` IMMEDIATELY before `appium_set_value`"
  - "exclude_destructive=true on all path planning (no deposit/withdraw/KYC — see app_structure.md)"
  - "all four sub-strategies fail → SaveEvidence + emit done with target.unresolved=true for the report"
  - "≥5 same-screen visits in 20 actions → loop detector trips; back off via `appium_mobile_press_key key=\"BACK\"`"
  - "DetectScreen `unknown` + no visual signature confirmation = SaveEvidence(label=nav_unverified), `target.unresolved=true reason=signature_unknown`, emit done. No hallucinated success"
risk_tier: MEDIUM
notes: "Spec 005 T033 + spec 006 T006-01. Walks the lobby to a target game. Cross-ref prompts/persona/app_structure.md for screen layouts and kind→pill mapping."
---

# intent_navigate_to_game

Walk the lobby to the target's `loaded_signature`. Auth has already happened.

**Read [`app_structure.md`](../prompts/persona/app_structure.md) first** for lobby layout, kind→pill map, search location, modal defaults.

## How to proceed

1. **Resolve target** via `ResolveDirectory`. `unresolved` is the NORMAL case on a fresh DB — it does NOT mean absent; proceed to step 2.
2. **Run the checklist in order. FIRST SUCCESS wins.** A tool call counts as an attempt; thinking does not.
   - **Sub-strategy 1 — recents.** Tap matching tile in Recently-Played strip if present. Else continue.
   - **Sub-strategy 2 — category pill.** Tap the pill matching `kind` (see app_structure.md), then tap the tile in the resulting grid.
   - **Sub-strategy 3 — search.** (a) Tap search input (rid selector, not text-contains xpath). (b) Pre-typing shows trending/suggestion pills (`casino1`, `casino2`, recents) — NORMAL, NOT failure. Do NOT bail. (c) Re-find EditText after focus, type `SessionIntent.target.query` LITERALLY. (d) Tap first result.
   - **Sub-strategy 4 — scroll grid.** `appium_swipe` (or `appium_scroll`) the main grid up to N pages, tap the tile when its display text appears.
3. **Verify** after every tap with `DetectScreen` against `loaded_signature` (8s budget). Mismatch → next sub-strategy.
4. **On match**, emit `next='done'` with `active_intent=intent_navigate_to_game`. `intent_load_game_context` takes over.

## Failure handling

- **No taps attempted by step 4** → `SaveEvidence(label=nav_no_attempts)`, emit done. Don't invent a "exhausted all four strategies" rationale.
- **All four genuinely tried + failed** → `SaveEvidence(label=nav_unresolved)`, append `target.unresolved=true` to the report, emit done.
- **Loop detector trips** → `appium_mobile_press_key key="BACK"` (cap 5), re-detect; still looping → terminate.

## Scope

Navigation only. No bets, no stake changes, no settings. If you land deeper than intended, BACK out before emitting done.
