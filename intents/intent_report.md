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
notes: "Wraps tools/slingo_qa/generate_report.py as a goal-level intent."
---

# intent_report

You are writing the session report. This intent runs after all other intents have been completed (or the session has timed out). It is the natural terminator of a session.

## How to proceed

1. Call `GenerateReport` with the run_id, session_prompt, and the workflow's `completed_intents` list. The report writer pulls observations, transitions, and catalog updates from the DB itself — you do not need to pass them in.
2. The writer produces `reports/YYYY-MM-DD-<run_id>.md` with:
   - Session prompt verbatim
   - Intent timeline (id, started, completed, screens traversed)
   - Bug- and warn-severity rollups from observation_log
   - New transitions and catalog rows added this run
3. Emit `next='done'` with `active_intent=intent_report`. The workflow will treat this as session-level done (no further intents) and end gracefully.

## Scope

Reporting only. Do not navigate, do not play. If you find yourself on a non-lobby screen at the start of this intent, do not navigate back — the report writer is screen-agnostic.
