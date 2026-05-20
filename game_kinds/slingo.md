---
name: slingo
description: 5×5 grid + 5-position slot reel hybrid.
sub_types: [cash_out, bonus_trigger]
---

# Slingo

5×5 grid + 5-position reel. Each spin reveals 5 symbols; matches mark the
column above. Row/col/diagonal = a Slingo; each climbs the prize ladder.

## Turn structure
`bet_set → spin → mark_grid → evaluate_pattern → ladder_progression`

## Sub-types
- `cash_out` — pays per rung (Slingo Classic, Reveal)
- `bonus_trigger` — pays only on bonus rung; higher volatility (Rainbow Riches, Centurion)

## Special symbols
- **Joker** — mark any in the column above
- **Super Joker** — mark anywhere on the grid
- **Free Spin** — +1 spin
- **Coin** — instant cash, ladder-independent
- **Devil** — blocker (wasted reel position)

## Wild placement priority
1. Complete an existing line
2. Centre (part of 4 lines)
3. Corners (3 lines)
4. Edges (2 lines)

## Key signatures
`slingo_base_grid`, `slingo_bonus_intro`, `slingo_bonus_screen`,
`slingo_ladder_complete`, `slingo_extra_spin_offer`, `slingo_free_spin_grant`

## Animation defaults (overridden by `animation_timings` ≥5 samples)
`spin_to_idle_ms` 4500 · `bonus_intro_ms` 8000

## Auto-dismiss
`low_balance_modal`, `geo_warning`, `session_renewal`

## Risk tiers
HIGH: `spin_button`, `place_bet` · MEDIUM: bet-amount · LOW: help, paytable

## Buy-extra-spins policy (HARD)
On `slingo_extra_spin_offer`: **always decline**. Variable cost (10–20× base
stake near full-house) blows `MAX_LOSS_USD`. Override per-game via playbook
`recovery_json.allow_buy_spins`.

## Bonus exploration
On `slingo_bonus_screen`, `intent_play_game` enters its frozen-wager branch:
no new bets, no stake changes, advance via prominent Continue/Next/Pick text
candidates. Returns to base play when `slingo_base_grid` is observed. Capped
at 30 actions; novel screens → `signature_proposals`.
