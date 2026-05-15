"""BudgetCheck — pre-action budget gate for the play loop.

Per spec 005 T039 / FR-003 / FR-004 / FR-015. Evaluates the four bounds in
priority order and returns the first one that fires:

    1. balance_unparseable     - balance read failed too many times in a row
    2. budget_exhausted        - balance delta vs session-start ≤ -max_loss_usd
    3. n_spins                 - spins_played ≥ effective max_spins
    4. max_minutes             - elapsed minutes ≥ effective max_minutes

The env `MAX_LOSS_USD` is the HARD ceiling. A prompt-supplied loss budget is
silently capped to it (FR-003 — agent cannot raise its own bankroll cap). The
cap math lives in `shared/runtime_facts.py::lower_budget`; here we just
trust the values that arrive in `args` and decide whether to terminate.

Anti-hardcoding: nothing per-game. Round counts and timestamps are session
state passed in by the workflow. Bounds come from the SessionIntent.budget
envelope, which itself was clamped at parse time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


_TERMINAL_REASONS = {
    "budget_exhausted",
    "n_spins",
    "max_minutes",
    "balance_unparseable",
    "maintenance_observed",
}


def budget_check(args: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate the play-loop budget. Returns a decision dict.

    Args (passed from the workflow):
        balance_now:                   float | null — latest ReadBalance result
        balance_session_start:         float        — recorded at session start
        max_loss_usd:                  float        — already env-clamped
        max_spins:                     int          — effective bound
        max_minutes:                   int          — effective bound
        spins_played:                  int          — running count (workflow state)
        session_started_at_iso:        str          — ISO-8601 UTC
        balance_consecutive_failures:  int          — for `balance_unparseable`
        balance_failure_threshold:     int          — default 3

    Returns:
        {
            "terminal": null | str,                 # one of _TERMINAL_REASONS
            "should_continue": bool,
            "delta_usd": float | null,
            "spins_played": int,
            "elapsed_minutes": float,
            "details": str,                         # human-readable rationale
        }
    """
    balance_now = _safe_float(args.get("balance_now"))
    balance_session_start = _safe_float(args.get("balance_session_start"))
    max_loss_usd = _safe_float(args.get("max_loss_usd")) or 0.0
    max_spins = _safe_int(args.get("max_spins")) or 0
    max_minutes = _safe_int(args.get("max_minutes")) or 0
    spins_played = _safe_int(args.get("spins_played")) or 0

    bal_failures = _safe_int(args.get("balance_consecutive_failures")) or 0
    bal_fail_threshold = _safe_int(args.get("balance_failure_threshold")) or 3

    elapsed_minutes = _elapsed_minutes(args.get("session_started_at_iso"))

    # 1. ReadBalance has been failing repeatedly — hard stop, can't trust state.
    if bal_failures >= bal_fail_threshold:
        return _terminal(
            "balance_unparseable",
            details=f"balance read failed {bal_failures} times in a row "
            f"(threshold {bal_fail_threshold}); cannot evaluate budget safely",
            balance_now=balance_now,
            balance_session_start=balance_session_start,
            spins_played=spins_played,
            elapsed_minutes=elapsed_minutes,
        )

    # 2. Stop-loss. delta = current - start; loss is negative; terminal when
    #    -delta ≥ max_loss_usd (i.e. losses meet or exceed the cap).
    delta = None
    if balance_now is not None and balance_session_start is not None:
        delta = balance_now - balance_session_start
        if max_loss_usd > 0 and -delta >= max_loss_usd:
            return _terminal(
                "budget_exhausted",
                details=f"loss ${-delta:.2f} ≥ stop-loss ${max_loss_usd:.2f}",
                balance_now=balance_now,
                balance_session_start=balance_session_start,
                spins_played=spins_played,
                elapsed_minutes=elapsed_minutes,
                delta_usd=delta,
            )

    # 3. Round count.
    if max_spins > 0 and spins_played >= max_spins:
        return _terminal(
            "n_spins",
            details=f"spins_played {spins_played} ≥ max_spins {max_spins}",
            balance_now=balance_now,
            balance_session_start=balance_session_start,
            spins_played=spins_played,
            elapsed_minutes=elapsed_minutes,
            delta_usd=delta,
        )

    # 4. Wall-clock minutes.
    if max_minutes > 0 and elapsed_minutes >= max_minutes:
        return _terminal(
            "max_minutes",
            details=f"elapsed {elapsed_minutes:.1f}m ≥ max_minutes {max_minutes}",
            balance_now=balance_now,
            balance_session_start=balance_session_start,
            spins_played=spins_played,
            elapsed_minutes=elapsed_minutes,
            delta_usd=delta,
        )

    return {
        "terminal": None,
        "should_continue": True,
        "delta_usd": delta,
        "spins_played": spins_played,
        "elapsed_minutes": elapsed_minutes,
        "details": "within budget",
    }


# ── helpers ──


def _terminal(
    reason: str,
    *,
    details: str,
    balance_now: Optional[float],
    balance_session_start: Optional[float],
    spins_played: int,
    elapsed_minutes: float,
    delta_usd: Optional[float] = None,
) -> Dict[str, Any]:
    if reason not in _TERMINAL_REASONS:
        # Defensive: callers should never pass an unknown reason. Fall back to
        # the generic exhausted label rather than emit a string the planner
        # doesn't know about.
        reason = "budget_exhausted"
    return {
        "terminal": reason,
        "should_continue": False,
        "delta_usd": delta_usd,
        "spins_played": spins_played,
        "elapsed_minutes": elapsed_minutes,
        "details": details,
    }


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _elapsed_minutes(started_at_iso: Optional[str]) -> float:
    if not started_at_iso:
        return 0.0
    try:
        ts = datetime.fromisoformat(str(started_at_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 60.0)
