# Quickstart — Navigation Graph & Intent Layer

**Feature**: `004-nav-graph-intents`

A walkthrough of running a session end-to-end under the new architecture. Assumes the implementation in this plan has shipped.

## 1. Bring up the stack (unchanged from CLAUDE.md)

```bash
# Infrastructure
docker compose -f docker-compose.yml up temporal postgresql temporal-ui api frontend -d

# Persistent appium-mcp SSE server (PINNED 1.56.3)
ANDROID_HOME=$ANDROID_HOME npx -y appium-mcp@1.56.3 --httpStream --port=3100

# Android worker
PLATFORM=android ANDROID_HOME=$ANDROID_HOME uv run scripts/run_worker_android.py
```

The worker startup logs now include:

```
Observer framework: persona curiosity=high, jackpot_optin=True, max_loss=$5.0
Intent registry: 4 intents loaded (intent_authenticate, intent_navigate_to_screen, intent_play_game, intent_report)
Screen graph: 10+ transitions, 51+ signatures, 1+ games
Android worker ready to process tasks!
```

If any intent file fails validation, startup logs a warning and that intent is excluded from `allowed_intent_ids`. Other intents continue to load.

## 2. Issue a high-level prompt

```bash
curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=play+slingo+till+you+lose+$1'
```

Or send anything natural-language that names a session goal:

- `"log in and check the lobby"` — drives `intent_authenticate` → (no further intents fired) → `intent_report`
- `"play any slingo game for 5 minutes"` — drives `intent_authenticate` → `intent_navigate_to_screen` → `intent_play_game(time_bound)` → `intent_report`
- `"play whatever's most generous with FanCash today"` — same, but `intent_play_game` reads game_catalog ordered by FanCash multiplier

**No code change is required to handle a new prompt shape** (SC-011).

## 3. Watch the agent walk the graph

