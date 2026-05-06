---
id: intent_play_game
end_state_signatures:
  - home
  - home_lobby
success_check: "exit condition from the prompt is met (budget bound, time bound, or loss-streak) AND the agent has safely exited back to the lobby"
guardrails:
  - "respect SHOW_CONFIRM at financial boundaries — bets, deposits, withdrawals require human confirm in cert/prod"
  - "stake at the minimum unless the prompt says otherwise; never tap stake_adjuster blindly"
  - "monitor balance after every spin — record observation if it diverges from expected delta by more than the stake"
  - "≥5 consecutive spin-tap failures → SaveEvidence and STOP, do not drain the balance"
  - "if the game crashes or freezes (no balance update, no animation), SaveEvidence with label 'play_freeze' and exit"
risk_tier: HIGH
notes: "Generic spin-loop driver. Per-game data lives in game_catalog.play_loop_json (R3); no per-game intent files."
---

# intent_play_game

You are playing the currently-loaded game until an exit condition is met, then exiting safely back to the lobby. The exit condition is parsed from the user's session prompt — typical forms: `loss_bound:1.00` (stop after losing $1), `session_seconds:600` (stop after 10 min), `loss_streak:5` (stop after 5 losing rounds in a row).

## How to proceed

1. Confirm the loaded game by detecting its `loaded_signature`. If the catalog has a `play_loop_json`, follow its `actions_per_round` (e.g. `["spin"]` for slots, `["hit","stand"]` for blackjack); otherwise default to `["spin"]`.
2. Read the starting balance and stake. Adjust stake to the strategy in `play_loop_json` (default: minimum).
3. Round loop: take each action; verify the round resolves (animation ends, balance updates); record win/loss via observation_log; check exit condition.
4. When the exit condition fires, exit the game safely — back out via the recorded transition; if the FanCash / "Keep Playing?" prompt appears, dismiss it and confirm landing back on the lobby.
5. Emit `next='done'` once the lobby signature is matched.

## Catalog growth

If the game is new (no catalog row), the navigate intent should have created a stub. Update `play_loop_json` only if you've inferred a working loop. Do not invent strategies for games you've never played.
