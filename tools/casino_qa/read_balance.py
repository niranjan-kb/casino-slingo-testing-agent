"""ReadBalance — extract the wallet balance from page-source via the
per-game playbook's signature + regex.

Per spec 005 T038 / FR-009 / gaps-and-guardrails §A5. Bounded retry budget
(`min(3, ceil(1/balance_read_confidence))` per gap A5). Failure is silent to
the goal loop (Constitution III) but bumps a `balance_consecutive_failures`
counter that the workflow threads into BudgetCheck — three failures in a row
trip the `balance_unparseable` terminal there.

Anti-hardcoding: NO regex patterns live in this file. The regex is per-game
in `game_playbook.balance_regex`; it's discovered first-time during play
(initially empty → LLM fallback for the very first balance read), then
auto-populated. The `balance_signature` is also per-game.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

from ._deps import get_screen_db


def read_balance(args: Dict[str, Any]) -> Dict[str, Any]:
    """Extract balance from a page-source dump.

    Args (passed by the planner):
        page_source:                  str  — the appium_get_page_source result
        slug:                         str  — game_directory.slug for playbook lookup
        balance_regex_override:       str? — optional override (rare; ops only)
        balance_signature_override:   str? — optional override
        balance_read_confidence:      float? — for retry budget; default 1.0

    Returns:
        {
            "found": bool,
            "balance_usd": float | null,
            "raw_match": str | null,         # the matched substring (for evidence)
            "regex_used": str | null,
            "retry_budget": int,             # min(3, ceil(1/conf))
            "reason": "found" | "no_page_source" | "no_playbook" |
                      "no_regex" | "regex_no_match" | "parse_failed",
        }
    """
    page_source = args.get("page_source") or ""
    slug = (args.get("slug") or "").strip()
    regex_override = args.get("balance_regex_override")

    if not page_source:
        return _miss("no_page_source", retry_budget=_retry_budget(args))

    regex = regex_override
    if not regex and slug:
        regex = _lookup_balance_regex(slug)

    if not regex:
        # First-time encounter: planner should fall back to LLM/OCR to derive a
        # regex; once derived, it's persisted by the auto-recorder. Until then,
        # this tool returns no_regex and the play loop knows to defer.
        return _miss("no_regex", retry_budget=_retry_budget(args))

    try:
        match = re.search(regex, page_source)
    except re.error:
        return _miss("parse_failed", retry_budget=_retry_budget(args), regex_used=regex)

    if not match:
        return _miss("regex_no_match", retry_budget=_retry_budget(args), regex_used=regex)

    raw = match.group(1) if match.groups() else match.group(0)
    balance = _parse_amount(raw)
    if balance is None:
        return _miss(
            "parse_failed",
            retry_budget=_retry_budget(args),
            regex_used=regex,
            raw_match=raw,
        )

    return {
        "found": True,
        "balance_usd": balance,
        "raw_match": raw,
        "regex_used": regex,
        "retry_budget": _retry_budget(args),
        "reason": "found",
    }


# ── helpers ──


def _lookup_balance_regex(slug: str) -> Optional[str]:
    """Read game_playbook.balance_regex for a slug. None if no row or unset."""
    db = get_screen_db()
    if db is None:
        return None
    try:
        row = db._get_conn().execute(
            "SELECT balance_regex FROM game_playbook WHERE slug = ?",
            (slug,),
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return row["balance_regex"] or None


def _parse_amount(raw: str) -> Optional[float]:
    """Strip thousands separators and currency symbols; return float or None.

    Accepts $1,234.56 / 1234.56 / 1.234,56 (European). Anti-locale-hardcoding:
    we infer separator role from position, not from a hard rule.
    """
    if not raw:
        return None
    s = str(raw).strip()
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s:
        return None
    # If the last separator is '.', treat ',' as thousands; if last is ',',
    # treat '.' as thousands (European). If only one of them appears, drop it
    # only when it looks like a thousands separator (3 trailing digits).
    last_dot = s.rfind(".")
    last_comma = s.rfind(",")
    if last_dot != -1 and last_comma != -1:
        if last_dot > last_comma:
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif last_comma != -1:
        # Only commas: thousands if followed by exactly 3 digits, else decimal.
        if re.fullmatch(r"-?\d+,\d{3}(?:,\d{3})*", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _retry_budget(args: Dict[str, Any]) -> int:
    raw = args.get("balance_read_confidence")
    try:
        conf = float(raw) if raw is not None else 1.0
    except (TypeError, ValueError):
        conf = 1.0
    if conf <= 0:
        return 3
    return min(3, max(1, math.ceil(1.0 / conf)))


def _miss(
    reason: str,
    *,
    retry_budget: int,
    regex_used: Optional[str] = None,
    raw_match: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "found": False,
        "balance_usd": None,
        "raw_match": raw_match,
        "regex_used": regex_used,
        "retry_budget": retry_budget,
        "reason": reason,
    }
