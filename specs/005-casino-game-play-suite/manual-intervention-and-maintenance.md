# Manual intervention & maintenance — post-prod runbook

What a human still has to do after the agent is live. Everything here is by design (FR-022 forbids auto-promotion; budget/credential ops are intentionally out-of-band).

## Daily (≤10 min)

- **Triage `signature_proposals`**: `uv run scripts/scan_signature_proposals.py`. Accept real screens with `accept_signature_proposal.py <hash> --as <name>`; reject noise. Unaccepted proposals re-cost an LLM turn on next encounter.
- **Scan failed runs**: `reports/<date>-*.md` where `outcome=panic|stuck|budget_breach`. Open evidence/ for the run, file Jira if a real app bug, otherwise tag for retraining.
- **Check cost dashboard**: per-run input tokens trending up → working-memory compactor or prompt-cache likely broke.

## Weekly

- **Review CI report-diffs**: builds that added/removed transitions in known flows. Confirm intent (real product change vs. regression).
- **Confidence calibration**: query `screen_elements` rows graduated to deterministic-tap (>90% conf) with any failures in the last 7d. One failure on HIGH-tier should already reset; verify it did.
- **Animation-timing drift**: rows where `mean_ms` shifted >30% week-over-week. Often a build changed an animation; baselines need re-seeding for that game.
- **Account pool rotation**: cycle test accounts that hit RG cooldowns, KYC stale, or balance drained. The agent doesn't refill — ops does.
- **OTP source health**: static OTP for cert; for cert+/prod-spectator, verify the IMAP test-inbox listener is alive.

## Monthly

- **Build-env audit**: when app moves test → cert → prod, re-seed signatures for the new `build_env`. The decay rule (×0.5 on build mismatch) protects against silent reuse, but doesn't replace deliberate seeding.
- **Game catalog grooming**: mark deprecated games (`active=false`); add new releases with `kind`, `popularity`, `aliases_json`. The resolver's fuzzy match degrades quietly if aliases are stale.
- **Stale-row sweep**: rows untouched >90d → delete or re-verify. Prevents the DB from accumulating dead Android-only rows after iOS/web ship.
- **`game_kinds/<kind>.md` review**: regulators or game studios change rules; the per-kind KB is small enough to re-read in full.

## Per-release (app under test)

- **Re-seed if signature hashes shift**: a UI refresh changes hashes even when behavior is identical. Run `seed_login_signatures.py` and the equivalent for any locked flows; don't wait for the agent to discover.
- **Smoke before regression**: `uv run scripts/smoke_login.py` and `smoke_play_intent.py` against the new build. Failures here are blockers — don't run the broader suite over a broken floor.
- **Tool-list drift**: if `appium-mcp` is bumped, verify pinned version (1.56.3) hasn't been overridden; tool names break silently on 1.57+.

## Per-incident (the agent gets stuck)

1. Open the Temporal UI (`localhost:8080`) workflow history; identify the last successful `screen_signature`.
2. Pull `evidence/<run>/` — page-source XML + screenshot at the stuck point.
3. Decide: (a) real app bug → file Jira, mark intent attempt as expected-fail; (b) novel screen → accept its proposal; (c) selector drift → re-seed element with corrected coords.
4. **Never** edit the DB to "fix" a run in flight. Terminate the workflow, fix the data, restart.

## Credentials, budget, jurisdiction

- `MAX_LOSS_USD` — env var, owned by whoever launches the worker. The agent reads, never writes. **Hard ceiling**: a prompt-supplied budget can only *lower* this number; never raise it. Vague prompts also get default `max_spins=20` and `max_minutes=10` bounds (first terminal wins) so an accidental `"play X"` cannot drain the full env budget.
- Test-account credentials — secret store; rotated on a quarterly cadence by ops, not by the agent.
- New jurisdiction (e.g., adding ON or MA) — drop a manifest under `compliance/<reg>/`, add to `RuntimeFacts.jurisdiction` allowlist. Manual one-time per region.

## What the agent will NEVER do for itself (by design)

- Promote `signature_proposals` (FR-022).
- Refill or rotate accounts.
- Raise its own `MAX_LOSS_USD`.
- Re-seed signatures after a UI refresh.
- Decide a transition is a regression vs. an intentional product change.
- Push to prod, change feature flags, or modify CI gates.

These are the load-bearing human checkpoints. Everything else self-heals or self-improves.
