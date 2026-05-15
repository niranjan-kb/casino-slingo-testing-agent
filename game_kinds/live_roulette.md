---
name: live_roulette
description: Live-streamed dealer roulette — timed betting over video.
---

# Live Roulette

Streamed video of a human dealer spinning a physical wheel. The betting
window closes when the dealer says "no more bets", not when the agent feels
ready. Variants in this app: Lightning Roulette, Red Door Roulette, American
Roulette (live), Fanatics Live VIP variants. EVONET-provided.

Differs from RNG `roulette` in three ways:
1. **Real-time betting window** driven by the stream, not a deterministic timer.
2. **Multiplier overlays** (Lightning Roulette) — random numbers get
   2x/50x/500x multipliers after bets lock. Agent reads outcome from result
   panel, not by inspecting the wheel.
3. **No private wheel** — multiple players bet on the same spin. Outcome is
   shared, not personalised.

## Turn structure
`bet_window_open → place_bet → bet_window_close → wheel_spin → outcome_announced
→ multipliers_applied (variant-only) → settle`

## Key signatures
- `live_roulette_lobby` — table picker
- `live_roulette_bet_window_open` — chips active, timer visible
- `live_roulette_bet_window_closed` — bets locked
- `live_roulette_wheel_spinning` — ball in motion
- `live_roulette_outcome` — winning number + multipliers shown
- `live_roulette_settle` — winnings paid

## Time constraints
- `min_bet_window_ms`: 4000 — skip the round if less remains
- `safety_buffer_ms`: 1500

## Animation defaults
- `bet_window_ms`: 22000 · `wheel_spin_ms`: 12000 · `outcome_announce_ms`: 4000

## Auto-dismiss modals
`side_bet_offer` (DECLINE), `table_full` (try next from lobby, max 2 retries),
`dealer_offline` (terminate `terminal_reason=dealer_offline`)

## Risk tiers
- HIGH: `place_bet_chip` (per-grid-cell)
- MEDIUM: `chip_value_selector`, `clear_bets`, `repeat_last_bet`
- LOW: stats, history, chat

## Default bet pattern
Conservative outside bet (red/black, even/odd, dozens) — smoke validates
window timing and result reading, not strategy.

## Jurisdiction
EVONET live games **unavailable in WV**. Runtime guard as in `live_blackjack`.
