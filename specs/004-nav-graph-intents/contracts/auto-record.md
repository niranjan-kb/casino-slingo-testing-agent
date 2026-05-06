# Contract — Auto-Record Writeback

Three localized hooks in `tools/slingo_qa/` (NOT frozen by WF-3) that grow the screen-map every run.

## SmartTap → screen_transitions (FR-017, MW-1)

**Owner**: `tools/slingo_qa/smart_tap.py`

After a successful tap-and-verify, SmartTap calls:

```python
screen_db.record_transition_observation(
    from_screen=before_screen,                  # captured before the tap
    intent_verb=verb,                           # e.g. "tap" or composite verb from intent
    intent_target=element_name,                 # e.g. "continue_button"
    intent_args=args_or_None,                   # extra args (text typed, key pressed)
    to_screen=verified_after_screen,            # what VerifyTap actually saw
    success=True,                               # always True if VerifyTap returned ok
    app_context=app_context,
)
```

When `verified_after_screen != expected_after_screen` (verified divergence — Story 1 scenario 2):

```python
# 1. Decrement confidence on the assumed (and now wrong) edge
screen_db.record_transition_observation(
    from_screen=before_screen,
    intent_verb=verb,
    intent_target=element_name,
    intent_args=args_or_None,
    to_screen=expected_after_screen,            # the wrong destination
    success=False,
    app_context=app_context,
)
# 2. Upsert the actual edge
screen_db.record_transition_observation(
    from_screen=before_screen,
    intent_verb=verb,
    intent_target=element_name,
    intent_args=args_or_None,
    to_screen=verified_after_screen,            # what really happened
    success=True,
    app_context=app_context,
)
```

**Failure tolerance**: each call is wrapped in try/except. Any DB write error logs a warn observation via the observer pipeline and continues. SmartTap does NOT raise (FR-027).

## VerifyTap return shape (FR-018)

**Owner**: `tools/slingo_qa/verify_tap.py`

Existing return shape gets two new optional fields:

```python
{
  "verified": bool,
  "expected_screen": str,
  "actual_screen": str,                         # NEW (previously implicit)
  "from_screen": str,                           # NEW — captured at tap time, plumbed for recording
  "tap_x": int,
  "tap_y": int,
  ...                                           # existing fields unchanged
}
```

Existing callers ignoring `from_screen` / `actual_screen` continue to work. SmartTap is the only caller that needs to read them.

## FindElementWithFallback → screen_elements (FR-019, MW-2)

**Owner**: `tools/slingo_qa/find_element_with_fallback.py`

On hit (any candidate matches), call:

```python
device_profile_id = ensure_device_profile()
screen_db.upsert_element(
    device_profile_id=device_profile_id,
    app_context=app_context,
    screen_name=current_screen,                 # from caller's intent context
    element_name=intent_target_label,           # e.g. "email_field" — from caller
    x=center_x,                                 # from element bounds
    y=center_y,
    element_type=None,                          # optional
    intent=None,                                # optional
    confidence=0.6,                             # initial; bumped by record_tap_result
    source="element",
)
```

When `intent_target_label` is not provided (raw exploration), use the matched candidate's `f"{strategy}:{selector}"` as the fallback label (FR-020). The label can be renamed later by a subsequent intent-context-aware call.

**Failure tolerance**: try/except around the call; failures log + continue. Tool's user-facing return is unchanged.

## Confidence updates

The existing methods continue to govern confidence:

- `screen_db.record_tap_result(device, screen, element, success)` — bumps element confidence on verified taps. Already called by VerifyTap today.
- `screen_db.record_transition_observation(..., success)` — bumps transition confidence on verified transitions. NEW call site (this contract).

Risk-tier graduation policy in `should_verify_tap` is unchanged: HIGH-RISK never graduates, MEDIUM at 0.9 conf + 5 uses, LOW at 0.8 + 3 uses.

## Build-aware writes (R6, MW-3)

All three writeback paths set `build_env` and `app_package` from the worker's `os.environ` at write time:

```python
build_env = os.getenv("BUILD_ENV", "unknown")
app_package = os.getenv("APP_PACKAGE", "unknown")
```

These columns are added to `screen_signatures`, `screen_elements`, `screen_transitions`. Read-time decay (R5) compares the row's stored values to the current env; mismatch multiplies effective confidence by 0.5.

## What MUST NOT happen in auto-record (FR-027)

- ❌ Raise an exception that propagates to the workflow — all writes are try/except.
- ❌ Block on network or file I/O beyond the local SQLite write.
- ❌ Modify workflow state directly — auto-record is purely DB writes; workflow state is touched only via `@workflow.query` reads.
- ❌ Trigger more than one DB write per tool call (per write call) — keeps replay cost predictable.
