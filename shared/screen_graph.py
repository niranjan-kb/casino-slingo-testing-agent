"""Screen graph — path planning over `screen_transitions`.

Given a start screen and a target screen, find the shortest sequence of
transitions the agent should execute. Returns None when no path is known —
caller hands off to LLM reasoning (and the agent's eventual success will
record a new transition that grows the graph).

This module is the runtime counterpart to the seeded login flow markdown.
The phase-by-phase procedure in goals/login/prompts/user.md becomes data
in screen_transitions; the agent walks the graph instead of reading prose.
"""

from __future__ import annotations

import heapq
import itertools
import json
from collections import deque
from typing import Any, Dict, List, Optional


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
) -> Optional[List[Dict[str, Any]]]:
    """Return the highest-confidence known path of transitions, or None.

    Searches for the path that maximizes its weakest edge — i.e. the most
    reliable route — with shorter paths breaking ties. A 2-hop verified path
    (each edge ≥ 0.95) is preferred over a 1-hop hedge (0.50), because the
    runtime will detect divergence and replan if the executed step doesn't
    land where expected.

    Edges with confidence < min_confidence are excluded entirely. A path of
    length 0 (empty list) means already-at-target.
    """
    if from_screen == to_screen:
        return []
    counter = itertools.count()
    # heap items: (-min_conf_so_far, hop_count, push_order, current, path)
    # heapq is min-heap; negative min_conf → highest min_conf pops first.
    # hop_count is the secondary key (shorter wins ties).
    # push_order is a stable tiebreaker so dicts are never compared.
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
        for row in db.get_transitions_from(current, app_context=app_context):
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


def all_reachable(
    db: Any,
    from_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.0,
) -> List[str]:
    """Set of screens reachable from `from_screen` within `max_hops`."""
    visited = {from_screen}
    queue = deque([(from_screen, 0)])
    while queue:
        current, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for row in db.get_transitions_from(current, app_context=app_context):
            if row["confidence"] < min_confidence:
                continue
            nxt = row["to_screen"]
            if nxt in visited:
                continue
            visited.add(nxt)
            queue.append((nxt, depth + 1))
    return sorted(visited - {from_screen})
