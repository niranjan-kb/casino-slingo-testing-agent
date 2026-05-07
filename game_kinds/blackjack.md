---
name: blackjack
description: Card-table blackjack — single hand or multi-hand, vs. dealer.
---

# Blackjack

Player vs. dealer; total ≤ 21 wins. Decisions: hit, stand, double, split,
surrender (table-rule), insurance (dealer Ace up). Multi-hand variants present
N hands per round; the agent decides each sequentially before the dealer plays.

## Turn structure
`bet_set → deal_initial → player_decision_loop → dealer_action → settle`

In multi-hand the player_decision_loop iterates per hand. Dealer-state polling:
same dealer-state signature seen twice → re-poll, do not re-tap.

## Key signatures (logical names)
- `bj_betting` — chips selectable, deal button visible
- `bj_player_decision_pending` — hit/stand controls visible
- `bj_dealer_action_pending` — wait while dealer animates
- `bj_hand_settled` — outcome announced, balance updated
- `bj_insurance_offered` — dealer Ace up
- `bj_split_available` — pair dealt, split visible

## Animation defaults (overridden by `animation_timings` once 5+ samples)
- `card_deal_ms`: 600
- `dealer_play_ms`: 4000
- `settle_ms`: 2000

## Auto-dismiss modals
`insurance_offer` (default DECLINE), `take_even_money` (default DECLINE),
`connection_lost` (retry once, then save evidence)

## Risk tiers
- HIGH: `hit_button`, `stand_button`, `double_button`, `split_button`,
  `place_bet`, `deal_button`
- MEDIUM: chip selectors
- LOW: help, rules, chat

## Decision policy
Default = sensible-not-pathological for smoke runs. Per-game playbook
`recovery_json.strategy` overrides. (Strategy specifics live in playbook,
not kind.)
