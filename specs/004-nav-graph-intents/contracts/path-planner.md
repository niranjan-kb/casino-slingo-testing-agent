# Contract — Path Planner

**Owner**: `shared/screen_graph.py` (already exists; this contract documents and extends it)

## API (existing, stable)

```python
def find_path(
    db: ScreenMapDB,
    from_screen: str,
    to_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.5,
) -> Optional[List[Dict[str, Any]]]:
    """Returns the highest-min-confidence path of transitions, or None.

    Each step: {from_screen, intent_verb, intent_target, intent_args, to_screen, confidence}.
    Path of length 0 means already-at-target.
    """

def propose_next_step(
    db: ScreenMapDB,
    from_screen: str,
    to_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.5,
) -> Optional[Dict[str, Any]]:
    """First step of find_path; for one-action-at-a-time loops."""

def all_reachable(
    db: ScreenMapDB,
    from_screen: str,
    *,
    app_context: str = "platform",
    max_hops: int = 12,
    min_confidence: float = 0.0,
) -> List[str]:
    """Set of screens reachable from from_screen within max_hops."""
```

## Semantics (FR-005, FR-006, FR-007)

- **Max-min-confidence path**: priority-queue search where each candidate path's score is `min(edge.confidence for edge in path)`. Highest min-conf pops first; ties break by hop count (shorter wins); insertion order tertiary so dicts never compare.
- **`min_confidence` floor**: edges below the floor are excluded from search entirely. Used to prefer verified flows over hedge edges.
- **`max_hops` cap**: hard limit on path length. Default 12 covers the deepest seeded login flow (9 hops) with headroom for navigate-then-play paths.
- **Already-at-target**: returns `[]` (empty list), distinct from "no path" (returns `None`).
- **Cycle handling**: visited set on screens within a single search prevents infinite loops; the same screen can still appear as a destination of multiple competing edges in different searches.

## Read-time decay (R5, R6, MW-3) — NEW

A wrapper around `db.get_transitions_from` applies decay to each row's confidence before BFS sees it:

```python
def _effective_confidence(row, current_build_env, current_app_package, now_iso):
    conf = row["confidence"]
    # Build mismatch
    if row.get("build_env", "unknown") not in (current_build_env, "unknown"):
        conf *= 0.5
    if row.get("app_package", "unknown") not in (current_app_package, "unknown"):
        conf *= 0.5
    # Staleness ramp
    last_verified = row.get("last_verified")
    if last_verified:
        days_stale = _days_between(last_verified, now_iso)
        staleness_window = int(os.getenv("SCREEN_MAP_STALENESS_DAYS", "30"))
        if days_stale > staleness_window:
            ramp = max(0.5, 1.0 - (days_stale - staleness_window) / 60.0)
            conf *= ramp
    return conf
```

Decay is **read-only** — the row's stored confidence is unchanged (FR-026). On the next successful verification (`record_transition_observation(success=True)`), `last_verified` is bumped and stored confidence is recomputed; the row's effective confidence resumes at the stored value.

## Performance budget (Technical Context)

- A single `find_path` call MUST complete in < 50 ms on a graph of ≤ 1000 transitions. The current planner is in-memory BFS over rows fetched per-node from SQLite (no pre-loading); SQLite query overhead is the dominant cost.
- v2 optimization (deferred): bulk-load the graph at workflow start into an in-memory adjacency map. Only do this if path-finding becomes a hot spot.

## Integration with intents

Intents call the planner indirectly through SmartTap or the workflow. A typical turn:

```
1. Workflow asks LLM: "your active intent is X; current screen is Y; available tools..."
2. LLM emits: {active_intent: X, next: confirm, tool: SmartTap, args: {...}}
3. Workflow dispatches SmartTap, which:
   a. Reads current screen via DetectScreen
   b. Calls propose_next_step(current_screen, intent.end_state_signatures[0])
   c. If a step is returned, executes its (verb, target, args)
   d. If None, hands back to LLM to reason from page-source (FR-016)
```

The path planner is invisible to the LLM — the planner is a deterministic shortcut consumed by tools, not a tool the LLM directly invokes.
