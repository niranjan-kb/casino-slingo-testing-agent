"""Screen graph — path planning over `screen_transitions`.

Given a start screen and a target screen, find the shortest sequence of
transitions the agent should execute. Returns None when no path is known —
caller hands off to LLM reasoning (and the agent's eventual success will
record a new transition that grows the graph).

This module is the runtime counterpart to the seeded login flow markdown.
The phase-by-phase procedure in goals/casino_session/prompts/user.md becomes data
in screen_transitions; the agent walks the graph instead of reading prose.
"""

from __future__ import annotations

import heapq
import itertools
import json
import os
from collections import deque
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Set


# ── Spec 005 additions ──────────────────────────────────────────────────
#
# Three additive extensions per plan.md Phase 2 T021–T023:
#   T021: per-surface decay. _effective_confidence now consults a
#         screen_signatures.staleness_days override when set; falls back to
#         SCREEN_MAP_STALENESS_DAYS env. Legacy callers unaffected.
#   T022: stochastic outcomes. New helpers (`outcomes_for`, `top_outcome`,
#         `distribution_shift`) read from the transition_outcomes table —
#         parallel to find_path, used by report-diff and per-action
#         distribution checks. find_path itself unchanged.
#   T023: edge_kind / side_effect / precondition filtering. find_path /
#         all_reachable now accept optional filters; defaults preserve
#         legacy behavior. Destructive edges blacklisted from explore mode
#         by default.
#
# Anti-hardcoding mandate: nothing per-game in here. Filters take RuntimeFacts
# and edge metadata from the DB; no per-jurisdiction or per-build logic.

# Edges that mutate financial or account state. Maintained as a small,
# explicit list because the agent's safety depends on exact match — these
# verbs (the existing intent_verb shape from spec 004) trigger destructive
# operations regardless of confidence. Compared as a substring check on
# intent_verb so e.g. "deposit_submit", "deposit_confirm_v2" all blacklist.
_DESTRUCTIVE_VERB_FRAGMENTS: FrozenSet[str] = frozenset(
    {
        "deposit_submit",
        "deposit_confirm",
        "withdraw_submit",
        "withdraw_confirm",
        "kyc_submit",
        "account_close",
        "account_self_exclude",
        "promo_redeem",
        "fancash_convert",
    }
)


def _is_destructive_edge(row: Mapping[str, Any]) -> bool:
    """Classify an edge by side effect. Reads `side_effect` if present (new
    schema), else infers from intent_verb against a blocklist."""
    side_effect = row.get("side_effect")
    if side_effect:
        return side_effect == "destructive"
    verb = (row.get("intent_verb") or "").lower()
    return any(frag in verb for frag in _DESTRUCTIVE_VERB_FRAGMENTS)


def _days_between(iso_ts: Optional[str], now: Optional[datetime] = None) -> float:
    """Days between an ISO timestamp string and `now` (utc).

    Returns 0.0 on parse failure or when `iso_ts` is None — i.e. unknown
    staleness is treated as fresh (no penalty), matching MW-3's read-only
    posture: we never destructively penalize rows we can't date.
    """
    if not iso_ts:
        return 0.0
    try:
        ts = datetime.fromisoformat(iso_ts)
    except (TypeError, ValueError):
        return 0.0
    base = now or datetime.utcnow()
    return max(0.0, (base - ts).total_seconds() / 86400.0)


def _effective_confidence(
    row: Dict[str, Any],
    *,
    current_build_env: Optional[str] = None,
    current_app_package: Optional[str] = None,
    staleness_days_window: int = 30,
    now: Optional[datetime] = None,
) -> float:
    """Compute read-time-decayed confidence (MW-3, R5/R6).

    Stored confidence is never modified. Build/package mismatch multiplies
    by 0.5; rows older than the staleness window get a soft linear ramp
    (floor 0.5) until 90 days post-window.

    Per-surface decay (spec 005 T021): callers may pass a per-surface
    `staleness_days_window` derived from `screen_signatures.staleness_days`
    via `_load_staleness_overrides()`. Without that, the env default is used
    (`SCREEN_MAP_STALENESS_DAYS=30`).
    """
    conf = float(row.get("confidence") or 0.0)
    row_env = row.get("build_env") or "unknown"
    row_pkg = row.get("app_package") or "unknown"
    if current_build_env and row_env not in (current_build_env, "unknown"):
        conf *= 0.5
    if current_app_package and row_pkg not in (current_app_package, "unknown"):
        conf *= 0.5
    last_verified = row.get("last_verified")
    days_stale = _days_between(last_verified, now=now)
    if days_stale > staleness_days_window:
        ramp = max(0.5, 1.0 - (days_stale - staleness_days_window) / 60.0)
        conf *= ramp
    return conf


