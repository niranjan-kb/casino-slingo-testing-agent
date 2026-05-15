---
name: live_blackjack
description: Live-streamed dealer blackjack — timed betting windows over video.
---

# Live Blackjack

Streamed video of a human dealer at a real table. Differs from RNG blackjack
(`blackjack` kind) in three load-bearing ways:

1. **Timed betting window** — chips must be placed before the window closes,
   not when the agent is ready. Miss the window and the round runs without you.
2. **No synchronous decision prompt** — hit/stand decisions are also windowed,
   and tables vary (some auto-stand on timeout, some bust the hand).
3. **Side bets** — perfect pairs, 21+3, etc., usually shown as separate chip
   wells. Treat side bets as DECLINE for smoke runs.

Common variants in this app: Live Blackjack 1/2/3, Live VIP, Live VIP 2,
Infinite Blackjack, Free Bet Blackjack. EVONET-provided.

## Turn structure
`bet_window_open → place_bet → bet_window_close → deal → decision_window →
dealer_play → settle`

Decision-window and bet-window timers are read from the screen; same
`time_remaining_ms` reading twice in a row → re-poll, do not assume.

## Key signatures
- `live_bj_lobby` — table picker (one-time entry)
- `live_bj_bet_window_open` — chips active, deal-timer visible
- `live_bj_bet_window_closed` — bets locked, deal incoming
- `live_bj_decision_window` — hit/stand controls active
- `live_bj_dealer_playing` — wait
- `live_bj_settled` — outcome announced

## Time constraints
- `min_bet_window_ms`: 3000 (skip if less remains)
- `min_decision_window_ms`: 4000
- `safety_buffer_ms`: 1500 (stop tapping this close to close)

## Animation defaults
- `bet_window_ms`: 14000 · `decision_window_ms`: 12000 · `dealer_play_ms`: 5000

## Auto-dismiss modals
`side_bet_offer` (DECLINE), `insurance_offer` (DECLINE), `take_even_money`
(DECLINE), `dealer_offline` (terminate `terminal_reason=dealer_offline`),
`table_full` (try next table from lobby, max 2 retries)

## Risk tiers
- HIGH: `place_bet_chip`, `hit_button`, `stand_button`, `double_button`,
  `split_button`, `deal_now`
- MEDIUM: chip selectors, `clear_bets`, `rebet`
- LOW: chat, tips, settings

## Jurisdiction
EVONET live games are **unavailable in WV**. Runtime guard: if
`RuntimeFacts.jurisdiction == "WV"`, do not attempt this kind.
