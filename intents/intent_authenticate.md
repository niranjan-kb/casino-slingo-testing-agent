---
id: intent_authenticate
end_state_signatures:
  - home
  - home_lobby
success_check: "balance text visible OR header logo visible AND no auth screens (email/password/otp) on top"
guardrails:
  - "never echo password or OTP in user-facing responses"
  - "OTP follows OTP_POLICY: AUTO-OTP in test/dev (use {{DEFAULT_OTP}}); ASK-USER-OTP only in cert/prod"
  - "≥3 failed strategies on one screen → SaveEvidence and continue with a different selector"
  - "≥5 failures on one screen → SaveEvidence and STOP — do not loop forever"
risk_tier: HIGH
notes: "Locked verified flow on Pixel 9 Pro test build, 2026-04-29."
---

# intent_authenticate

You are authenticating the casino app. Reach a logged-in home/lobby screen. When you see balance text and the header logo with no auth screens overlaid, you are done — emit `next='done'` with `active_intent=intent_authenticate`.

## How to proceed

1. Detect the current screen (DetectScreen).
2. If the screen is known and a path exists from current → an `end_state_signatures` entry, walk the path one step at a time using SmartTap. Each step's verb, target, and args come from the recorded transition; you do not invent them.
3. If no path exists or the current screen is unknown, read the page-source and reason from it toward the end-state. Use FindElementWithFallback for raw element lookup; SmartTap for tap-and-verify; TapCoordinate as the last-resort coord fallback. Auto-record fires automatically — you do not need to record manually.
4. When the success_check is satisfied, emit `next='done'` with `active_intent=intent_authenticate`. The workflow will mark this intent complete and prompt you to pick the next active_intent.

## Scope

Authentication only. Do not navigate further than a logged-in lobby — the next intent will pick up from there. If you find yourself in a deeper section of the app (a game, settings), back out to home and then mark complete.