def _load_staleness_overrides(db: Any) -> Dict[str, int]:
    """Load screen_name → staleness_days overrides from screen_signatures.

    Only rows where staleness_days is non-NULL are returned. Per research §R4
    the intended defaults are: auth/kyc/settings = 90d; in-game stable = 60d;
    lobby = 14d; promo banners = 7d. The values are operator-set on
    promotion (accept_signature_proposal --staleness-days N), so this lookup
    yields whatever the human curated.

    Failures are swallowed — a missing override falls back to the env default
    `SCREEN_MAP_STALENESS_DAYS` per Constitution III (observers never halt).
    """
    try:
        rows = db._get_conn().execute(
            "SELECT screen_name, staleness_days FROM screen_signatures "
            "WHERE staleness_days IS NOT NULL"
        ).fetchall()
        return {r["screen_name"]: int(r["staleness_days"]) for r in rows}
    except Exception:
        return {}


def _decayed_transitions_from(
    db: Any,
    from_screen: str,
    *,
    app_context: str,
    staleness_overrides: Optional[Mapping[str, int]] = None,
    exclude_destructive: bool = False,
    allowed_intent_verbs: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Wrapper around db.get_transitions_from that applies read-time decay.

    Returns rows with their `confidence` field replaced by the decayed value;
    the original confidence is preserved as `_stored_confidence` for callers
    that want it. Sorted by decayed confidence descending so callers that
    pick the top row continue to behave as before.

    Per-surface decay (T021): when `staleness_overrides` is provided, each
    row's window comes from the override map (keyed by from_screen) before
    falling back to the env default.

    Edge filtering (T023): `exclude_destructive` blocks edges classified as
    destructive (deposit/withdraw/kyc-submit/account-close/...). The default
    is False to preserve legacy callers — explore mode passes True.
    `allowed_intent_verbs` restricts to a verb whitelist (None = all).
    """
    build_env = os.getenv("BUILD_ENV") or None
    app_package = os.getenv("APP_PACKAGE") or None
    try:
        default_window = int(os.getenv("SCREEN_MAP_STALENESS_DAYS", "30"))
    except (TypeError, ValueError):
        default_window = 30
    decayed: List[Dict[str, Any]] = []
    for row in db.get_transitions_from(from_screen, app_context=app_context):
        if exclude_destructive and _is_destructive_edge(row):
            continue
        if allowed_intent_verbs is not None and row.get("intent_verb") not in allowed_intent_verbs:
            continue
        # Per-surface staleness: from_screen's override if set, else env default.
        window = default_window
        if staleness_overrides:
            override = staleness_overrides.get(row.get("from_screen"))
            if override is not None:
                window = override
        eff = _effective_confidence(
            row,
            current_build_env=build_env,
            current_app_package=app_package,
            staleness_days_window=window,
        )
        out = dict(row)
        out["_stored_confidence"] = row.get("confidence")
        out["confidence"] = eff
        decayed.append(out)
    decayed.sort(key=lambda r: r["confidence"], reverse=True)
    return decayed


def _normalize_step(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a screen_transitions row into a planner step dict."""
    args_blob = row.get("intent_args_json")
    args: Optional[Dict[str, Any]] = None
    if args_blob:
        try:
            args = json.loads(args_blob)
        except (TypeError, ValueError):
            args = None
    return {
        "from_screen": row["from_screen"],
        "intent_verb": row["intent_verb"],
        "intent_target": row.get("intent_target"),
        "intent_args": args,
        "to_screen": row["to_screen"],
        "confidence": row.get("confidence", 0.0),
    }


def find_path(
    db: Any,
    from_screen: str,
    to_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.5,
    exclude_destructive: bool = False,
    allowed_intent_verbs: Optional[Set[str]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Return the highest-confidence known path of transitions, or None.

    Searches for the path that maximizes its weakest edge — i.e. the most
    reliable route — with shorter paths breaking ties. A 2-hop verified path
    (each edge ≥ 0.95) is preferred over a 1-hop hedge (0.50), because the
    runtime will detect divergence and replan if the executed step doesn't
    land where expected.

    Edges with confidence < min_confidence are excluded entirely. A path of
    length 0 (empty list) means already-at-target.

    Spec 005 additions (defaults preserve legacy behavior):
        exclude_destructive   — drop edges with destructive side_effects.
                                Explore mode + autonomous play set True.
        allowed_intent_verbs  — verb whitelist. None = no restriction.

    Per-surface decay (T021) is automatic — no caller change required.
    """
    if from_screen == to_screen:
        return []
    overrides = _load_staleness_overrides(db)
    counter = itertools.count()
    # heap items: (-min_conf_so_far, hop_count, push_order, current, path)
    pq: list = [(-1.0, 0, next(counter), from_screen, [])]
    best_neg_min: Dict[str, float] = {from_screen: -1.0}
    while pq:
        neg_min_conf, hops, _, current, path = heapq.heappop(pq)
        if current == to_screen:
            return path
        if hops >= max_hops:
            continue
        if neg_min_conf > best_neg_min.get(current, float("inf")):
            continue  # already reached this node with a better min-conf
        rows = _decayed_transitions_from(
            db,
            current,
            app_context=app_context,
            staleness_overrides=overrides,
            exclude_destructive=exclude_destructive,
            allowed_intent_verbs=allowed_intent_verbs,
        )
        for row in rows:
            if row["confidence"] < min_confidence:
                continue
            nxt = row["to_screen"]
            if nxt == from_screen:
                continue  # cycle back to start: skip
            new_min = min(-neg_min_conf, row["confidence"])
            neg_new = -new_min
            if neg_new < best_neg_min.get(nxt, float("inf")):
                best_neg_min[nxt] = neg_new
                step = _normalize_step(row)
                heapq.heappush(
                    pq,
                    (neg_new, hops + 1, next(counter), nxt, path + [step]),
                )
    return None


def propose_next_step(
    db: Any,
    from_screen: str,
    to_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.5,
) -> Optional[Dict[str, Any]]:
    """Return the FIRST step of the path. For one-action-at-a-time loops."""
    path = find_path(
        db,
        from_screen,
        to_screen,
        app_context=app_context,
        max_hops=max_hops,
        min_confidence=min_confidence,
    )
    return path[0] if path else None


# ── T022: stochastic outcomes API (read-only helpers over transition_outcomes) ──
#
# transition_outcomes is keyed by (start_sig, action, end_sig) with observed_count.
# Same start_sig + action can land on N different end_sigs (A/B variants, banner
# rotation, RNG prompts). These helpers expose the distribution; report-diff
# uses `distribution_shift` to flag genuine regressions vs. rotation noise.
#
# These do NOT replace find_path — find_path operates over the legacy
# screen_transitions table (logical-name-keyed, used by goal-driven planning).
# transition_outcomes is signature-hash-keyed, used by the auto-recorder
# and per-action distribution checks.


def outcomes_for(db: Any, start_sig: str, action: str) -> List[Dict[str, Any]]:
    """All observed outcomes for a (start_sig, action), ordered by observed_count desc.

    Empty list when no observations exist yet — caller (path planner / report-diff)
    falls back to whatever default behaviour is appropriate.
    """
    try:
        rows = db._get_conn().execute(
            "SELECT start_sig, action, end_sig, observed_count, last_seen, "
            "edge_kind, side_effect, precondition "
            "FROM transition_outcomes WHERE start_sig=? AND action=? "
            "ORDER BY observed_count DESC, last_seen DESC",
            (start_sig, action),
        ).fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


def top_outcome(db: Any, start_sig: str, action: str) -> Optional[Dict[str, Any]]:
    """The most-observed end_sig for (start_sig, action), or None if unseen."""
    rows = outcomes_for(db, start_sig, action)
    return rows[0] if rows else None


def distribution_shift(
    db: Any,
    start_sig: str,
    action: str,
    baseline_counts: Mapping[str, int],
) -> float:
    """Maximum relative count change between current outcomes and a baseline.

    `baseline_counts`: {end_sig: observed_count_at_baseline}. Returns the
    largest |delta_relative| across end_sigs that appear in either set; 0.0
    when distributions match. Below the configured `OUTCOME_DRIFT_THRESHOLD`
    (default 0.30) the shift is treated as noise (A/B rotation), not regression.
    """
    current = {r["end_sig"]: r["observed_count"] for r in outcomes_for(db, start_sig, action)}
    all_sigs = set(current) | set(baseline_counts)
    if not all_sigs:
        return 0.0
    cur_total = sum(current.values()) or 1
    base_total = sum(baseline_counts.values()) or 1
    max_shift = 0.0
    for sig in all_sigs:
        cur_freq = current.get(sig, 0) / cur_total
        base_freq = baseline_counts.get(sig, 0) / base_total
        denom = max(cur_freq, base_freq, 1e-6)
        max_shift = max(max_shift, abs(cur_freq - base_freq) / denom)
    return max_shift


# ── T023: precondition evaluator over RuntimeFacts ──────────────────────────


def evaluate_precondition(
    precondition_json: Optional[str],
    runtime_facts: Optional[Mapping[str, Any]],
) -> bool:
    """Evaluate a transition_outcomes.precondition predicate against RuntimeFacts.

    Predicate format (intentionally simple — no eval/exec):
        {"logged_in": true, "jurisdiction": "NJ", "balance_gt": 0,
         "feature_flags": {"X": true}}

    Each key is checked against the corresponding RuntimeFacts path. Missing
    runtime_facts → True (permissive — legacy edges with no precondition).
    Unknown keys → False (fail closed) so a typo doesn't silently allow a
    destructive edge.
    """
    if not precondition_json:
        return True
    if runtime_facts is None:
        # Predicate exists but no facts to check against → fail closed.
        return False
    try:
        pred = json.loads(precondition_json) if isinstance(precondition_json, str) else precondition_json
    except (TypeError, ValueError):
        return False
    if not isinstance(pred, dict):
        return False

    for key, expected in pred.items():
        if key == "logged_in":
            actual = bool(runtime_facts.get("target", {}).get("account_ref"))
            if actual != bool(expected):
                return False
        elif key == "jurisdiction":
            if runtime_facts.get("jurisdiction") != expected:
                return False
        elif key == "build_env":
            if runtime_facts.get("build_env") != expected:
                return False
        elif key == "platform":
            if runtime_facts.get("platform") != expected:
                return False
        elif key == "balance_gt":
            balance = runtime_facts.get("extras", {}).get("current_balance_usd")
            if balance is None or balance <= float(expected):
                return False
        elif key == "feature_flags":
            flags = runtime_facts.get("extras", {}).get("feature_flags", {})
            if not isinstance(expected, dict):
                return False
            for flag_name, flag_expected in expected.items():
                if bool(flags.get(flag_name)) != bool(flag_expected):
                    return False
        else:
            # Unknown predicate key — fail closed.
            return False
    return True


def all_reachable(
    db: Any,
    from_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.0,
    exclude_destructive: bool = False,
    allowed_intent_verbs: Optional[Set[str]] = None,
) -> List[str]:
    """Set of screens reachable from `from_screen` within `max_hops`."""
    overrides = _load_staleness_overrides(db)
    visited = {from_screen}
    queue = deque([(from_screen, 0)])
    while queue:
        current, depth = queue.popleft()
        if depth >= max_hops:
            continue
        rows = _decayed_transitions_from(
            db,
            current,
            app_context=app_context,
            staleness_overrides=overrides,
            exclude_destructive=exclude_destructive,
            allowed_intent_verbs=allowed_intent_verbs,
        )
        for row in rows:
            if row["confidence"] < min_confidence:
                continue
            nxt = row["to_screen"]
            if nxt in visited:
                continue
            visited.add(nxt)
            queue.append((nxt, depth + 1))
    return sorted(visited - {from_screen})
