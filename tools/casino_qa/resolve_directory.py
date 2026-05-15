"""ResolveDirectory — fuzzy resolver from a free-text query to a `game_directory` slug.

Per spec 005 T037 / research §R1. Pure SQLite + a tiny token-set ratio in Python;
no LLM call. Replay-deterministic, cheap, and bounded by the directory's small
size (≤ a few hundred rows in practice).

The pipeline (each step short-circuits on a usable hit):
    1. exact slug match
    2. kind filter (when supplied) + LIKE on display_name and aliases_json
    3. token-set ratio fallback (Jaccard over normalised tokens)
    4. rank by popularity DESC, last_played_at DESC
    5. K=0 → unresolved=true; downstream `intent_navigate_to_game` falls
       through to the search-bar branch with the literal query

Anti-hardcoding: nothing per-game lives here. The list of valid kinds is read
from the directory rows themselves, not a Python constant.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ._deps import get_screen_db


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def resolve_directory(args: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a free-text query to a game_directory slug.

    Args (passed by the planner via tool args):
        query:        free text (e.g. "fanatics spin to win", "slingo")
        kind:         optional filter — "slots" | "slingo" | "blackjack" | "roulette"
        slug:         optional exact slug (skip fuzzy resolution if provided)
        limit:        max alternatives to return (default 5, capped at 20)

    Returns:
        {
            "resolved": bool,
            "slug": str | null,
            "kind": str | null,
            "loaded_signature": str | null,
            "alternatives": [{slug, display_name, kind, popularity}, ...],
            "reason": "exact_slug" | "name_like" | "alias_match" | "token_set" |
                      "no_query" | "no_db" | "unresolved",
        }
    """
    query = (args.get("query") or "").strip()
    kind = (args.get("kind") or "").strip() or None
    explicit_slug = (args.get("slug") or "").strip() or None
    try:
        limit = max(1, min(20, int(args.get("limit", 5))))
    except (TypeError, ValueError):
        limit = 5

    db = get_screen_db()
    if db is None:
        return _empty(reason="no_db")

    conn = db._get_conn()

    # 1. Exact slug match — used when the operator names a known slug exactly.
    if explicit_slug:
        row = conn.execute(
            "SELECT slug, display_name, kind, popularity, loaded_signature "
            "FROM game_directory WHERE slug = ? AND available = 1",
            (explicit_slug,),
        ).fetchone()
        if row:
            return _hit(row, reason="exact_slug", alternatives=[])

    if not query:
        return _empty(reason="no_query")

    # 2. Kind filter (when supplied) + LIKE on display_name and aliases_json.
    where_kind = ""
    params: List[Any] = []
    if kind:
        where_kind = " AND kind = ? "
        params.append(kind)

    name_pattern = f"%{query.lower()}%"
    name_rows = conn.execute(
        f"SELECT slug, display_name, kind, popularity, loaded_signature, aliases_json "
        f"FROM game_directory "
        f"WHERE available = 1 {where_kind} "
        f"  AND (LOWER(display_name) LIKE ? OR LOWER(slug) LIKE ?) "
        f"ORDER BY popularity DESC, last_played_at DESC NULLS LAST "
        f"LIMIT ?",
        (*params, name_pattern, name_pattern, limit),
    ).fetchall()

    if name_rows:
        # The first row IS the top pick. Remainder are alternatives.
        top = name_rows[0]
        alts = [_alt(r) for r in name_rows[1:]]
        return _hit(top, reason="name_like", alternatives=alts)

    # 3. Alias match — aliases_json is stored as a JSON array.
    alias_rows = conn.execute(
        f"SELECT slug, display_name, kind, popularity, loaded_signature, aliases_json "
        f"FROM game_directory "
        f"WHERE available = 1 {where_kind} "
        f"ORDER BY popularity DESC, last_played_at DESC NULLS LAST",
        tuple(params),
    ).fetchall()
    query_lower = query.lower()
    matched_aliases: List[Any] = []
    for r in alias_rows:
        try:
            aliases = json.loads(r["aliases_json"] or "[]")
        except (TypeError, ValueError):
            aliases = []
        if any(query_lower in str(a).lower() for a in aliases):
            matched_aliases.append(r)
            if len(matched_aliases) >= limit:
                break
    if matched_aliases:
        top = matched_aliases[0]
        alts = [_alt(r) for r in matched_aliases[1:]]
        return _hit(top, reason="alias_match", alternatives=alts)

    # 4. Token-set ratio fallback — when the substring search misses, do a
    #    Jaccard-style overlap on tokenised query vs. tokenised display_name.
    q_tokens = _tokenise(query)
    if q_tokens:
        scored: List[Any] = []
        for r in alias_rows:
            name_tokens = _tokenise(r["display_name"] or "")
            if not name_tokens:
                continue
            overlap = len(q_tokens & name_tokens)
            if overlap == 0:
                continue
            denom = len(q_tokens | name_tokens)
            ratio = overlap / denom if denom else 0.0
            if ratio >= 0.3:
                scored.append((ratio, r))
        # Highest ratio first; ties broken by popularity (already ORDER BY'd).
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            top_row = scored[0][1]
            alts = [_alt(s[1]) for s in scored[1:limit]]
            return _hit(top_row, reason="token_set", alternatives=alts)

    return _empty(reason="unresolved")


# ── helpers ──


def _hit(
    row: Any,
    *,
    reason: str,
    alternatives: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "resolved": True,
        "slug": row["slug"],
        "kind": row["kind"],
        "loaded_signature": row["loaded_signature"],
        "alternatives": alternatives,
        "reason": reason,
    }


def _alt(row: Any) -> Dict[str, Any]:
    return {
        "slug": row["slug"],
        "display_name": row["display_name"],
        "kind": row["kind"],
        "popularity": row["popularity"],
    }


def _empty(*, reason: str) -> Dict[str, Any]:
    return {
        "resolved": False,
        "slug": None,
        "kind": None,
        "loaded_signature": None,
        "alternatives": [],
        "reason": reason,
    }


def _tokenise(text: str) -> set:
    """Lowercase + extract alphanumerics; drop common stopwords that pollute matches."""
    tokens = {m.group(0) for m in _TOKEN_RE.finditer(text.lower())}
    return tokens - {"the", "a", "an", "of", "and", "or", "to", "for", "on", "in"}
