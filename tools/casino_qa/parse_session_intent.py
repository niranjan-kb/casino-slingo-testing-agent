"""ParseSessionIntent — translate the operator's free-text prompt into a
structured SessionIntent envelope.

Per spec 005 T036 / contracts/session_intent.schema.json. The output shape:

    {flow, target?: {kind, query, slug}, budget: {max_loss_usd, max_spins?,
     max_minutes?}, terminal}

This implementation is deliberately heuristic-first: most operator prompts
are short and direct ("play slingo", "play fanatics spin to win for 5
minutes") and a regex-driven extractor handles them deterministically.
LLM fallback is reserved for prompts the heuristic cannot classify
(currently a no-op stub — falls back to flow=report_only).

Hard-ceiling rule (FR-003 / FR-004): MAX_LOSS_USD env is the cap.
A prompt-supplied loss budget is silently lowered to env, never raised.
Vague prompts get default `max_spins=20` AND `max_minutes=10` AND
env loss ceiling — first-of-many semantics.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple


# Per CLAUDE.md / spec assumptions, kinds are a closed set. Adding a new kind
# is hand-authored (game_kinds/<kind>.md) and gets reflected here.
_KIND_KEYWORDS = {
    "slingo": ("slingo",),
    "slots": ("slot", "slots", "spin to win", "video slot"),
    "blackjack": ("blackjack", "bj", "21", "twenty-one", "twenty one"),
    "roulette": ("roulette", "wheel"),
    "live_dealer": ("live dealer", "live blackjack", "live roulette"),
}

_FLOW_KEYWORDS = {
    "play": ("play", "spin", "bet"),
    "navigate": ("navigate", "open", "go to", "find"),
    "audit": (
        "audit", "look around", "explore", "scout",
        "tell me what changed", "what's new", "whats new", "what has changed",
    ),
    "observe": ("watch", "observe"),
    "report_only": ("report", "summarise", "summarize"),
}

# Default bounds for vague prompts (FR-004). Env-overridable so test runs can
# tighten without code changes.
_DEFAULT_MAX_SPINS = int(os.getenv("DEFAULT_MAX_SPINS", "20"))
_DEFAULT_MAX_MINUTES = int(os.getenv("DEFAULT_MAX_MINUTES", "10"))


def parse_session_intent(args: Dict[str, Any]) -> Dict[str, Any]:
    """Compile a free-text prompt to a SessionIntent dict.

    Args:
        prompt:           str — the operator's free-text ask
        env_max_loss_usd: float — env hard ceiling (override; defaults to MAX_LOSS_USD)

    Returns:
        SessionIntent dict per contracts/session_intent.schema.json,
        plus the pair (`requested_max_loss_usd`, `effective_max_loss_usd`)
        so the run report can show the cap math.
    """
    prompt = (args.get("prompt") or "").strip()

    env_cap = _safe_float(args.get("env_max_loss_usd"))
    if env_cap is None:
        env_cap = _safe_float(os.getenv("MAX_LOSS_USD"))
    env_cap = env_cap if env_cap is not None else 10.0

    if not prompt:
        return _envelope(
            flow="report_only",
            target=None,
            budget=_default_budget(env_cap),
            terminal="report",
            env_cap=env_cap,
            requested_max_loss=None,
            reason="empty_prompt",
        )

    lower = prompt.lower()

    flow = _detect_flow(lower)
    target = _detect_target(prompt, lower)
    requested_loss, max_spins, max_minutes = _extract_bounds(lower)

    # Apply hard ceiling: prompt can only LOWER, never RAISE.
    if requested_loss is None:
        effective_loss = env_cap
    else:
        effective_loss = min(env_cap, requested_loss)

    # Default bounds if not specified (FR-004).
    if max_spins is None:
        max_spins = _DEFAULT_MAX_SPINS
    if max_minutes is None:
        max_minutes = _DEFAULT_MAX_MINUTES

    # Terminal classification: stricter prompt-supplied bound wins, else
    # default to the first-of-many semantics with budget_exhausted as the
    # canonical fallback.
    if "spin" in lower and re.search(r"\b\d+\s*spins?\b", lower):
        terminal = "n_spins"
    elif "minute" in lower and re.search(r"\b\d+\s*(min|minute|mins|minutes)\b", lower):
        terminal = "max_minutes"
    elif flow == "play":
        terminal = "budget_exhausted"
    elif flow in ("audit", "report_only", "observe"):
        terminal = "report"
    else:
        terminal = "budget_exhausted"

    return _envelope(
        flow=flow,
        target=target,
        budget={
            "max_loss_usd": effective_loss,
            "max_spins": max_spins,
            "max_minutes": max_minutes,
        },
        terminal=terminal,
        env_cap=env_cap,
        requested_max_loss=requested_loss,
        reason="parsed",
    )


# ── extractors ──


def _detect_flow(lower: str) -> str:
    """Pick the flow whose keyword has the LONGEST match in the prompt.

    Longest-match resolves ambiguity in operator phrasings: "open the lobby and
    look around" should hit `audit` (via "look around"), not `navigate` (via
    "open"). Ties broken by specificity score: audit/observe > navigate >
    play > report_only — i.e. the more specific intent wins on equal length.
    """
    specificity = {"observe": 4, "audit": 3, "report_only": 2, "navigate": 1, "play": 0}
    best_flow: Optional[str] = None
    best_len = 0
    best_specificity = -1
    for flow, kws in _FLOW_KEYWORDS.items():
        for kw in kws:
            if kw not in lower:
                continue
            kw_len = len(kw)
            kw_spec = specificity.get(flow, 0)
            if kw_len > best_len or (
                kw_len == best_len and kw_spec > best_specificity
            ):
                best_flow = flow
                best_len = kw_len
                best_specificity = kw_spec
    if best_flow:
        return best_flow
    # No verb at all: default to play. The downstream resolver / nav layer
    # will fail visibly if this turns out to be wrong; safer than guessing
    # "report_only" and skipping the work the operator probably wanted.
    return "play"


def _detect_target(prompt: str, lower: str) -> Optional[Dict[str, Any]]:
    """Pull `kind` and a query string from the prompt.

    Strategy:
        1. Pick the kind whose keyword has the LONGEST match in the prompt
           (so "live blackjack" beats "blackjack").
        2. Build the query from the prompt minus boilerplate ("play", "for X",
           "$Y loss", etc.). This becomes the resolver's free-text input.
    """
    kind: Optional[str] = None
    best_match_len = 0
    for k, kws in _KIND_KEYWORDS.items():
        for kw in kws:
            if kw in lower and len(kw) > best_match_len:
                kind = k
                best_match_len = len(kw)

    # Strip boilerplate from the prompt to get a clean resolver query.
    query = prompt
    for verb_set in _FLOW_KEYWORDS.values():
        for kw in verb_set:
            query = re.sub(rf"\b{re.escape(kw)}\b", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\bfor\s+\d+\s*(min|minute|mins|minutes|spins?|hours?)\b", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\$\s*\d+(\.\d+)?\s*(loss|max|cap|limit)?", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\b\d+\s*(spins?|minutes?|mins?)\b", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" .,!?:")

    if not kind and not query:
        return None

    target: Dict[str, Any] = {}
    if kind:
        target["kind"] = kind
    if query:
        target["query"] = query
    return target


_NUM_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")


def _extract_bounds(lower: str) -> Tuple[Optional[float], Optional[int], Optional[int]]:
    """Pull the three numeric bounds from the prompt.

    Returns (requested_max_loss_usd, max_spins, max_minutes). Any may be None.
    """
    requested_loss: Optional[float] = None
    max_spins: Optional[int] = None
    max_minutes: Optional[int] = None

    # `lose $X`, `$X loss`, `$X max`, `up to $X`
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)\b", lower)
    if m:
        try:
            requested_loss = float(m.group(1))
        except ValueError:
            pass

    # `5 spins`, `for 5 spins`, `for 5 minutes`
    m = re.search(r"\b(\d+)\s*spins?\b", lower)
    if m:
        max_spins = int(m.group(1))
    m = re.search(r"\b(\d+)\s*(?:min|minute|mins|minutes)\b", lower)
    if m:
        max_minutes = int(m.group(1))
    m = re.search(r"\b(\d+)\s*hours?\b", lower)
    if m:
        max_minutes = int(m.group(1)) * 60

    return requested_loss, max_spins, max_minutes


# ── envelope ──


def _default_budget(env_cap: float) -> Dict[str, Any]:
    return {
        "max_loss_usd": env_cap,
        "max_spins": _DEFAULT_MAX_SPINS,
        "max_minutes": _DEFAULT_MAX_MINUTES,
    }


def _envelope(
    *,
    flow: str,
    target: Optional[Dict[str, Any]],
    budget: Dict[str, Any],
    terminal: str,
    env_cap: float,
    requested_max_loss: Optional[float],
    reason: str,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "flow": flow,
        "budget": budget,
        "terminal": terminal,
        # Audit fields kept alongside the SessionIntent shape so the report
        # can show "operator asked for $50, capped to $10". Workflow stores
        # the SessionIntent itself (matching the contract); the audit fields
        # are surfaced separately in the report.
        "_meta": {
            "env_max_loss_usd": env_cap,
            "requested_max_loss_usd": requested_max_loss,
            "effective_max_loss_usd": budget["max_loss_usd"],
            "reason": reason,
        },
    }
    if target:
        out["target"] = target
    return out


def _safe_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
