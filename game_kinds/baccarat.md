---
name: baccarat
description: Player vs banker card comparison — bet on banker, player, or tie.
---

# Baccarat

Two hands are dealt: `player` and `banker`. Player bets on which side will
finish closer to 9. Live-streamed variants (Speed Baccarat, Baccarat,
EVONET) and any RNG variants share the same betting and outcome model.
Decisions are limited to where to place chips — there is no hit/stand.

## Turn structure
`bet_window_open → place_bet → bet_window_close → deal → resolve → settle`

Cards are dealt and the winner determined by table rules (no agent action
inside the deal). Optional third-card rules apply automatically.

## Key signatures
- `baccarat_lobby` — table picker (live variants)
- `baccarat_bet_window_open` — three main bet wells visible (Player, Banker, Tie)
- `baccarat_bet_window_closed` — bets locked
- `baccarat_dealing` — cards animating
- `baccarat_result` — winner highlighted
- `baccarat_settle` — winnings paid

## Time constraints (live variants)
- `min_bet_window_ms`: 3000
- `safety_buffer_ms`: 1500

## Animation defaults
- `bet_window_ms`: 14000 · `deal_ms`: 4000 · `result_ms`: 2500

## Auto-dismiss modals
`side_bet_offer` (DECLINE), `dragon_bonus_offer` (DECLINE), `table_full`
(retry from lobby, max 2), `dealer_offline` (terminate)

## Risk tiers
- HIGH: `bet_player`, `bet_banker`, `bet_tie`, side-bet wells, `chip_drop`
- MEDIUM: `chip_value_selector`, `clear_bets`, `rebet`
- LOW: history, stats, chat

## Default bet pattern
Banker (lowest house edge). Smoke validates window timing and result reading,
not strategy. Tie bet is forbidden (highest house edge).

## Jurisdiction
EVONET live games **unavailable in WV**.
