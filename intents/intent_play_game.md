---
id: intent_play_game
end_state_signatures:
  - home
  - home_lobby
  - lobby_home
success_check: "BudgetCheck has emitted a terminal AND the agent has exited safely back to a lobby signature"
guardrails:
  - "respect SHOW_CONFIRM at financial boundaries (cert/prod require human confirm)"
  - "stake at minimum unless SessionIntent says otherwise; never tap stake_adjuster blindly"
  - "round shape: ReadBalance → BudgetCheck → action → WaitForSignature → record_round (always in this order)"
  - "ReadBalance retry budget ≤ 3; all-fail → terminal=balance_unparseable + SaveEvidence"
  - "≥5 consecutive failures on one screen → SaveEvidence + STOP (Constitution IV)"
  - "buy-extra-spins HARD decline unless playbook.recovery_json.allow_buy_spins=true"
  - "autoplay NEVER engaged — bypasses per-round BudgetCheck"
  - "on bonus_trigger_signature, plan-graph routes to intent_play_bonus; do not handle inline"
risk_tier: HIGH
notes: "Spec 005 T035. Generic round-loop driver. Per-game in game_playbook (data); per-kind in game_kinds/<kind>.md."
---

# intent_play_game

Play the loaded game one round at a time until BudgetCheck signals terminal, then exit safely to the lobby.

## Round loop (order matters)

1. **ReadBalance** via `playbook.balance_signature` + `balance_regex`. ≤3 retries; all-fail → terminal=balance_unparseable.
2. **BudgetCheck** with `(balance_now, balance_session_start, SessionIntent.budget)` → `{terminal: <reason>}` or `{terminal: null}`. Env hard ceiling honoured.
3. **Action** from `playbook.actions_json`: slots/Slingo → `spin`; blackjack → per-hand `hit`/`stand`/`double`/`split`; roulette → `place_bet` only if window ≥`min_bet_window_ms`. **First-launch (playbook.actions_json is empty)**: derive the action button via `FindElementWithFallback` against the kind's HIGH-risk element names (e.g. slots → `spin_button`, blackjack → `hit_button`/`stand_button`, roulette → grid cells). Once the selector resolves, the auto-recorder writes it back into `screen_elements` and the next round reuses it — no manual playbook writes needed.
4. **WaitForSignature** for `playbook.round_end_signature`. Timeout = learned `p95+2σ` (samples≥5) → kind `learned_default` → stable-UI detector (DOM stable 800ms).
5. **Record round** in `game_rounds`: bet, balance_before/after, outcome, evidence on failure.

## Terminal handling

When terminal fires: SaveEvidence with the terminal reason, back out via the recorded transition; decline any "Keep Playing?" prompt; emit `next='done'` once a lobby signature matches.

## Scope

Round loop only. No deposits, withdrawals, KYC. Low-balance modals → dismiss per `auto_dismiss_signatures`; BudgetCheck owns terminal, not modals.
