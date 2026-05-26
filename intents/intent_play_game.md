---
id: intent_play_game
end_state_signatures:
  - home
  - home_lobby
  - lobby_home
success_check: "CheckBudget has emitted a terminal AND the agent has exited safely back to a lobby signature"
guardrails:
  - "respect SHOW_CONFIRM at financial boundaries (cert/prod require human confirm)"
  - "stake at minimum unless SessionIntent says otherwise; never tap stake_adjuster blindly"
  - "round shape: ReadBalance → CheckBudget → action → WaitForSignature → record_round (always in this order)"
  - "ReadBalance retry budget ≤ 3; all-fail → terminal=balance_unparseable + SaveEvidence"
  - "≥5 consecutive failures on one screen → SaveEvidence + STOP (Constitution IV)"
  - "buy-extra-spins HARD decline unless playbook.recovery_json.allow_buy_spins=true"
  - "autoplay NEVER engaged — bypasses per-round CheckBudget"
  - "on bonus_trigger_signature, enter the frozen-wager inline branch (see Bonus branch below); no separate intent"
risk_tier: HIGH
notes: "Spec 005 T035. Generic round-loop driver. Per-game in game_playbook (data); per-kind in game_kinds/<kind>.md."
---

# intent_play_game

Play the loaded game one round at a time until CheckBudget signals terminal, then exit safely to the lobby.

## Round loop (order matters)

1. **ReadBalance** via `playbook.balance_signature` + `balance_regex`. ≤3 retries; all-fail → terminal=balance_unparseable.
2. **CheckBudget** with `(balance_now, balance_session_start, SessionIntent.budget)` → `{terminal: <reason>}` or `{terminal: null}`. Env hard ceiling honoured.
3. **Action** from `playbook.actions_json`: slots/Slingo → `spin`; blackjack → `hit`/`stand`/`double`/`split`; roulette → `place_bet` only if window ≥`min_bet_window_ms`. **First-launch (actions_json empty)**: derive the action via `FindElement` against the kind's HIGH-risk element names (slots → `spin_button`, blackjack → `hit_button`/`stand_button`, roulette → grid cells). Auto-recorder persists the resolved selector to `screen_elements`; next round reuses it.
4. **WaitForSignature** for `playbook.round_end_signature`. Timeout = learned `p95+2σ` (samples≥5) → kind `learned_default` → stable-UI fallback (DOM stable 800ms).
5. **Record round** in `game_rounds`: bet, balance_before/after, outcome, evidence on failure.

## Bonus branch (frozen wager — inline)

On `bonus_trigger_signature` (from `game_playbook`), pause the round loop and:
- **Freeze the wager.** No new bets, no stake changes — the bet you placed rides through.
- **Advance** with `FindElement` against prominent text candidates: `Continue`, `Next`, `Pick`, `Reveal`, `Collect`. **NEVER tap** `Buy`, `Deposit`, `Add Funds`, `Extra Spins`.
- **Wait** with `WaitForSignature` between advances; novel screens land in `signature_proposals`.
- **Exit** when `DetectScreen` matches the base `loaded_signature` again. Cap 30 actions; over-cap → `SaveEvidence` + resume base loop on the next non-bonus signature.

## Terminal handling

When terminal fires: SaveEvidence with the terminal reason, back out via the recorded transition; decline any "Keep Playing?" prompt; emit `next='done'` once a lobby signature matches.

## Scope

Round loop only. No deposits, withdrawals, KYC. Low-balance modals → dismiss per `auto_dismiss_signatures`; CheckBudget owns terminal, not modals.
