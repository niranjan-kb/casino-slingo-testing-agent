---
name: roulette
description: Wheel-and-grid roulette — time-pressured betting windows.
---

# Roulette

Place chips on the number/colour grid during a bounded betting window;
window closes; wheel spins; result announced; winnings paid. Typical digital
window: 15–30s. Live-streamed dealer roulette is out of scope.

## Turn structure
`betting_window_open → place_bet → window_close → wheel_spin → wheel_result → settle`

The agent reads `time_remaining_ms` and skips placing if below
`min_bet_window_ms` to avoid missed-window events.

## Key signatures (logical names)
- `roulette_betting_open` — chips draggable, time indicator visible
- `roulette_wheel_spinning` — ball in motion
- `roulette_wheel_result` — winning number lit
- `roulette_settle` — winnings paid

## Animation defaults (overridden by `animation_timings` once 5+ samples)
- `betting_window_ms`: 20000
- `wheel_spin_ms`: 8000
- `result_announce_ms`: 3000

## Time constraints
- `min_bet_window_ms`: 2000 — skip the round if less remains
- `safety_buffer_ms`: 1000 — stop attempting bets this far from window-close

## Auto-dismiss modals
`low_balance_modal`, `min_bet_warning` (bump chip or skip),
`dealer_offline` (terminate `terminal_reason=dealer_offline`)

## Risk tiers
- HIGH: `place_bet_chip` (per-grid-cell)
- MEDIUM: `chip_value_selector`, `clear_bets`, `repeat_last_bet`
- LOW: stats, history, help

## Default bet pattern
Conservative outside-bet (red/black, even/odd, dozens) for smoke runs unless
per-game playbook overrides. Smoke validates window timing, not strategy.
