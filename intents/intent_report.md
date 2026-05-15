---
id: intent_report
end_state_signatures:
  - home
  - home_lobby
success_check: "a markdown report has been written to reports/YYYY-MM-DD-<run_id>.md AND the agent has emitted next='done' with active_intent=intent_report"
guardrails:
  - "never echo password, OTP, or session tokens into the report"
  - "if the report writer fails (disk error, permission denied), log a warn observation and continue — do not loop"
  - "the report is the LAST intent in a session — do not start a new intent after it"
risk_tier: LOW
notes: "Wraps tools/casino_qa/generate_report.py as a goal-level intent."
---

# intent_report

You are writing the session report. This intent runs after all other intents have been completed (or the session has timed out). It is the natural terminator of a session.

## How to proceed — in this strict order

1. **You MUST call `GenerateReport` first.** Pass at minimum: `workflow_id`, `terminal_reason`, `started_at`, `ended_at`, plus `balance` (start/end/delta/max_loss_*) and `intents` (per-intent telemetry) when known. The writer pulls `rounds` and `transitions_added` from the DB on its own — do not pass them in. Emitting `next='done'` BEFORE this call is a contract violation that produces a session with no report on disk.
2. The writer produces BOTH `reports/<date>-<workflow_id>.json` (per the run_report contract) AND a markdown sibling.
3. Only AFTER `GenerateReport` returns successfully, emit `next='done'` with `active_intent=intent_report`. The workflow treats this as session-level done and ends gracefully.

## Scope

Reporting only. Do not navigate, do not play. If you find yourself on a non-lobby screen at the start of this intent, do not navigate back — the report writer is screen-agnostic.
