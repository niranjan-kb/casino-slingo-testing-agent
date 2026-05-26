---
id: intent_navigate_to_screen
end_state_signatures:
  - home
  - home_lobby
success_check: "current screen matches the requested target's logical_id (see anchor list below) or its seeded screen_name"
guardrails:
  - "non-play navigation only — if the target is a game, the workflow should be dispatching intent_navigate_to_game instead"
  - "exclude_destructive=true on all path planning"
  - "never tap: Deposit, Add Funds, Withdraw, Convert FanCash, KYC Submit, Cancel Withdrawal, the Fanatics logo on non-debug builds, or Confirm/Submit inside the Quick Deposit bottom sheet"
  - "≥1 verified tap on a navigation control before `next=done` is allowed"
  - "≥5 same-screen visits in 20 actions → loop detector trips; back off via `appium_mobile_press_key key=\"BACK\"` (cap 5)"
  - "≥3 failed strategies on one screen → SaveEvidence, try alternative; ≥5 failures → SaveEvidence and STOP"
risk_tier: MEDIUM
notes: "Spec 004 + spec 006 T006-04. Off-lobby + recovery navigation. Cross-ref prompts/persona/app_structure.md for anchor map and universal modal handling."
---

# intent_navigate_to_screen

Reach a target screen from any logged-in surface. Auth has already happened. The target is named in `SessionIntent.target` or implied by an upstream intent.

**Read [`app_structure.md`](../prompts/persona/app_structure.md) first** for anchor screens, universal-modal defaults, and the shared navigation safety rules (back-to-home recovery, loop detector, deposit avoidance) — all inherited.

## Legitimate anchor targets

Any seeded `logical_screens` row is a legitimate target. The reliable ones today: `home`, `home_lobby`, `profile`, `settings`, `promotions`, `rewards`, `help`, `fancash_spins_daily`. Targets whose `role='destructive'` (`debug_menu`, `quick_deposit_sheet`) are NEVER legitimate — see guardrails.

## How to proceed

1. **Resolve target.** If `SessionIntent.target` names a game (kind/slug/query), this is the wrong intent — flag for the workflow and emit done. Otherwise resolve to a `logical_id` from the anchor list.
2. **Detect current screen** via `DetectScreen`.
3. **Walk the graph.** If `screen_transitions` has a path current → target (with `exclude_destructive=true`), take it one step at a time via `TapMapped`. Each step's verb, target, args come from the recorded transition — don't invent them.
4. **No path? Recover via the home anchor.** Tap the Home bottom-nav item OR `appium_mobile_press_key key="BACK"` (cap 5). From `home`, re-detect and re-plan once.
5. **On match**, emit `next='done'` with `active_intent=intent_navigate_to_screen`.

## Failure handling

- **Loop detector trips** → `SaveEvidence(label=nav_loop)`, BACK out, terminate.
- **≥5 failures on one screen** → `SaveEvidence(label=nav_stuck)`, STOP.
- **No verified tap by step 5** → `SaveEvidence(label=nav_no_attempts)`, emit done. Don't fabricate success.

## Scope

Off-lobby + recovery navigation. No bets, no game launch, no financial actions, no logout. If you find yourself inside a game, BACK out to `home` before completing.