[Temporal UI](http://localhost:8080/namespaces/default/workflows/agent-workflow):

- The workflow's "Pending Activities" panel shows `agent_toolPlanner` calls returning `active_intent` per turn.
- New queries are queryable: `get_session_prompt`, `get_active_intent`, `get_completed_intents`.
- The workflow log shows `intent transition: <prev> -> <next>` lines whenever the LLM advances the active intent.

The worker log shows the deterministic-vs-LLM split:

```
intent transition: None -> intent_authenticate
SmartTap: lookup hit screen=app_launch, walking transition launch -> location_modal (conf=0.95, build=test)
record_transition_observation: from=app_launch verb=launch target=casino_app to=location_modal success=True
SmartTap: lookup hit screen=location_modal, walking transition tap[continue_button] -> system_permission_location
... (continues deterministically through the seeded path)
intent completed: intent_authenticate
intent transition: None -> intent_navigate_to_screen
SmartTap: lookup MISS for from=home target_signature=slingo_cash_eruption_loaded -- handing to LLM
agent_toolPlanner: planning lobby exploration toward slingo
... (LLM-reasoning path, recording new transitions as it succeeds)
record_transition_observation: from=home verb=tap target=slots_tab to=slots_category success=True (NEW EDGE)
... (continues until catalog hits or budget reached)
intent completed: intent_play_game
intent transition: None -> intent_report
... (writes session report)
session done.
```

## 4. Verify the report

`reports/2026-05-05-<workflow_run_id>.md` should contain:

- **Session prompt** verbatim
- **Intent timeline**: ordered list of `(intent_id, started_at, completed_at, screens_traversed)`
- **Top-of-report rollups** (FR-028 from feature 003): bug-severity and warn-severity observations from the run, with spec links and evidence paths
- **Auto-recorded transitions**: new edges this run added to the graph, ordered by hop
- **Catalog updates**: new game-catalog rows (if any), with `slug, name, category, loaded_signature`

## 5. Verify the graph grew

```bash
uv run python -c "
from shared.screen_map_db import ScreenMapDB
db = ScreenMapDB()
stats = db.get_stats()
print(f'Stats after run: {stats}')

# Peek at recently-recorded transitions
import json
conn = db._get_conn()
rows = conn.execute('''
    SELECT from_screen, intent_verb, intent_target, to_screen, confidence,
           times_used, times_succeeded, last_verified
    FROM screen_transitions
    ORDER BY last_verified DESC LIMIT 10
''').fetchall()
for r in rows:
    print(dict(r))
"
```

You should see `times_used` ≥ 1 on every transition the agent walked, with `last_verified` timestamps from this run.

## 6. Re-run and verify graduation

Run the same prompt a second time:

```bash
curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=play+slingo+till+you+lose+$1'
```

Watch for:

- LLM-reasoning calls drop (≥ 80% of transitions walk deterministically — SC-002).
- Some elements + transitions cross the LOW-RISK graduation threshold (`confidence ≥ 0.8`, `times_used ≥ 3`); their post-tap verification screenshots are skipped (Story 2 scenario 3).
- HIGH-RISK rows (sign_in_button, otp_submit, place_bet, etc.) keep their pre-graduation verification regardless of confidence.

## 7. Try a brand-new prompt shape

```bash
curl -s -X POST http://127.0.0.1:8000/start-workflow
curl -s -X POST 'http://127.0.0.1:8000/send-prompt?prompt=keep+playing+whatever+looks+interesting+for+10+minutes'
```

The agent should:

1. Pick `intent_authenticate` (login isn't optional)
2. Pick `intent_navigate_to_screen` toward the lobby
3. Pick `intent_play_game` with a time-bound exit condition derived from the prompt
4. Wrap with `intent_report`

**Zero code changes** to handle this shape — the LLM decomposes per turn from the prompt + intent registry (SC-011).

## 8. Drive an unknown screen and see a proposal

If the agent encounters a previously-unknown screen ≥ 3 times across runs:

```bash
uv run scripts/scan_signature_proposals.py
# Outputs:
# Proposal: signature_hash=unk:9ea6109f02ed0059...
#   occurrences: 4 across 3 runs
#   candidate_name: post_otp_loading_screen
#   top_text_signals: ["Loading...", "Just a moment"]
#   top_id_signals: ["loading_spinner", "progress_indicator"]
#   accept with: uv run scripts/accept_signature_proposal.py unk:9ea6109f02ed0059 --as post_otp_loading_screen
```

Accept moves the proposal into `screen_signatures`. Subsequent runs match the screen by name and contribute to path planning instead of firing `obs.unknown_screen`.

## What to look for if something goes wrong

| Symptom | Likely cause |
|---|---|
| Worker startup: "Intent registry: 0 intents loaded" | Missing or invalid frontmatter; check `intents/*.md` validation log |
| Workflow stalls without picking an intent | `active_intent` enum may be empty (registry didn't load); check planner LLM input |
| Agent loops between two screens | Path planner chose a high-confidence-but-wrong edge; check `screen_transitions` rows for that source screen |
| Tap succeeds but no transition recorded | SmartTap or VerifyTap try/except swallowed an error — grep worker log for `record_transition_observation: failed` |
| New build, agent ignores cached coords | Build-mismatch decay working as designed (R5); first run rediscovers + grows the new build's graph |
| `obs.unknown_screen` fires repeatedly on the same screen | The agent is encountering the same unmatched signature; run `scan_signature_proposals.py` and seed it |

## Smoke target for the implementation push

`scripts/smoke_play_intent.py` (NEW) should pass:

```bash
uv run scripts/smoke_play_intent.py --timeout 600 --prompt "play any slingo game till you lose $1"
# Exit 0 on:
#   - intent_authenticate completed
#   - intent_navigate_to_screen completed (slingo loaded screen reached)
#   - intent_play_game completed (budget bound hit OR session-seconds bound hit)
#   - intent_report completed
#   - 0 observer-side or auto-recorder-side halts (FR-027)
```
