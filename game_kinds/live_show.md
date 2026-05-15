---
name: live_show
description: Live-streamed game-show formats — wheel-of-fortune-style hosted variants.
---

# Live Show Games

Hosted live-streamed game shows. The "wheel" or main board is the focal
point; one human host spins/triggers it; outcome triggers either a base
payout or a themed bonus round (cards flipping, Monopoly board roll, etc.).
Variants in this app: Crazy Time, MONOPOLY Deluxe. EVONET-provided.

The key difference from `live_roulette`: outcomes can branch into a
**multi-screen bonus round** that takes minutes and changes the UI
significantly. The agent treats bonus-round screens as observe-only — no
new bets are placed; the original bet rides through.

## Turn structure
`bet_window_open → place_bet → bet_window_close → host_spin → outcome →
[bonus_round_branch?] → settle`

## Key signatures
- `liveshow_lobby` — table picker
- `liveshow_bet_window_open` — segment chips active, timer visible
- `liveshow_bet_window_closed` — bets locked
- `liveshow_spin` — wheel/board in motion
- `liveshow_outcome_base` — non-bonus segment hit, settle direct
- `liveshow_bonus_intro` — bonus round starting (frozen wager)
- `liveshow_bonus_round` — bonus mechanic UI (variant-specific)
- `liveshow_settle` — winnings paid back on the main screen

## Time constraints
- `min_bet_window_ms`: 5000
- `safety_buffer_ms`: 2000

## Animation defaults
- `bet_window_ms`: 25000 · `wheel_spin_ms`: 10000 · `bonus_round_ms`: 60000

The bonus-round duration is intentionally pessimistic — Crazy Time bonuses
can run 90+ seconds. The agent does not block on this; it polls the screen
until `liveshow_settle` reappears.

## Auto-dismiss modals
`side_bet_offer` (DECLINE), `top_slot_intro` (informational, dismiss),
`dealer_offline` (terminate)

## Risk tiers
- HIGH: per-segment bet chips (`bet_segment_1x`, `bet_segment_cash_hunt`, etc.)
- MEDIUM: `chip_value_selector`, `clear_bets`, `rebet`
- LOW: chat, host_intro_close, sound

## Bonus-round behaviour
Frozen wager — the original stake rides through; no new bets placed during
the bonus screens. If `bonus_trigger_signature` fires from `game_playbook`,
the play loop switches to `intent_play_bonus` (US5 spec) and returns to
base on `liveshow_settle`.

## Jurisdiction
EVONET live games **unavailable in WV**.
