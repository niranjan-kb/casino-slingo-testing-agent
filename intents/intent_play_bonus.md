---
id: intent_play_bonus
end_state_signatures:
  - game_loaded
success_check: "bonus-round screens have exited and the base-play loaded signature is back"
guardrails:
  - "frozen wager — DO NOT place new bets, change stake, or tap deposit/buy-extra during a bonus"
  - "max_actions: 30 — exit and let the loop fall back to base if we exceed"
  - "novel screens land in signature_proposals via the auto-recorder; do not invent names"
  - "on exit-loop detection (same screen seen 3× in 5 actions), SaveEvidence + emit done"
risk_tier: HIGH
notes: "Spec 005 US5 placeholder. Full driver lands when slingo / live-show bonus flows are exercised."
---

# intent_play_bonus

You are inside a bonus round triggered by `playbook.bonus_trigger_signatures`.
The base wager is FROZEN — the bet you placed before the trigger rides
through this entire branch. Your job: navigate the bonus mini-game to its
natural exit and observe the base-play screen returning.

## How to proceed

1. **Identify the bonus surface.** Read page-source; match against
   `game_kinds/<kind>.md` bonus signatures (e.g. `slingo_bonus_screen`,
   `liveshow_bonus_intro`). Use `DetectScreen` first.
2. **Tap the most prominent advance/continue/pick element.** Use
   `FindElementWithFallback` with candidates ordered by visual prominence:
   text=`Continue`, text=`Next`, text=`Pick`, text=`Reveal`. Never tap any
   button containing the words `Buy`, `Deposit`, `Add Funds`, `Extra Spins`.
3. **Wait for transition** with `WaitForSignature` against the kind's bonus
   advance signatures, falling back to stable-UI detection.
4. **Detect exit.** When `DetectScreen` matches the base-play
   `loaded_signature`, emit `next='done'` with `active_intent=intent_play_bonus`.
   The plan graph routes back to `intent_play_game`.

## Scope

This is a navigation-only intent: no bets, no stake changes, no deposit
interactions. The base wager pays out (or doesn't) through normal play
once we exit. If after 30 actions we still haven't exited, SaveEvidence
and emit done — base play handles the residual outcome.
