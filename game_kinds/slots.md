---
name: slots
description: Reel-spin slot machines (3-reel classic to 5-reel video).
---

# Slots

Press spin → reels animate → settle → payline evaluated → balance updates →
back to spin-idle. Common features: max-bet, autospin, paytable info,
bet-amount controls, bonus mini-games (free spins, pick-em, multipliers).

## Turn structure
`bet_set → spin → reels_settle → evaluate_payline → balance_update → spin_idle`

## Key signatures (logical names)
- `slot_spin_idle` — ready for next spin
- `slot_paytable` — info screen
- `slot_bonus_intro` — pre-bonus splash
- `slot_bonus_screen` — bonus mini-game
- `slot_autoplay_settings` — autospin drawer

(Reels-animating is transient — do not signature it.)

## Animation defaults (overridden by `animation_timings` once 5+ samples)
- `spin_to_idle_ms`: 3500
- `bonus_intro_ms`: 6000
- `bet_change_ms`: 400

## Auto-dismiss modals
`low_balance_modal`, `responsible_gaming_reminder`, `session_keepalive`,
`network_glitch_modal` (retry once, then save evidence)

## Risk tiers
- HIGH: `spin_button`, `max_bet_button`, `place_bet`
- MEDIUM: `bet_up`, `bet_down`, `autoplay_start`
- LOW: paytable, info, help, sound

## Constraints
Autoplay is NEVER engaged by the agent — it skips per-round BudgetCheck.
Manual-spin only.

## Provider variants
Same kind, different chrome — UI layouts differ by provider, so per-game
playbook rows carry the actual signatures. Major providers in this catalog:
- **OGS** — top-vol Slingo + slot titles (Mice Heist, Royal Reels, Huff N
  Puff series). Spin button typically bottom-centre; bet selector left.
- **WHG** — branded slots (WrestleMania, Goonies, Megaways variants). Larger
  bonus-intro animations; "Jackpot Royale" hold-and-win popups.
- **IGT** — Cash Eruption family. Distinctive `MAX BET` chrome.
- **GG (DGC)** — Drum Frenzy / Power Combo themes.
- **PLAYTECH / PARIPLAY** — long tail.

Per-game playbook is the source of truth for spin/bet locators and the
balance regex. The kind file documents only what is universal across all
variants.
