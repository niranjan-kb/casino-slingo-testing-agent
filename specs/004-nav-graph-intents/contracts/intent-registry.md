# Contract — Intent Registry

**Owner**: `intents/__init__.py`

## File layout

```
intents/
├── __init__.py                  # registry loader, frontmatter parser
├── base.py                      # IntentDeclaration dataclass
├── authenticate.md
├── navigate_to_screen.md
├── play_game.md
└── report.md
```

## File format — `intents/<id>.md`

YAML frontmatter + markdown body.

```markdown
---
id: intent_authenticate                  # unique; matches filename stem
end_state_signatures:
  - home
  - home_lobby
success_check: "balance text visible OR header logo visible"
guardrails:
  - "never echo password or OTP in user-facing responses"
  - "OTP follows OTP_POLICY (AUTO-OTP in test/dev, ASK-USER-OTP in cert/prod)"
risk_tier: HIGH                          # HIGH | MEDIUM | LOW
notes: "Optional free-form notes for human readers."
---

# intent_authenticate

You are completing the casino-app authentication flow. Reach a logged-in
home/lobby screen.

## How to proceed

1. Read the current screen via the screen-map (DetectScreen). If matched
   and a path exists from current → end_state_signatures, walk the path
   step-by-step using SmartTap / FindElementWithFallback.
2. If no path exists or the screen is unknown, reason from the page-source
   toward an end_state_signature. Auto-record observations as you go.
3. When the success_check is satisfied, emit next='done' with active_intent
   still set to intent_authenticate. The workflow will mark the intent
   complete and pick the next intent on the following turn.

## Guardrails

- never echo password or OTP in user-facing responses
- OTP_POLICY governs how OTP is sourced
- ≥3 failed strategies on one intent → SaveEvidence + continue
- ≥5 failures on one screen → SaveEvidence + STOP
```

## Validation rules (enforced at startup by `load_registry`)

- `id` MUST be present and MUST match the filename stem.
- `id` MUST be unique across all loaded files.
- `id` MUST start with `intent_`.
- `end_state_signatures` MUST be a non-empty list of strings.
- Each `end_state_signatures` entry SHOULD exist in `screen_signatures.screen_name` — startup logs a warning if not, but does not fail.
- `success_check` MUST be a non-empty string.
- `guardrails` MAY be empty.
- `risk_tier` MUST be one of `HIGH`, `MEDIUM`, `LOW`.
- Markdown body length MUST be ≤ 600 tokens (~2400 chars). Enforced at startup; over-budget files log a warning per SC-012.

## API

```python
# intents/base.py
from dataclasses import dataclass, field
from typing import List, Literal, Optional

@dataclass
class IntentDeclaration:
    id: str
    end_state_signatures: List[str]
    success_check: str
    guardrails: List[str] = field(default_factory=list)
    risk_tier: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    notes: Optional[str] = None
    body_md: str = ""                    # markdown body (the LLM-facing prose)
    body_token_estimate: int = 0          # rough estimate (chars / 4)

# intents/__init__.py
def load_registry(intents_dir: Optional[str] = None) -> dict[str, IntentDeclaration]:
    """Load all intent files at startup. Idempotent.

    Returns: dict keyed by intent id.
    Raises: ValueError if any file has invalid frontmatter or duplicate id.
    """
```

## Adding a new intent

Three steps. **No code changes required.**

1. Drop a new file `intents/<new_id>.md` with frontmatter + body ≤ 600 tokens.
2. Restart the worker (registry loads at worker startup).
3. The intent is now in `allowed_intent_ids` for the planner; the LLM may pick it on subsequent turns.

To remove an intent: delete the file. To temporarily disable: rename to `intents/_disabled_<id>.md` (the loader skips files prefixed with `_`).

## What MUST NOT appear in an intent body (Principle VI)

- ❌ Selector strings (xpath, resource-ids, accessibility-ids)
- ❌ Fallback candidate lists
- ❌ Wait-time tables ("after a tap, wait 2 seconds")
- ❌ Per-screen procedural phases ("Phase 2a — type email")
- ❌ Tool argument specs already documented in tools/tools.md

The intent body declares **what end-state to reach** and **how to know you're there**. The screen graph + tool catalog handle the how.
