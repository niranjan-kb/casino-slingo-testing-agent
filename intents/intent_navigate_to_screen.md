---
id: intent_navigate_to_screen
end_state_signatures:
  - home
  - home_lobby
success_check: "current screen matches the requested target signature (e.g. <game_slug>_loaded), or the requested screen_name in the screen-map"
guardrails:
  - "never tap financial or HIGH-RISK elements during navigation (place_bet, deposit_confirm, otp_submit, etc.)"
  - "if the target is a game and the catalog has it, prefer search > category browse > recent"
  - "if a pre-game modal appears (FanCash reward, location prompt, age confirm), dismiss it with the recorded transition and continue"
  - "≥5 failed strategies on one screen → SaveEvidence and STOP"
risk_tier: MEDIUM
notes: "Adds new screens and transitions to the graph as it explores the lobby."
---

# intent_navigate_to_screen

You are navigating from the current logged-in screen to a target screen. The target is named in the prompt or implied by the next active intent (typically a game's loaded screen).

## How to proceed

1. Resolve the target. If the prompt names a game (e.g. "slingo cash eruption"), the catalog row's `loaded_signature` is the target screen_name. If the prompt names a screen ("lobby", "promotions"), the screen_name is the target.
2. Detect the current screen.
3. If a path exists from current → target in the graph, walk it via SmartTap.
4. If no path exists, explore: open search, type the game name, tap the first matching result; or browse by category. Each successful step grows the graph.
5. When the loaded screen matches the target signature, emit `next='done'`.

## What you DO record

The auto-record layer writes every verified tap-and-verify into `screen_transitions`. You do not call any record-* tool yourself. If you discover a new game in the lobby (a tile you haven't seen), the next layer (intent_play_game) handles catalog upsert.

## Scope

Get to the target screen. Do not start playing — the next intent owns the play loop. Do not log out or back out of the app.
